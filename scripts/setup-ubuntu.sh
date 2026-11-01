#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(id -u)" -eq 0 ]; then privilege=(); else privilege=(sudo); fi
"${privilege[@]}" apt-get update
"${privilege[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y mininet openvswitch-switch python3-venv iperf3 tcpdump
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-controller.txt
echo 'Activate .venv, start Open vSwitch, then run experiments as root with .venv/bin/python.'
