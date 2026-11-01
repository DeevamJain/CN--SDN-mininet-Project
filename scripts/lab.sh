#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image="${SDN_IMAGE:-jackfruit-project:ubuntu22}"
if [ "${1:-}" = build ]; then
  build_args=()
  if [ -n "${SDN_CA_BUNDLE:-}" ]; then
    build_args+=(--secret "id=ca_bundle,src=$SDN_CA_BUNDLE")
  fi
  docker build --target lab "${build_args[@]}" -t "$image" .
else
  # Privilege is scoped to a disposable Mininet lab container. No host networking
  # or public service ports are used. Results are written to the mounted checkout.
  docker run --rm --privileged --mount "type=bind,src=$PWD,dst=/project" "$image" "${@:-test}"
fi
