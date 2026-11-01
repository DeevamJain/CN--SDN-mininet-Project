#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="${1:-results/mininet-$(date -u +%Y%m%dT%H%M%SZ)}"
python_bin="${SDN_PYTHON:-/opt/sdn/bin/python}"
for trial in 1 2 3; do
  for scenario in normal loss link_failure; do
    for mode in static dynamic; do
      "$python_bin" -m jackfruit.experiment --mode "$mode" --scenario "$scenario" \
        --seed "$trial" --output "$output/$scenario-$mode-$trial"
    done
  done
done
"$python_bin" -m jackfruit.analyze "$output"
"$python_bin" scripts/verify_results.py "$output"
