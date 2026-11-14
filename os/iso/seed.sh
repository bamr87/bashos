#!/usr/bin/env bash
# os/iso/seed.sh — the `cidata` drive that installs the bashOS ISO unattended: the configurator's
# own answer files (Omarchy's autoinstall, amrchy/manual/51-unattended-installs.md), written for one
# machine. Attach it beside the ISO (a second stick, or a VM's second drive) and the installer
# skips its questions, erases the named disk, installs, and reboots into bashOS; the first boot
# then finishes the runtime online (bashos-firstboot).
#
# The files follow the configurator of the omarchy-iso commit os/iso/iso.conf pins. The disk is
# erased whole and is not encrypted: an encrypted unattended install would carry its passphrase
# in clear on this drive and still stop at the first boot to ask for it, so encryption is the
# interactive installer's.
set -Eeuo pipefail

OS_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib.sh
source "$OS_SRC/os/lib.sh"

usage() {
  cat <<'EOF'
usage: bashos os iso seed --user NAME --disk DEV --disk-bytes N [options]

  --user NAME           the machine's person: created by the installer, with sudo
  --disk DEV            the disk the installer ERASES and installs to, e.g. /dev/nvme0n1
  --disk-bytes N        that disk's exact size: `lsblk -bdno SIZE DEV` on the machine
                        (the one-os home base boots it with nothing installed)
  --hostname NAME       default: bashos
  --timezone ZONE       default: UTC
  --keyboard LAYOUT     default: us
  --keys FILE           ssh public keys for the user, one per line; sshd is enabled and
                        opened for them (default: ~/.ssh/id_ed25519.pub when it exists)
  --password-hash HASH  the user's password as a crypt(5) hash (openssl passwd -6); default:
                        asked twice on this terminal and hashed here
  --full-name NAME      git's user.name;  --email ADDR  git's user.email
  --out DIR             default: build/iso/cidata (and DIR.iso, labelled cidata)
  -h, --help
EOF
}

die_usage() {
  printf 'bashos os iso seed: %s\n\n' "$1" >&2
  usage >&2
  exit 2
}

# The configurator's sizes: a 1 MiB gap, a 2 GiB ESP, the rest btrfs, less the GPT backup.
MIB=$((1024 * 1024))
GIB=$((1024 * MIB))

# configuration DISK BYTES HOSTNAME TIMEZONE KEYBOARD — user_configuration.json.
configuration() {
  local boot_start=$MIB boot_size=$((2 * GIB))
  local main_start=$((boot_start + boot_size))
  local main_size=$(($2 - main_start - MIB))
  jq -n --arg disk "$1" --arg host "$3" --arg tz "$4" --arg kb "$5" \
    --argjson boot_start "$boot_start" --argjson boot_size "$boot_size" \
    --argjson main_start "$main_start" --argjson main_size "$main_size" '
    def bytes($v): { "sector_size": { "unit": "B", "value": 512 }, "unit": "B", "value": $v };
    {
      "app_config": null,
      "archinstall-language": "English",
      "auth_config": {},
      "audio_config": { "audio": "pipewire" },
      "bootloader_config": { "bootloader": "Limine", "uki": false, "removable": false },
      "custom_commands": [],
      "omarchy_install": {
        "mode": "full_disk",
        "defer_provisioning": false,
        "target_mount": "/mnt",
        "boot": { "esp_mount": "/boot", "esp_path": "/EFI/limine", "efi_binary": "limine_x64.efi",
                  "enable_fallback": true },
        "storage": { "kernel": "linux-omarchy" }
      },
      "disk_config": {
        "config_type": "default_layout",
        "device_modifications": [ {
          "device": $disk,
          "partitions": [
            { "btrfs": [], "dev_path": null, "flags": ["boot", "esp"], "fs_type": "fat32",
              "mount_options": [], "mountpoint": "/boot",
              "obj_id": "ea21d3f2-82bb-49cc-ab5d-6f81ae94e18d",
              "size": bytes($boot_size), "start": bytes($boot_start),
              "status": "create", "type": "primary" },
            { "btrfs": [ { "mountpoint": "/", "name": "@" }, { "mountpoint": "/home", "name": "@home" },
                         { "mountpoint": "/var/log", "name": "@log" },
                         { "mountpoint": "/var/cache/pacman/pkg", "name": "@pkg" } ],
              "dev_path": null, "flags": [], "fs_type": "btrfs", "mount_options": ["compress=zstd"],
              "mountpoint": null, "obj_id": "8c2c2b92-1070-455d-b76a-56263bab24aa",
              "size": bytes($main_size), "start": bytes($main_start),
              "status": "create", "type": "primary" }
          ],
          "wipe": true
        } ]
      },
      "hostname": $host,
      "kernels": ["linux-omarchy"],
      "network_config": { "type": "iso" },
      "ntp": true,
      "parallel_downloads": 8,
      "script": null,
      "services": [],
      "swap": true,
      "timezone": $tz,
      "locale_config": { "kb_layout": $kb, "sys_enc": "UTF-8", "sys_lang": "en_US.UTF-8" },
      "mirror_config": {
        "custom_repositories": [],
        "custom_servers": [
          { "url": "https://mirror.omarchy.org/$repo/os/$arch" },
          { "url": "https://mirror.rackspace.com/archlinux/$repo/os/$arch" },
          { "url": "https://geo.mirror.pkgbuild.com/$repo/os/$arch" }
        ],
        "mirror_regions": {},
        "optional_repositories": []
      },
      "packages": ["base-devel", "git", "omarchy-keyring", "omarchy-settings-dev", "omarchy-dev"],
      "profile_config": { "gfx_driver": null, "greeter": null, "profile": {} },
      "version": "3.0.9"
    }'
}

