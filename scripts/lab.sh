#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image="${SDN_IMAGE:-jackfruit-project:ubuntu22}"
if [ "${1:-}" = build ] || [ "${1:-}" = vm-build ]; then
  target=lab
  if [ "$1" = vm-build ]; then target=vm; image="${SDN_VM_IMAGE:-jackfruit-project:vm}"; fi
  build_args=()
  if [ -n "${CODEX_PROXY_CERT:-}" ]; then
    build_args+=(--secret id=ca_bundle,src=/etc/ssl/certs/ca-certificates.crt)
  fi
  docker build --target "$target" "${build_args[@]}" -t "$image" .
elif [ "${1:-}" = vm ]; then
  shift
  docker run --rm --privileged --mount "type=bind,src=$PWD,dst=/project" \
    --entrypoint bash "${SDN_VM_IMAGE:-jackfruit-project:vm}" /project/scripts/vm-lab.sh "${@:-test}"
else
  # Privilege is scoped to a disposable Mininet lab container. No host networking
  # or public service ports are used. Results are written to the mounted checkout.
  docker run --rm --privileged --mount "type=bind,src=$PWD,dst=/project" "$image" "${@:-test}"
fi
