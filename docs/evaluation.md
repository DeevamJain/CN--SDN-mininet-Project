# Evaluation and reproducibility

Required runs are normal, 35% primary forward loss, and primary link failure,
each in static and dynamic mode, repeated three times. Both policies use the
same reliable UDP application, packet count, window, payload size, retry limits,
two concurrent clients, and physical topology. Only controller policy changes.
This isolates the benefit of rerouting from the benefit of retransmission.

The primary and backup have equal link bandwidth. Each path crosses two
host-to-switch links plus two inter-switch links (four links total). Each link adds 5 ms
one-way delay. Loss is injected on s2's egress toward s4 after 0.8 seconds.
Replacing that interface's root queue changes its shaping configuration in both
comparison modes equally. `netem` randomness is not seed-controlled on this
Ubuntu version; reported seeds control application payload generation only.
Use repetitions and raw traces rather than claiming identical loss traces.

| Metric | Definition |
|---|---|
| Unique delivery | Receiver's unique sequence count / total |
| Final unacked ratio | Sender's unacknowledged sequences / total; may include ACK loss |
| First-attempt timeout ratio | Packets whose initial ACK missed timeout / initial packets sent (unsent packets are separate) |
| Retransmissions | Additional send attempts after initial sends |
| Goodput | ACK-confirmed unique payload bits / sender elapsed seconds |
| RTT p50/p95 | Non-retransmitted packet ACK RTT samples; excludes ambiguous retries |
| Controller update time | Rule-request to all tracked barrier replies |
| Fault-to-barriers | Fault injection to completed backup rule updates |
| Application recovery proxy | Detection to first ACK for a retransmitted packet |
| Queue drops | `tc -s qdisc` counters from the impaired egress |

Application recovery is a proxy, not proof of sustained throughput or a one-way
packet-delivery measurement. Report it beside controller barriers and goodput.
Receiver datagram totals and final unique counts are saved separately from ACK
statistics. The CSV's observed forward datagram deficit is attempted sends
minus receiver datagrams; it includes local send errors and packets left in
flight at shutdown, so it is not labeled a physical loss rate. OpenFlow dropped-packet counters do not necessarily include Linux
qdisc drops, so queue counters are captured directly.

`summary.csv` includes first-attempt timeout ratios for packets first sent
before the fault, during recovery, and after barrier completion. Empty cohorts
are blank, not zero; static runs have no after-recovery cohort. For loss runs,
compare dynamic after-recovery to static during-impairment indicators and show
cohort sizes. A before/after timeout decrease is not an exact wire-loss rate.

Each result directory contains client JSON and logs, receiver JSON, controller
events and logs, plus `experiment.json` with scenario, policy, timestamps,
exit codes, flow dumps, controller status and qdisc statistics. Never reuse an
output directory. The analyzer excludes invalid setup runs and refuses to
generate a report if no valid runs exist. It preserves incomplete-delivery
outcomes; static link failure is an expected negative comparison.

Record VM CPU/RAM, guest kernel, Docker version and contention with results.
Software-emulated VM throughput includes emulation overhead; compare policies
within that VM and avoid treating its absolute throughput as real hardware
performance. See `docs/validation.md` for evidence actually obtained.

The final comparison uses a 500 ms ACK timeout and an eight-retransmission
notification threshold in both policies. Preliminary 150 ms timeout trials
produced false alarms under QEMU scheduling; those invalid runs are excluded.
The final normal-traffic runs must retain the primary path, or the runner
rejects the experiment. These conservative fixed parameters trade faster
detection for fewer scheduling-related false alarms.

To export the measured comparison as a standalone PNG and PDF, install the
optional plotting tool in a separate virtual environment (not the controller
runtime), then run:

```sh
python3 -m venv .plot-venv
.plot-venv/bin/pip install matplotlib==3.10.8
.plot-venv/bin/python scripts/plot_results.py results/comparison/summary.csv
```

Each bar averages trial means; error bars show the sample standard deviation
across trials. The two clients within one trial are not treated as independent
trials. This plotting dependency is optional and does not affect the network.
