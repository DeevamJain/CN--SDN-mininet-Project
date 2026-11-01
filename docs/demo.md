# D1/D2 demonstration and viva

## D1 (15 marks)

1. Explain the loss-recovery problem, four-switch topology and out-of-band
   controller link using the architecture diagram.
2. Show the UDP message schema, sequence-state sets, window, ACK and retry loop.
3. Run `bash scripts/lab.sh test`; identify concurrency, data/ACK loss,
   reordering, duplicates, malformed input and retry-exhaustion tests.
4. Run the normal dynamic Mininet demo and show all three hosts can communicate.
5. Show priority-100 destination flows and two completed client reports.
6. Run the dynamic loss demo and show `application_loss` and barrier completion
   in `controller-events.jsonl`, then the sender's retransmission counts.

## D2 (25 marks)

1. Run the full 18-experiment matrix using a fresh output directory.
2. Compare static and dynamic under loss: both use UDP retransmission, but only
   dynamic can leave the impaired link.
3. Show primary-link failure. Dynamic should select backup; static should retain
   the broken primary and report failed packets after bounded retries.
4. Explain unavailable-backup rejection, authentication, deduplication, session
   expiry and receiver-unavailable behavior.
5. Present generated CSV/report, cohort sizes, goodput, ACK timeout indicators,
   unique reception, queue drops, and recovery timing. Explain measurement limits.
6. Show source, README, dependency pins, topology, tests, logs and reproduction
   commands in the GitHub repository. No staged or invented benchmark numbers.

## Questions to prepare

- Why use UDP, and what reliability does the application add?
- How do you distinguish missing data from a lost ACK or delayed packet?
- Why ACK duplicates, and why retain completed receiver state?
- What is selective repeat, and why bound both retries and transfer duration?
- What is the role of static ARP and exact MAC rules in avoiding a diamond loop?
- Why does changing only the forward route risk ACK-path failure?
- How does an application loss event reach the controller during data-plane loss?
- What do barriers guarantee, and why are updates not atomic across switches?
- Why can a receiver outage not be fixed by routing?
- Why is first-attempt ACK timeout ratio different from physical packet loss?
- How do static and dynamic runs control other variables?
- What remains out of scope? Adaptive congestion control, encrypted transport,
  authenticated data payloads, durable file delivery, and automatic failback.

## Troubleshooting

Missing `ovs_datapath`, unknown qdisc kind, or absent virtual interfaces indicate
kernel support problems. Use the Ubuntu VM recommended in the installation
guide; a container image cannot replace its host kernel. If controller startup
fails, inspect controller.log before running clients. A process or listening port
alone does not prove forwarding works: require initial ping and actual UDP
delivery. Do not disable TLS or package signature verification for installation.
