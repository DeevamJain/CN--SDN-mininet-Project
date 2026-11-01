"""Multiplex concurrent UDP transfers and ACK every valid packet, including duplicates."""
import argparse
import json
import signal
import socket
import time
from .protocol import MAX_DATAGRAM, decode, encode


class Receiver:
    def __init__(self, host='0.0.0.0', port=9000, ttl=120, max_sessions=256,
                 drop_every=0, drop_ack_every=0, max_sequences=200000):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(.1)
        self.ttl, self.max_sessions = ttl, max_sessions
        self.drop_every, self.drop_ack_every = drop_every, drop_ack_every
        self.sessions = {}
        self.tracked, self.max_sequences = 0, max_sequences
        self.count = self.invalid = self.rejected = self.expired = 0
        self.running = True

    @property
    def address(self):
        return self.socket.getsockname()

    def serve(self):
        try:
            while self.running:
                now = time.monotonic()
                for key in [k for k, s in self.sessions.items() if now - s['last'] > self.ttl]:
                    self.tracked -= len(self.sessions[key]['seen'])
                    del self.sessions[key]
                    self.expired += 1
                try:
                    raw, peer = self.socket.recvfrom(MAX_DATAGRAM + 1)
                except socket.timeout:
                    continue
                try:
                    msg = decode(raw)
                    if msg['type'] != 'data':
                        raise ValueError('receiver expects data')
                except (ValueError, TypeError, KeyError, UnicodeError):
                    self.invalid += 1
                    continue
                self.count += 1
                if self.drop_every and self.count % self.drop_every == 0:
                    continue  # deterministic application-level test impairment
                key = (peer, msg['transfer'])
                if key not in self.sessions:
                    if len(self.sessions) >= self.max_sessions:
                        self.rejected += 1
                        continue
                    self.sessions[key] = dict(total=msg['total'], seen=set(), highest=-1,
                        gap_events=0, duplicates=0, received=0, last=now, start=now)
                session = self.sessions[key]
                if session['total'] != msg['total']:
                    self.invalid += 1
                    continue
                session['last'] = now
                session['received'] += 1
                seq = msg['seq']
                if seq in session['seen']:
                    session['duplicates'] += 1
                else:
                    if self.tracked >= self.max_sequences:
                        self.rejected += 1
                        continue
                    if seq > session['highest'] + 1:
                        session['gap_events'] += seq - session['highest'] - 1
                    session['highest'] = max(seq, session['highest'])
                    session['seen'].add(seq)
                    self.tracked += 1
                if not self.drop_ack_every or self.count % self.drop_ack_every:
                    self.socket.sendto(encode(dict(type='ack', transfer=msg['transfer'], seq=seq)), peer)
        finally:
            self.socket.close()

    def report(self):
        return dict(invalid=self.invalid, rejected=self.rejected, expired=self.expired,
            sessions=[dict(peer='%s:%s' % peer, transfer=transfer,
                total=s['total'], unique=len(s['seen']), missing=s['total']-len(s['seen']),
                duplicates=s['duplicates'], received_datagrams=s['received'], gap_events=s['gap_events'],
                complete=len(s['seen']) == s['total'])
                for (peer, transfer), s in self.sessions.items()])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=9000)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    receiver = Receiver(args.host, args.port)
    def stop(*_):
        receiver.running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(json.dumps(dict(ready=True, address=receiver.address)), flush=True)
    receiver.serve()
    with open(args.output, 'w') as f:
        json.dump(receiver.report(), f, indent=2)


if __name__ == '__main__':
    main()
