import io
import json
import unittest
from unittest.mock import Mock, patch
import uuid

try:
    from jackfruit.controller import RecoveryController, output_port
    from os_ken.ofproto import ofproto_v1_3, ofproto_v1_3_parser
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, 'OS-Ken required; run the Docker test command')
class ControllerTests(unittest.TestCase):
    def test_framework_event_queue_is_preserved(self):
        with patch.dict('os.environ', {'SDN_CONTROL_TOKEN':'unit-test-token-123'}), \
                patch('jackfruit.controller.hub.spawn'):
            controller = RecoveryController()
        self.assertTrue(callable(controller.events.put))
        self.assertEqual(controller.history, [])

    def setUp(self):
        self.controller = RecoveryController.__new__(RecoveryController)
        c = self.controller
        c.mode, c.token, c.path = 'dynamic', 'unit-test-token-123', 'primary'
        c.datapaths, c.down, c.port_stats = {}, set(), {}
        c.history, c.pending_barriers = [], set()
        c.switch_started = c.switch_completed = None
        for i in range(1,5):
            dp = Mock(id=i, ofproto=ofproto_v1_3, ofproto_parser=ofproto_v1_3_parser)
            counter = iter(range(1,1000))
            def set_xid(message, counter=counter):
                message.xid = next(counter)
            dp.set_xid = set_xid
            c.datapaths[i] = dp

    def request(self, token=None, message=None, path='/event'):
        raw = json.dumps(message).encode() if message is not None else b''
        env = dict(REQUEST_METHOD='POST' if message is not None else 'GET', PATH_INFO=path,
            CONTENT_LENGTH=str(len(raw)), HTTP_AUTHORIZATION='Bearer '+(token or ''),
            **{'wsgi.input':io.BytesIO(raw)})
        status = []
        reply = self.controller.http(env, lambda code, headers: status.append(code))
        return status[0], json.loads(b''.join(reply))

    def test_loss_event_changes_rules_and_barriers_complete(self):
        code, reply = self.request(self.controller.token,
            dict(type='loss', transfer=str(uuid.uuid4()), missing=[2,4], retransmissions=3))
        self.assertEqual(code, '200 OK')
        self.assertTrue(reply['changed'])
        self.assertEqual(reply['path'], 'backup')
        self.assertEqual(reply['pending_barriers'], 4)
        for switch, xid in list(self.controller.pending_barriers):
            self.controller.barrier(Mock(msg=Mock(datapath=Mock(id=switch), xid=xid)))
        self.assertIsNotNone(self.controller.switch_completed)
        for dp in self.controller.datapaths.values():
            messages = [call.args[0] for call in dp.send_msg.call_args_list]
            self.assertEqual(len(messages), 4)
            self.assertEqual(messages[0].priority, 100)

    def test_static_mode_is_valid_baseline(self):
        self.controller.mode = 'static'
        self.assertFalse(self.controller.reroute('application_loss'))
        self.assertEqual(self.controller.path, 'primary')

    def test_auth_and_bad_payload_do_not_reroute(self):
        self.assertEqual(self.request(path='/status')[0], '401 Unauthorized')
        self.assertEqual(self.request(self.controller.token, {'type':'loss'})[0], '400 Bad Request')
        self.assertEqual(self.request(self.controller.token,
            dict(type='loss', transfer=42, missing=[1], retransmissions=3))[0], '400 Bad Request')
        self.assertEqual(self.controller.path, 'primary')

    def test_unavailable_backup_and_repeated_events(self):
        self.controller.down.add((3,2))
        self.assertFalse(self.controller.reroute('application_loss'))
        self.controller.down.clear()
        self.assertTrue(self.controller.reroute('application_loss'))
        self.assertFalse(self.controller.reroute('application_loss'))

    def test_port_failure_and_destination_mapping(self):
        dp = self.controller.datapaths[2]
        self.controller.port_status(Mock(msg=Mock(datapath=dp,
            reason=ofproto_v1_3.OFPPR_MODIFY, desc=Mock(port_no=2,
            state=ofproto_v1_3.OFPPS_LINK_DOWN))))
        self.assertEqual(self.controller.path, 'backup')
        self.assertEqual(output_port(1,'server','backup'),4)
        self.assertEqual(output_port(4,'client1','backup'),2)


if __name__ == '__main__':
    unittest.main()
