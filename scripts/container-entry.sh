#!/usr/bin/env bash
set -euo pipefail
cd /project
action="${1:-test}"
shift || true
if [ "$action" = test ]; then
  exec /opt/sdn/bin/python -m unittest discover -s tests -v
fi
mkdir -p /var/run/openvswitch
ovsdb-tool create /var/run/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
ovsdb-server /var/run/openvswitch/conf.db --remote=punix:/var/run/openvswitch/db.sock --pidfile --detach
ovs-vsctl --no-wait init
ovs-vswitchd --pidfile --detach
export PATH="/opt/sdn/bin:$PATH"
case "$action" in
  demo)
    mode="${1:-dynamic}"; scenario="${2:-loss}"
    output="${3:-results/demo-$(date -u +%Y%m%dT%H%M%SZ)}"
    exec python -m jackfruit.experiment --mode "$mode" --scenario "$scenario" --output "$output"
    ;;
  matrix) exec bash scripts/matrix.sh "$@" ;;
  shell) exec bash ;;
  *) echo "Usage: test | demo [static|dynamic] [normal|loss|link_failure] [output] | matrix [output] | shell" >&2; exit 2 ;;
esac
