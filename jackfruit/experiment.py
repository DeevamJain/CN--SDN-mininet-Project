"""Root-only reproducible Mininet experiment. Run inside the lab container/VM."""
import argparse
import json
import os
import platform
import importlib.metadata
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request


def status(token):
    request = urllib.request.Request('http://127.0.0.1:8080/status',
        headers={'Authorization': 'Bearer '+token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=1) as response:
        return json.load(response)


def wait_until(predicate, timeout=60):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        try:
            result = predicate()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise RuntimeError('readiness check timed out')


def run(mode, scenario, output, packets=400, seed=1):
    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSSwitch
    from mininet.link import TCLink
    if os.geteuid() != 0:
        raise RuntimeError('Mininet experiment requires root')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)  # never reuse stale results
    root = Path(__file__).resolve().parent.parent
    token = secrets.token_hex(24)
    env = dict(os.environ, SDN_CONTROL_TOKEN=token, SDN_MODE=mode,
               SDN_EVENT_LOG=str(output/'controller-events.jsonl'))
    env['PYTHONPATH'] = str(root)
    log_files, processes = [], []
    net = None
    metadata = dict(mode=mode, scenario=scenario, seed=seed, packets=packets,
        started_wall=time.time(), valid=False,
        environment=dict(kernel=platform.release(), machine=platform.machine(),
            cpus=os.cpu_count(), python=platform.python_version(),
            osken=importlib.metadata.version('os-ken'),
            memory_kib=next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                            if line.startswith('MemTotal:'))))
    def spawn(command, host=None, name='process'):
        log = open(output/(name+'.log'), 'w')
        log_files.append(log)
        proc = (host.popen if host else subprocess.Popen)(command, cwd=str(root), env=env,
            stdout=log, stderr=subprocess.STDOUT)
        processes.append(proc)
        return proc
    try:
        manager = shutil.which('osken-manager')
        if not manager:
            raise RuntimeError('activate the SDN Python environment first')
        controller = spawn([manager, '--ofp-tcp-listen-port', '6653',
                            str(root/'jackfruit/controller.py')], name='controller')
        wait_until(lambda: controller.poll() is None and status(token))
        net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, build=False)
        net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
        h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        switches = {i: net.addSwitch('s%d' % i, dpid='%016x' % i,
            protocols='OpenFlow13', failMode='secure') for i in range(1, 5)}
        s1, s2, s3, s4 = [switches[i] for i in range(1, 5)]
        for a, b, pa, pb in [(h1,s1,0,1),(h3,s1,0,2),(h2,s4,0,3),
                             (s1,s2,3,1),(s2,s4,2,1),(s1,s3,4,1),(s3,s4,2,2)]:
            net.addLink(a, b, port1=pa, port2=pb, bw=10, delay='5ms', max_queue_size=100)
        # Dedicated out-of-band control links keep loss reports off impaired paths.
        mgmt = net.addHost('mgmt', inNamespace=False, ip=None)
        control_links = []
        for index, host in [(1,h1),(2,h3)]:
            link = net.addLink(host, mgmt, cls=__import__('mininet.link', fromlist=['Link']).Link)
            control_links.append((index, host, link))
        net.build()
        net.start()
        for index, host, link in control_links:
            host.setIP('10.255.%d.2/30' % index, intf=link.intf1)
            mgmt.setIP('10.255.%d.1/30' % index, intf=link.intf2)
        for host in (h1,h2,h3):
            for peer in (h1,h2,h3):
                if host != peer:
                    host.setARP(peer.IP(intf=peer.defaultIntf()), peer.MAC())
        wait_until(lambda: status(token)['switches'] == [1,2,3,4])
        if not net.waitConnected(timeout=15):
            raise RuntimeError('switches did not connect')
        if net.ping([h1,h2,h3]) != 0:
            raise RuntimeError('initial topology ping failed (check OVS and tc kernel support)')
        server = spawn([sys.executable, '-m', 'jackfruit.receiver', '--output',
                        str(output/'receiver.json')], h2, 'receiver')
        wait_until(lambda: '"ready": true' in (output/'receiver.log').read_text())
        clients = []
        for index, host in [(1,h1),(2,h3)]:
            clients.append(spawn([sys.executable, '-m', 'jackfruit.sender', '--host', '10.0.0.2',
                '--packets', str(packets), '--seed', str(seed+index), '--retries', '20',
                '--deadline', '20', '--event-url', 'http://10.255.%d.1:8080' % index,
                '--output', str(output/('client%d.json' % index))], host, 'client%d' % index))
        for index in (1,2):
            wait_until(lambda index=index: '"ready": true' in
                       (output/('client%d.log' % index)).read_text())
        time.sleep(.8)
        if all(c.poll() is not None for c in clients):
            raise RuntimeError('transfers ended before fault injection; increase packets')
        metadata['fault_wall'] = time.time()
        if scenario == 'loss':
            # Root namespace switch interfaces belong only to this experiment.
            subprocess.run(['tc','qdisc','replace','dev','s2-eth2','root','netem','loss','35%'], check=True)
        elif scenario == 'link_failure':
            net.configLinkStatus('s2','s4','down')
        elif scenario != 'normal':
            raise ValueError('unknown scenario')
        metadata['client_exit_codes'] = [c.wait(timeout=30) for c in clients]
        if any(code not in (0,2) for code in metadata['client_exit_codes']):
            raise RuntimeError('client crashed; inspect client logs')
        time.sleep(.3)
        metadata['controller'] = status(token)
        if server.poll() is not None:
            raise RuntimeError('receiver exited unexpectedly')
        metadata['tc_stats'] = s2.cmd('tc -s qdisc show dev s2-eth2')
        metadata['flows'] = {str(i): sw.cmd('ovs-ofctl -O OpenFlow13 dump-flows '+sw.name)
                             for i, sw in switches.items()}
        for index in (1,2):
            data = json.loads((output/('client%d.json' % index)).read_text())
            if data['packets'] != packets:
                raise RuntimeError('incomplete client output')
            if (mode == 'dynamic' or scenario == 'normal') and not data['complete']:
                raise RuntimeError('required reliable delivery failed')
        if scenario == 'normal' and metadata['controller']['path'] != 'primary':
            raise RuntimeError('false loss alarm changed the normal route')
        if mode == 'dynamic' and scenario != 'normal':
            if (metadata['controller']['path'] != 'backup'
                    or metadata['controller']['pending_barriers'] != 0
                    or metadata['controller']['switch_completed_wall'] is None):
                raise RuntimeError('required dynamic backup installation failed')
            reasons = [event.get('reason') for event in metadata['controller']['events']]
            if scenario == 'loss' and 'application_loss' not in reasons:
                raise RuntimeError('loss scenario did not exercise socket-to-SDN integration')
        metadata['valid'] = True
    except Exception as error:
        metadata['error'] = str(error)
        raise
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        if net is not None:
            net.stop()
        for log in log_files:
            log.close()
        metadata['ended_wall'] = time.time()
        (output/'experiment.json').write_text(json.dumps(metadata, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['static','dynamic'], required=True)
    p.add_argument('--scenario', choices=['normal','loss','link_failure'], required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--packets', type=int, default=400)
    p.add_argument('--seed', type=int, default=1)
    args = p.parse_args()
    run(**vars(args))


if __name__ == '__main__':
    main()
