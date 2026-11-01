# Architecture and flow

```mermaid
flowchart LR
  h1[Client h1: 10.0.0.1] --- s1
  h3[Client h3: 10.0.0.3] --- s1
  s1 ---|primary| s2
  s2 --- s4
  s1 ---|backup| s3
  s3 --- s4
  s4 --- h2[Receiver h2: 10.0.0.2:9000]
  h1 -. loss event on dedicated link .-> c[OS-Ken controller]
  h3 -. loss event on dedicated link .-> c
  c -. OpenFlow 1.3 .-> s1
  c -. OpenFlow 1.3 .-> s2
  c -. OpenFlow 1.3 .-> s3
  c -. OpenFlow 1.3 .-> s4
```

| Switch | Port | Connected endpoint |
|---|---:|---|
| s1 | 1 | h1 |
| s1 | 2 | h3 |
| s1 | 3 | s2 port 1 |
| s1 | 4 | s3 port 1 |
| s2 | 2 | s4 port 1 |
| s3 | 2 | s4 port 2 |
| s4 | 3 | h2 |

Hosts use MAC suffixes 01, 02, 03 matching their IP suffixes. Switch DPIDs are
1–4. Management addresses are h1 `10.255.1.2/30` to controller
`10.255.1.1`, and h3 `10.255.2.2/30` to controller `10.255.2.1`.
These direct links are outside the impaired data plane; this is an explicit
out-of-band management assumption.

1. Each sender opens a UDP socket and assigns a unique transfer UUID.
2. It sends up to 16 outstanding sequence-numbered data messages.
3. The receiver validates messages, records unseen sequences, and ACKs every
   valid reception, including duplicates.
4. A missing ACK beyond the retransmission timeout causes a bounded retry.
5. Eight retransmissions trigger a loss report over the management link.
6. The controller verifies the bearer token, schema, switch availability, and
   backup port health, then replaces exact destination forwarding rules.
7. OpenFlow barrier replies record completion across all four datapaths.
8. UDP retransmission recovers outstanding packets using the backup path.

Switch port-down events can trigger the same route change without waiting for
the application's timeout. A 1-second port-description poll provides a secondary
health check. Both directions change together; controller updates are not
cross-switch atomic, so a brief transition can lose additional packets.

Only one switch-over is allowed per experiment. A failed backup is never
intentionally selected when its port is known down. Failure of the receiver
cannot be repaired by routing; clients terminate after retry/deadline limits.
