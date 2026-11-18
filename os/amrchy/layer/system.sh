# bashOS on Amrchy: the layer's system setup (amrchy/docs/layers.md), sourced as root in the
# installed target with no network. It puts the bashOS tree this layer carries at /opt/bashos
# (root-owned, as `bashos os install` keeps it), the machine's settings in /etc/bashos, and arms
# bashos-firstboot, which finishes the install once the machine is online.
#
# os/iso/build.sh copies this directory into the Amrchy build as install/layers/bashos/, with
# payload/ (the bashOS tree) and build-info beside it. BASHOS_LAYER_ROOT puts every path under
# a directory instead of / (the offline tests).
root=${BASHOS_LAYER_ROOT:-}
layer=$root/opt/bashos

if [[ -e $root/var/lib/bashos/provisioned ]]; then
  # A finished machine updates itself (bashos os update); a framework upgrade leaves it be.
  echo "bashOS is installed; bashos os update keeps it current"
elif [[ -d $layer/.git ]]; then
  echo "/opt/bashos is a checkout; left alone"
else
  rm -rf "$layer.new"
  mkdir -p "$root/opt"
  cp -a "$LAYER_DIR/payload" "$layer.new"
  (( EUID != 0 )) || chown -R root:root "$layer.new"
  chmod 0755 "$layer.new"
  rm -rf "$layer"
  mv "$layer.new" "$layer"

  install -d -m 0755 "$root/etc/bashos" "$root/var/lib/bashos" "$root/usr/local/sbin" \
    "$root/usr/local/lib/systemd/system"
  [[ -f $root/etc/bashos/os.conf ]] || install -m 0644 "$layer/os/config/os.conf" "$root/etc/bashos/os.conf"
  install -m 0644 "$LAYER_DIR/build-info" "$root/etc/bashos/build-info"
  install -m 0644 "$layer/os/systemd/system/bashos-firstboot.service" \
    "$root/usr/local/lib/systemd/system/bashos-firstboot.service"
  ln -sfn /opt/bashos/os/bin/bashos-firstboot "$root/usr/local/sbin/bashos-firstboot"

  # The person the installer created; a deferred install names nobody, and first boot waits
  # for the first user instead.
  if [[ -n ${OMARCHY_INSTALL_USER:-} ]]; then
    printf 'BASHOS_USER=%s\n' "$OMARCHY_INSTALL_USER" >"$root/etc/bashos/firstboot.env"
  fi
  touch "$root/var/lib/bashos/firstboot-pending"
  systemctl ${root:+--root="$root"} enable bashos-firstboot.service
  echo "bashOS $(sed -n 's/^commit=//p' "$root/etc/bashos/build-info" | cut -c1-12) at /opt/bashos; bashos-firstboot finishes it online"
fi
