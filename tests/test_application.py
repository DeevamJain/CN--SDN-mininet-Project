import concurrent.futures
import json
import socket
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from jackfruit.protocol import decode, encode
from jackfruit.receiver import Receiver
from jackfruit.sender import transfer


class ApplicationTests(unittest.TestCase):
    def receiver(self, **kwargs):
        receiver = Receiver('127.0.0.1', 0, **kwargs)
        thread = threading.Thread(target=receiver.serve)
        thread.start()
        def cleanup():
            receiver.running = False
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.addCleanup(cleanup)
        return receiver

    def send(self, receiver, **kwargs):
        return transfer(*receiver.address, packets=40, interval=0,
                        timeout=.04, deadline=4, **kwargs)

    def test_concurrent_clients_complete_independent_sessions(self):
        receiver = self.receiver()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda seed: self.send(receiver, seed=seed), range(4)))
        self.assertTrue(all(r['complete'] for r in results))
        self.assertEqual(len(receiver.report()['sessions']), 4)
        self.assertTrue(all(s['unique'] == 40 for s in receiver.report()['sessions']))

    def test_missing_data_and_acks_retransmitted_without_duplicate_delivery(self):
        receiver = self.receiver(drop_every=4, drop_ack_every=3)
        result = self.send(receiver)
        self.assertTrue(result['complete'])
        self.assertGreater(result['retransmissions'], 0)
        session = receiver.report()['sessions'][0]
        self.assertEqual(session['unique'], 40)
        self.assertGreater(session['duplicates'], 0)
        self.assertGreater(session['gap_events'], 0)

    def test_no_receiver_fails_with_bounded_retries(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        start = time.monotonic()
        result = transfer('127.0.0.1', port, packets=3, interval=0,
                          timeout=.03, retries=2, deadline=1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['failed'], 3)
        self.assertLessEqual(result['sent_datagrams'], 9)
        self.assertLess(time.monotonic()-start, 1.5)

    def test_malformed_datagrams_do_not_kill_receiver(self):
        receiver = self.receiver()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for value in [b'x', b'[]', b'x'*1500,
                          json.dumps(dict(v=1, transfer=2, type='data')).encode()]:
                sock.sendto(value, receiver.address)
        self.assertTrue(self.send(receiver)['complete'])
        self.assertEqual(receiver.invalid, 4)

    def test_reordering_duplicates_and_total_consistency(self):
        receiver = self.receiver()
        transfer_id = str(uuid.uuid4())
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            for seq in (2, 0, 2, 1):
                sock.sendto(encode(dict(type='data', transfer=transfer_id,
                    seq=seq, total=3, payload='eA==')), receiver.address)
                self.assertEqual(decode(sock.recv(1400))['seq'], seq)
            sock.sendto(encode(dict(type='data', transfer=transfer_id,
                seq=0, total=4, payload='eA==')), receiver.address)
            time.sleep(.02)
        session = receiver.report()['sessions'][0]
        self.assertTrue(session['complete'])
        self.assertEqual(session['duplicates'], 1)
        self.assertEqual(session['gap_events'], 2)
        self.assertEqual(receiver.invalid, 1)

    def test_session_capacity_and_expiry(self):
        receiver = self.receiver(max_sessions=1, ttl=.15)
        self.assertTrue(self.send(receiver)['complete'])
        second = self.send(receiver, retries=0)
        self.assertFalse(second['complete'])
        self.assertGreater(receiver.rejected, 0)
        time.sleep(.3)
        self.assertTrue(self.send(receiver)['complete'])
        self.assertGreaterEqual(receiver.expired, 1)

    def test_protocol_rejects_unknown_version_and_bad_sequence(self):
        for message in [dict(v=2), dict(v=1, type='ack', transfer=str(uuid.uuid4()), seq=-1),
                        dict(v=1, type='ack', transfer=str(uuid.uuid4()), seq=True)]:
            with self.assertRaises(ValueError):
                decode(json.dumps(message).encode())

    def test_application_reports_loss_over_authenticated_http(self):
        receiver = self.receiver(drop_every=2)
        events = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                events.append((self.path, self.headers.get('Authorization'),
                    json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                receiver.drop_every = 0  # emulate removal of impairment, not an SDN dataplane
                raw = b'{"path":"backup","changed":true}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def log_message(self, *_):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            result = self.send(receiver, event_url='http://127.0.0.1:%d' % server.server_port,
                               token='test-token')
            self.assertTrue(result['complete'])
            self.assertGreater(result['retransmissions'], 2)
            self.assertEqual(events[0][0], '/event')
            self.assertEqual(events[0][1], 'Bearer test-token')
            self.assertEqual(events[0][2]['transfer'], result['transfer'])
            self.assertEqual(result['notifications'][0]['response']['path'], 'backup')
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_receiver_global_sequence_budget(self):
        receiver = self.receiver(max_sequences=5)
        result = self.send(receiver, retries=0)
        self.assertFalse(result['complete'])
        self.assertEqual(receiver.tracked, 5)
        self.assertGreater(receiver.rejected, 0)


if __name__ == '__main__':
    unittest.main()
