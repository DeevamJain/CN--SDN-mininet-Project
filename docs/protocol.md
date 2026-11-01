# UDP protocol and controller API

Datagrams are UTF-8 JSON, version 1, at most 1400 bytes. Synthetic payloads are
1–512 bytes encoded as base64. Sequence numbers are zero-based; a transfer has
1–100000 packets. Integers are validated strictly (JSON booleans are rejected).

Data example:

```json
{"v":1,"type":"data","transfer":"0e5d6d29-0dc1-4349-bc2a-191541bc365c","seq":0,"total":200,"payload":"aGVsbG8="}
```

ACK example:

```json
{"v":1,"type":"ack","transfer":"0e5d6d29-0dc1-4349-bc2a-191541bc365c","seq":0}
```

Receiver state is keyed by source IP/port plus transfer UUID. Different clients
cannot acknowledge one another's transfers. A connected UDP sender socket
filters ACK source endpoints; UUID and sequence membership are checked too.
The receiver remembers sequence IDs for 120 seconds since last reception,
including completed transfers, so a lost final ACK can be recovered by retry.
At most 256 sessions are retained; new sessions beyond this bound are rejected
until expiry. A global 200000-sequence budget also bounds receiver memory;
new sequence IDs over the budget are rejected without ACK. Each sender has a 16-packet window and 12 retries per packet by
default, with a conservative 500 ms ACK timeout and an eight-retransmission
reporting threshold, plus a whole-transfer deadline. Experiments use 20 retries.

Out-of-order arrival creates a gap observation, not proof of permanent loss.
Later arrivals close gaps. Duplicate sequence IDs are not delivered twice but
are ACKed again. `gap_events` counts holes observed when the highest sequence
advances; `missing` counts final undelivered unique sequences. Missing ACKs can
mean data loss, ACK loss, delay, or a failed receiver, so reports are deliberately
called timeout indicators. The application does not claim TCP-grade congestion
control: use only in the controlled lab.

The controller listens on TCP 6653 for OpenFlow and HTTP 8080 for control.
The runner generates a fresh token of 48 hexadecimal characters and injects it
through `SDN_CONTROL_TOKEN`; tokens are not written to results. No credentials
are committed. Every HTTP endpoint requires `Authorization: Bearer <token>`.
The lab control link is trusted; use TLS if deploying outside this isolated lab.

`GET /status` returns mode, chosen path, connected switches, down ports, port
counters, recent events and barrier progress.

`POST /event` accepts at most 4096 body bytes:

```json
{"type":"loss","transfer":"0e5d6d29-0dc1-4349-bc2a-191541bc365c","missing":[3,7],"retransmissions":3}
```

The UUID must parse, missing IDs must contain 1–32 valid integers, and the
retransmission count must be at least three. Invalid input returns 400, missing
or incorrect authentication 401, and unknown routes 404. Reports are idempotent:
once backup is selected they do not trigger repeated updates. Static mode
accepts valid telemetry but never changes its primary route. Clients retry
failed API requests at most once per second until their transfer deadline.
