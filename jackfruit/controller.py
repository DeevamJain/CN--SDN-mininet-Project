"""Fixed diamond OpenFlow 1.3 controller with an authenticated application event API."""
import hmac
import json
import os
import time
import uuid
import eventlet
from eventlet import wsgi
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.ofproto import ofproto_v1_3

HOSTS = {'client1': '00:00:00:00:00:01', 'server': '00:00:00:00:00:02',
         'client2': '00:00:00:00:00:03'}


def output_port(switch, destination, path):
    if switch == 1:
        return {'client1': 1, 'client2': 2, 'server': 3 if path == 'primary' else 4}[destination]
    if switch in (2, 3):
        return 2 if destination == 'server' else 1
    if switch == 4:
        return 3 if destination == 'server' else (1 if path == 'primary' else 2)
    raise ValueError('unknown datapath')


class RecoveryController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = os.environ.get('SDN_MODE', 'dynamic')
        if self.mode not in ('static', 'dynamic'):
            raise ValueError('SDN_MODE must be static or dynamic')
        self.token = os.environ.get('SDN_CONTROL_TOKEN', '')
        if len(self.token) < 16:
            raise ValueError('SDN_CONTROL_TOKEN must contain at least 16 characters')
        self.path = 'primary'
        self.datapaths, self.down, self.port_stats = {}, set(), {}
        self.history = []
        self.pending_barriers = set()
        self.switch_started = None
        self.switch_completed = None
        self.api = hub.spawn(self.http_server)
        self.monitor_thread = hub.spawn(self.monitor)

    def record(self, event):
        event = dict(wall_time=time.time(), **event)
        self.history.append(event)
        self.history = self.history[-1000:]
        path = os.environ.get('SDN_EVENT_LOG')
        if path:
            with open(path, 'a') as f:
                f.write(json.dumps(event)+'\n')

    def http_server(self):
        listener = eventlet.listen(('0.0.0.0', int(os.environ.get('SDN_API_PORT', '8080'))))
        wsgi.server(listener, self.http, log_output=False, socket_timeout=2)

    def http(self, env, start_response):
        code, result = '200 OK', {}
        auth = env.get('HTTP_AUTHORIZATION', '')
        if not hmac.compare_digest(auth.encode(), ('Bearer '+self.token).encode()):
            code, result = '401 Unauthorized', {'error': 'unauthorized'}
        elif env['REQUEST_METHOD'] == 'GET' and env['PATH_INFO'] == '/status':
            result = self.status()
        elif env['REQUEST_METHOD'] == 'POST' and env['PATH_INFO'] == '/event':
            try:
                length = int(env.get('CONTENT_LENGTH', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('invalid content length')
                message = json.loads(env['wsgi.input'].read(length))
                if not isinstance(message['transfer'], str):
                    raise ValueError('invalid transfer ID')
                uuid.UUID(message['transfer'])
                missing = message['missing']
                if (message['type'] != 'loss' or type(message['retransmissions']) is not int
                        or message['retransmissions'] < 3 or not isinstance(missing, list)
                        or not 1 <= len(missing) <= 32
                        or any(type(n) is not int or not 0 <= n < 100000 for n in missing)):
                    raise ValueError('invalid loss event')
                changed = self.reroute('application_loss', message['transfer'])
                result = dict(changed=changed, **self.status())
            except (ValueError, KeyError, TypeError, UnicodeError):
                code, result = '400 Bad Request', {'error': 'invalid event'}
        else:
            code, result = '404 Not Found', {'error': 'unknown endpoint'}
        raw = json.dumps(result).encode()
        start_response(code, [('Content-Type', 'application/json'), ('Content-Length', str(len(raw)))])
        return [raw]

    def status(self):
        return dict(mode=self.mode, path=self.path, switches=sorted(self.datapaths),
            down_ports=sorted(self.down), pending_barriers=len(self.pending_barriers),
            switch_started_wall=self.switch_started, switch_completed_wall=self.switch_completed,
            events=self.history[-20:], port_stats=self.port_stats)

    def program(self, dp, track=False):
        p, ofp = dp.ofproto_parser, dp.ofproto
        # Exact destination rules replace matching entries without removing the table.
        for host, mac in HOSTS.items():
            actions = [p.OFPActionOutput(output_port(dp.id, host, self.path))]
            dp.send_msg(p.OFPFlowMod(datapath=dp, priority=100,
                match=p.OFPMatch(eth_dst=mac),
                instructions=[p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]))
        request = p.OFPBarrierRequest(dp)
        dp.set_xid(request)
        if track:
            self.pending_barriers.add((dp.id, request.xid))
        dp.send_msg(request)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        if dp.id not in (1, 2, 3, 4):
            dp.close()
            return
        self.datapaths[dp.id] = dp
        self.program(dp)

    @set_ev_cls(ofp_event.EventOFPStateChange, DEAD_DISPATCHER)
    def disconnected(self, ev):
        self.datapaths.pop(ev.datapath.id, None)
        self.record(dict(type='switch_disconnected', switch=ev.datapath.id))

    def reroute(self, reason, transfer=None):
        if self.mode != 'dynamic' or self.path == 'backup':
            return False
        backup_ports = {(1, 4), (3, 1), (3, 2), (4, 2)}
        if set(self.datapaths) != {1, 2, 3, 4} or self.down & backup_ports:
            self.record(dict(type='reroute_unavailable', reason=reason))
            return False
        self.path = 'backup'
        self.switch_started = time.time()
        self.switch_completed = None
        self.pending_barriers.clear()
        # Program transit before ingress. Small cross-switch transition loss is
        # handled by selective repeat; barriers measure completion, not atomicity.
        for switch in (3, 2, 4, 1):
            self.program(self.datapaths[switch], track=True)
        self.record(dict(type='reroute_requested', reason=reason, transfer=transfer, path=self.path))
        return True

    @set_ev_cls(ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER)
    def barrier(self, ev):
        key = (ev.msg.datapath.id, ev.msg.xid)
        if key in self.pending_barriers:
            self.pending_barriers.remove(key)
            if not self.pending_barriers:
                self.switch_completed = time.time()
                self.record(dict(type='reroute_completed', path=self.path,
                    controller_update_s=self.switch_completed-self.switch_started))

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status(self, ev):
        msg = ev.msg
        key = (msg.datapath.id, msg.desc.port_no)
        down = msg.reason == msg.datapath.ofproto.OFPPR_DELETE or bool(
            msg.desc.state & msg.datapath.ofproto.OFPPS_LINK_DOWN)
        if down:
            self.down.add(key)
        else:
            self.down.discard(key)
        self.record(dict(type='port_status', switch=key[0], port=key[1], down=down))
        if down and key in {(1, 3), (2, 1), (2, 2), (4, 1)}:
            self.reroute('primary_link_down')

    def monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                dp.send_msg(dp.ofproto_parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
                dp.send_msg(dp.ofproto_parser.OFPPortDescStatsRequest(dp, 0))
            hub.sleep(1)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def descriptions(self, ev):
        dp = ev.msg.datapath
        for port in ev.msg.body:
            key = (dp.id, port.port_no)
            if port.state & dp.ofproto.OFPPS_LINK_DOWN:
                self.down.add(key)
            else:
                self.down.discard(key)
        if self.down & {(1, 3), (2, 1), (2, 2), (4, 1)}:
            self.reroute('monitored_primary_link_down')

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def statistics(self, ev):
        self.port_stats[str(ev.msg.datapath.id)] = [dict(port=p.port_no,
            rx_packets=p.rx_packets, tx_packets=p.tx_packets,
            rx_dropped=p.rx_dropped, tx_dropped=p.tx_dropped,
            rx_errors=p.rx_errors, tx_errors=p.tx_errors) for p in ev.msg.body]
