"""Versioned, size-limited JSON datagrams; one sequence number per payload."""
import base64
import json
import uuid

MAX_DATAGRAM = 1400
MAX_PAYLOAD = 512
MAX_PACKETS = 100000


def encode(message):
    raw = json.dumps(dict(v=1, **message), separators=(',', ':')).encode()
    if len(raw) > MAX_DATAGRAM:
        raise ValueError('datagram too large')
    return raw


def decode(raw):
    if len(raw) > MAX_DATAGRAM:
        raise ValueError('datagram too large')
    msg = json.loads(raw)
    if not isinstance(msg, dict) or msg.get('v') != 1:
        raise ValueError('unsupported message')
    if not isinstance(msg.get('transfer'), str):
        raise ValueError('invalid transfer ID')
    uuid.UUID(msg['transfer'])
    if msg.get('type') not in ('data', 'ack'):
        raise ValueError('unknown message type')
    if type(msg['seq']) is not int or not 0 <= msg['seq'] < MAX_PACKETS:
        raise ValueError('invalid sequence')
    if msg['type'] == 'data':
        if type(msg['total']) is not int or not 1 <= msg['total'] <= MAX_PACKETS:
            raise ValueError('invalid total')
        if msg['seq'] >= msg['total']:
            raise ValueError('sequence outside transfer')
        payload = base64.b64decode(msg['payload'], validate=True)
        if not 1 <= len(payload) <= MAX_PAYLOAD:
            raise ValueError('invalid payload size')
    return msg
