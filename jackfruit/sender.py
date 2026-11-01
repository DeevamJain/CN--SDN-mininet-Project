"""Selective-repeat UDP with bounded retries and loss-triggered SDN notification."""
import argparse
import base64
import json
import os
import random
import socket
import time
import urllib.request
import uuid
from .protocol import MAX_DATAGRAM, MAX_PACKETS, MAX_PAYLOAD, decode, encode


def notify(url, token, event):
    request = urllib.request.Request(url.rstrip('/') + '/event',
        data=json.dumps(event).encode(), headers={'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token}, method='POST')
    # The private lab control endpoint must not be sent to an Internet proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=.5) as response:
        return json.load(response)


def transfer(host, port=9000, packets=200, payload_size=256, window=16,
             timeout=.5, retries=12, interval=.005, seed=1, event_url='',
             token='', trigger=8, deadline=30):
    if not (1 <= packets <= MAX_PACKETS and 1 <= payload_size <= MAX_PAYLOAD
            and 1 <= window <= 256 and timeout > 0 and retries >= 0
            and interval >= 0 and trigger > 0 and deadline > 0):
        raise ValueError('invalid transfer settings')
    transfer_id = str(uuid.uuid4())
    rng = random.Random(seed)
    payload = base64.b64encode(bytes(rng.randrange(256) for _ in range(payload_size))).decode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect((host, port))  # kernel filters datagrams from other source endpoints
    sock.settimeout(.01)
    pending, acked, failed, records = {}, set(), set(), {}
    rtts = []
    start = time.monotonic()
    start_wall = time.time()
    next_seq = sent = retransmissions = first_timeouts = invalid_acks = 0
    next_send = start
    detection = recovery = None
    notifications = []
    last_notification = -1e9
    try:
        while len(acked) + len(failed) < packets and time.monotonic()-start < deadline:
            now = time.monotonic()
            if next_seq < packets and len(pending) < window and now >= next_send:
                raw = encode(dict(type='data', transfer=transfer_id, seq=next_seq,
                                  total=packets, payload=payload))
                try:
                    sock.send(raw)
                except ConnectionRefusedError:
                    pass  # retained as unacknowledged; bounded retry policy applies
                pending[next_seq] = dict(raw=raw, last=now, first=now, attempts=1)
                records[next_seq] = dict(seq=next_seq, first_sent_s=now-start,
                    ack_s=None, attempts=1, first_timeout=False)
                next_seq += 1
                sent += 1
                next_send = now + interval
            for seq, state in list(pending.items()):
                if now-state['last'] < timeout:
                    continue
                if state['attempts'] == 1:
                    first_timeouts += 1
                    records[seq]['first_timeout'] = True
                if state['attempts'] > retries:
                    failed.add(seq)
                    del pending[seq]
                    continue
                try:
                    sock.send(state['raw'])
                except ConnectionRefusedError:
                    pass
                state['attempts'] += 1
                records[seq]['attempts'] = state['attempts']
                state['last'] = now
                sent += 1
                retransmissions += 1
            if retransmissions >= trigger and detection is None:
                detection = time.monotonic()
            if detection is not None and event_url and now-last_notification >= 1:
                last_notification = now
                try:
                    reply = notify(event_url, token, dict(type='loss', transfer=transfer_id,
                        missing=sorted(pending)[:32], retransmissions=retransmissions))
                    notifications.append(dict(at=time.monotonic()-start, response=reply))
                    if reply.get('path') == 'backup':
                        event_url = ''  # accepted idempotently; do not flood the controller
                except (OSError, ValueError) as error:
                    notifications.append(dict(at=time.monotonic()-start, error=str(error)))
            try:
                raw = sock.recv(MAX_DATAGRAM + 1)
                msg = decode(raw)
                if msg['type'] != 'ack' or msg['transfer'] != transfer_id:
                    invalid_acks += 1
                    continue
                seq = msg['seq']
                if seq in pending:
                    state = pending.pop(seq)
                    acked.add(seq)
                    now = time.monotonic()
                    records[seq]['ack_s'] = now-start
                    if state['attempts'] == 1:  # Karn's rule: exclude ambiguous retransmitted RTTs
                        rtts.append((now-state['first'])*1000)
                    if detection is not None and recovery is None and state['attempts'] > 1:
                        recovery = now
            except (socket.timeout, ConnectionRefusedError):
                continue
            except (ValueError, TypeError, KeyError, UnicodeError):
                invalid_acks += 1
    finally:
        sock.close()
    elapsed = time.monotonic()-start
    rtts.sort()
    return dict(transfer=transfer_id, packets=packets, acked=len(acked),
        failed=packets-len(acked), complete=len(acked)==packets,
        sent_datagrams=sent, retransmissions=retransmissions,
        first_attempt_ack_timeouts=first_timeouts,
        initial_sent=next_seq, unsent=packets-next_seq,
        first_attempt_timeout_ratio=first_timeouts/next_seq if next_seq else None,
        final_unacked_ratio=(packets-len(acked))/packets,
        goodput_bps=len(acked)*payload_size*8/elapsed,
        duration_s=elapsed, invalid_acks=invalid_acks,
        rtt_samples=len(rtts), rtt_p50_ms=rtts[len(rtts)//2] if rtts else None,
        rtt_p95_ms=rtts[min(len(rtts)-1, int(len(rtts)*.95))] if rtts else None,
        detection_s=detection-start if detection else None,
        first_retransmitted_ack_after_detection_s=recovery-detection if recovery else None,
        notifications=notifications, seed=seed, start_wall=start_wall,
        packet_records=list(records.values()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, default=9000)
    for name, default in [('packets', 200), ('payload-size', 256), ('window', 16),
                          ('retries', 12), ('seed', 1), ('trigger', 8)]:
        p.add_argument('--'+name, type=int, default=default)
    for name, default in [('timeout', .5), ('interval', .005), ('deadline', 30)]:
        p.add_argument('--'+name, type=float, default=default)
    p.add_argument('--event-url', default='')
    p.add_argument('--output', required=True)
    args = vars(p.parse_args())
    output = args.pop('output')
    print(json.dumps(dict(ready=True)), flush=True)
    result = transfer(**args, token=os.environ.get('SDN_CONTROL_TOKEN', ''))
    with open(output, 'w') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['complete'] else 2)


if __name__ == '__main__':
    main()
