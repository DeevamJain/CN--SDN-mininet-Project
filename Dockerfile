# syntax=docker/dockerfile:1
FROM ubuntu:22.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends mininet openvswitch-switch python3 python3-venv python3-pip iproute2 iputils-ping iperf3 tcpdump procps ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/sdn
COPY requirements-controller.txt /opt/controller-requirements.txt
RUN --mount=type=secret,id=ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    /opt/sdn/bin/pip install --no-cache-dir -r /opt/controller-requirements.txt
ENV PATH=/opt/sdn/bin:$PATH
WORKDIR /project

FROM runtime AS lab
COPY . /project
ENTRYPOINT ["bash", "/project/scripts/container-entry.sh"]
CMD ["test"]

FROM runtime AS vm-runtime
RUN apt-get update && apt-get install -y --no-install-recommends qemu-system-x86 linux-generic busybox-static cpio && rm -rf /var/lib/apt/lists/*

FROM vm-runtime AS vm
COPY . /project
ENTRYPOINT ["bash", "/project/scripts/container-entry.sh"]
CMD ["test"]
