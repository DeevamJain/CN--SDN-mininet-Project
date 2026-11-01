#!/bin/bash
# PID 1 in the isolated guest. Mounts affect only the guest namespace.
export PATH=/opt/sdn/bin:/usr/sbin:/usr/bin:/sbin:/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
cp /tmp/jackfruit-vm-job.sh /run/jackfruit-vm-job.sh
mount -t tmpfs tmpfs /tmp
mkdir -p /dev/pts /run/openvswitch
mount -t devpts devpts /dev/pts
hostname jackfruit-guest
ip link set lo up
for module in openvswitch veth sch_htb sch_netem; do modprobe "$module" || exit 1; done
mkdir -p /project/results
uname -a > /project/results/guest-kernel.txt
bash /run/jackfruit-vm-job.sh
outcome=$?
echo "$outcome" > /project/results/guest-exit-status.txt
sync
echo "JACKFRUIT_GUEST_EXIT=$outcome"
/bin/busybox poweroff -f
