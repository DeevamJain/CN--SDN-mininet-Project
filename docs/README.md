# Project material: start here

Use this guide to study the implementation and prepare the faculty presentation.

## Presentation order

1. Read [the slides and speaker notes](presentation.md) from slide 1 to slide 12.
2. Rehearse [the live demonstration and viva](demo.md) on prepared Ubuntu.
3. Keep [the measured report](results/REPORT.md) and
   [comparison chart](results/comparison.png) open for questions about results.

The presentation includes the problem, objectives, topology, UDP protocol,
reliability, SDN integration, failure handling, experiments, results, demo, and
conclusion. Expand each speaker-notes section on GitHub while rehearsing;
collapse it when showing the slide content.

## Detailed study order

| Order | Material | What you should understand |
|---|---|---|
| 1 | [Root README](../README.md) | Project purpose, installation, and run commands |
| 2 | [Architecture](architecture.md) | Components, exact topology, switch ports, and communication flow |
| 3 | [Protocol](protocol.md) | Sequence numbers, ACKs, retries, duplicates, and controller API |
| 4 | [Evaluation](evaluation.md) | Static baseline, fault scenarios, metrics, and measurement limits |
| 5 | [Validation](validation.md) | Checks actually executed and measured conclusions |
| 6 | [Presentation](presentation.md) | How to explain the project in an ordered way |
| 7 | [Demo and viva](demo.md) | D1/D2 demonstration steps and questions to prepare |

## Code walkthrough order

| Order | Source | Explain this |
|---|---|---|
| 1 | [protocol.py](../jackfruit/protocol.py) | Message format and validation |
| 2 | [receiver.py](../jackfruit/receiver.py) | ACKs, sequence gaps, duplicate suppression, and concurrent transfer state |
| 3 | [sender.py](../jackfruit/sender.py) | Selective-repeat window, timeouts, retries, and loss reporting |
| 4 | [controller.py](../jackfruit/controller.py) | Authentication, forwarding rules, monitoring, and backup selection |
| 5 | [experiment.py](../jackfruit/experiment.py) | Mininet topology, client processes, fault injection, and cleanup |
| 6 | [analyze.py](../jackfruit/analyze.py) | Per-client metrics and before/during/after recovery cohorts |
| 7 | [Tests](../tests/) | Correctness and robustness checks |

## Evidence to show

- [Measured report](results/REPORT.md): readable comparison tables.
- [Chart](results/comparison.png): goodput, final unacknowledged packets, and retransmissions.
- [CSV](results/summary.csv): per-client measurements and cohort sizes.
- [Raw experiment archive](results/raw-mininet-runs.tar.gz): logs, JSON, flow rules, and queue counters.
- [Results audit](../scripts/verify_results.py): verifies actual forwarding and delivery outcomes.

Keep the distinction between measured results and proposed future improvements
clear. Static link-failure runs are expected negative outcomes; the 18 valid
experiments do not mean every static transfer completed successfully.