# credentials USER HASH — user_credentials.json: the user, with sudo; root gets the same hash.
credentials() {
  jq -n --arg user "$1" --arg hash "$2" '{
    "root_enc_password": $hash,
    "users": [ { "enc_password": $hash, "groups": [], "sudo": true, "username": $user } ]
  }'
}

ask_hash() {
  local pw1 pw2
  [[ -t 0 ]] || die_usage "no --password-hash and no terminal to ask on"
  while :; do
    read -rsp "password for $1: " pw1; echo >&2
    read -rsp "again: " pw2; echo >&2
    [[ -n $pw1 && $pw1 == "$pw2" ]] && break
    echo "  the two differ or are empty — again" >&2
  done
  openssl passwd -6 -stdin <<<"$pw1"
}

# pack DIR — DIR.iso, an ISO 9660 volume labelled cidata (any filesystem with the label works).
pack() {
  local dir=$1 iso="$1.iso"
  rm -f "$iso"
  if os_has xorriso; then
    xorriso -as mkisofs -quiet -V cidata -J -r -o "$iso" "$dir"
  elif os_has genisoimage; then
    genisoimage -quiet -V cidata -J -r -o "$iso" "$dir"
  elif os_has hdiutil; then
    hdiutil makehybrid -quiet -iso -joliet -default-volume-name cidata -o "$iso" "$dir"
  else
    os_warn "no xorriso, genisoimage or hdiutil: copy $dir onto any drive labelled cidata"
    return 0
  fi
  os_ok "$iso (volume cidata)"
}

main() {
  local user="" disk="" bytes="" host=bashos tz=UTC kb=us keys="" hash="" name="" email=""
  local out=$OS_SRC/build/iso/cidata
  [[ -f $HOME/.ssh/id_ed25519.pub ]] && keys=$HOME/.ssh/id_ed25519.pub
  while (($#)); do
    case $1 in
      --user) user=${2:-}; shift ;;
      --disk) disk=${2:-}; shift ;;
      --disk-bytes) bytes=${2:-}; shift ;;
      --hostname) host=${2:-}; shift ;;
      --timezone) tz=${2:-}; shift ;;
      --keyboard) kb=${2:-}; shift ;;
      --keys) keys=${2:-}; shift ;;
      --password-hash) hash=${2:-}; shift ;;
      --full-name) name=${2:-}; shift ;;
      --email) email=${2:-}; shift ;;
      --out) out=${2:-}; shift ;;
      -h | --help) usage; return 0 ;;
      *) die_usage "unknown option $1" ;;
    esac
    shift
  done
  os_has jq || os_die "jq is needed to write the answer files"
  [[ $user =~ ^[a-z_][a-z0-9_-]{0,31}$ && $user != root ]] || die_usage "--user: a lower-case login name, not root"
  [[ $disk == /dev/* ]] || die_usage "--disk: the device the installer erases, e.g. /dev/nvme0n1"
  [[ $bytes =~ ^[0-9]+$ ]] && ((bytes >= 16 * GIB)) || die_usage "--disk-bytes: the disk's size in bytes (16 GiB at least)"
  ((bytes % 512 == 0)) || die_usage "--disk-bytes: $bytes is not a whole number of 512-byte sectors"
  [[ $host =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || die_usage "--hostname: letters, digits and hyphens"
  if [[ -n $keys ]]; then
    [[ -r $keys ]] || die_usage "--keys: cannot read $keys"
    grep -Eq '^(ssh-|ecdsa-|sk-)' "$keys" || die_usage "--keys: $keys holds no ssh public key"
    grep -q 'PRIVATE KEY' "$keys" && die_usage "--keys: $keys is a private key"
  fi
  [[ -n $hash ]] || hash=$(ask_hash "$user")
  [[ $hash == \$* ]] || die_usage "--password-hash: a crypt(5) hash such as \$6\$…, never the password"

  rm -rf "$out"
  mkdir -p "$out"
  configuration "$disk" "$bytes" "$host" "$tz" "$kb" >"$out/user_configuration.json"
  (umask 077 && credentials "$user" "$hash" >"$out/user_credentials.json")
  printf 'false\n' >"$out/user_encrypt_installation.txt"
  [[ -n $keys ]] && grep -E '^(ssh-|ecdsa-|sk-)' "$keys" >"$out/authorized_keys"
  [[ -n $name ]] && printf '%s\n' "$name" >"$out/user_full_name.txt"
  [[ -n $email ]] && printf '%s\n' "$email" >"$out/user_email_address.txt"
  os_ok "$out: $user@$host, erases $disk ($((bytes / GIB)) GiB)${keys:+, ssh keys from $keys}"
  pack "$out"
  [[ -n $keys ]] || os_warn "no ssh keys: the machine will not answer ssh until you add one"
}

main "$@"
