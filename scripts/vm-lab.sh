#!/usr/bin/env bash
# Optional software-emulated guest for cloud kernels missing Mininet modules.
# Run INSIDE the dedicated privileged Ubuntu lab container, never on a shared host.
set -euo pipefail
cd /project
kernel="${SDN_GUEST_KERNEL:-$(basename "$(readlink -f /boot/vmlinuz)" | sed 's/^vmlinuz-//')}"
test -f "/boot/vmlinuz-$kernel"
command -v qemu-system-x86_64 >/dev/null
test -x /bin/busybox
staging="$(mktemp -d /tmp/jackfruit-initrd.XXXXXX)"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging"/{bin,dev,proc,sys,newroot}
cp /bin/busybox "$staging/bin/busybox"
for app in sh mount mkdir switch_root insmod sleep; do ln -s busybox "$staging/bin/$app"; done
cat > "$staging/init" <<'INIT'
#!/bin/sh
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
INIT
for module in virtio_pci 9pnet_virtio 9p; do
  while read -r instruction module_path remainder; do
    [ "$instruction" = insmod ] || continue
    mkdir -p "$staging/$(dirname "$module_path")"
    cp "$module_path" "$staging/$module_path"
    printf 'insmod %s || true\n' "$module_path" >> "$staging/init"
  done < <(modprobe --set-version "$kernel" --show-depends "$module")
done
cat >> "$staging/init" <<'INIT'
mount -t 9p -o trans=virtio,version=9p2000.L,cache=loose,msize=262144 rootfs /newroot || exec sh
exec switch_root /newroot /bin/bash /project/scripts/vm-init.sh
INIT
chmod +x "$staging/init"
(cd "$staging" && find . -print0 | cpio --null -o --format=newc 2>/dev/null | gzip -1 > /tmp/jackfruit-initrd.gz)
printf '#!/bin/bash\ncd /project\nbash scripts/container-entry.sh' > /tmp/jackfruit-vm-job.sh
printf ' %q' "${@:-test}" >> /tmp/jackfruit-vm-job.sh
printf '\n' >> /tmp/jackfruit-vm-job.sh
mkdir -p /project/results
rm -f /project/results/guest-exit-status.txt
qemu-system-x86_64 -accel tcg,thread=multi -m 1536 -smp 2 -nographic -no-reboot \
  -kernel "/boot/vmlinuz-$kernel" -initrd /tmp/jackfruit-initrd.gz \
  -append 'console=ttyS0 panic=-1 init=/init' -nic none \
  -fsdev local,id=shared,path=/,security_model=none,multidevs=remap \
  -device virtio-9p-pci,fsdev=shared,mount_tag=rootfs
test -f /project/results/guest-exit-status.txt
exit "$(cat /project/results/guest-exit-status.txt)"
