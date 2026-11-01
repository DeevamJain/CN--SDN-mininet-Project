# Measured Mininet results

Timeout ratios are missing-ACK indicators, not direct wire-loss rates.

| Scenario | Mode | Runs | Mean goodput (bit/s) | Mean final unacked ratio |
|---|---|---:|---:|---:|
| link_failure | dynamic | 3 | 165458.4 | 0.0000 |
| link_failure | static | 3 | 9417.8 | 0.7700 |
| loss | dynamic | 3 | 174240.2 | 0.0000 |
| loss | static | 3 | 97770.8 | 0.0000 |
| normal | dynamic | 3 | 190635.1 | 0.0000 |
| normal | static | 3 | 190573.2 | 0.0000 |

| Scenario | Mode | Mean retransmissions/client | Mean initial timeout ratio | Mean fault-to-barriers (s) |
|---|---|---:|---:|---:|
| link_failure | dynamic | 16.00 | 0.0400 | 0.3936 |
| link_failure | static | 573.67 | 0.2584 | — |
| loss | dynamic | 23.50 | 0.0471 | 1.0393 |
| loss | static | 165.83 | 0.2708 | — |
| normal | dynamic | 0.00 | 0.0000 | — |
| normal | static | 0.00 | 0.0000 | — |

ACK-timeout cohorts (packet counts and weighted ratios):

| Scenario | Mode | Before fault: n / ratio | During recovery: n / ratio | After barriers: n / ratio |
|---|---|---:|---:|---:|
| link_failure | dynamic | 498 / 0.0000 | 138 / 0.6957 | 1764 / 0.0000 |
| link_failure | static | 516 / 0.0000 | 228 / 0.8421 | 0 / — |
| loss | dynamic | 548 / 0.0000 | 371 / 0.3046 | 1481 / 0.0000 |
| loss | static | 489 / 0.0000 | 1911 / 0.3401 | 0 / — |
| normal | dynamic | 522 / 0.0000 | 1878 / 0.0000 | 0 / — |
| normal | static | 492 / 0.0000 | 1908 / 0.0000 | 0 / — |
