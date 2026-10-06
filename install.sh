#!/usr/bin/env bash
# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
#
# Derived from the Linux Device SDK installer by Meta Platforms, Inc.
# (muse-gadget-sdk, Apache-2.0). Ported from Debian/Ubuntu to Arch Linux
# (Omarchy), with musarchy's security posture and plugin install added.

# Install musarchy: Meta's open-source Muse device agent, Arch-ported, plus
# the musarchy plugin (Hyprland-aware commands).
#
#   curl -fsSL https://raw.githubusercontent.com/ahrazzle/musarchy/main/install.sh -o install.sh
#   less install.sh            # read it first
#   bash install.sh [--sdk-token mgst_...] [--run-as USER] [options]
#
# Installs system packages with pacman, a pinned uv, and musegadget into
# /opt/musegadget; installs the musarchy plugin into the same venv; sets
# BlueZ's GATT MTU for the Android app; installs and starts the musegadget
# service (running the plugin entry point); then opens Bluetooth pairing
# for the Muse app.

set -euo pipefail

UV_VERSION="0.9.9"
UPSTREAM_PIN="b1a3822995a51c0203cd1f3d72c1c656b8c3e620"
PREFIX="/opt/musegadget"
VENV="$PREFIX/venv"
UNIT="/etc/systemd/system/musegadget.service"
DROPIN_DIR="/etc/systemd/system/musegadget.service.d"
STATE_DIR="/var/lib/musegadget"
BLUEZ_CONF="/etc/bluetooth/main.conf"
BLUEZ_DROPIN="/etc/systemd/system/bluetooth.service.d/zz-musegadget.conf"
DEFAULT_SOURCE="git+https://github.com/facebookincubator/muse-gadget-sdk@${UPSTREAM_PIN}#subdirectory=linux"
DEFAULT_PLUGIN_SOURCE="git+https://github.com/ahrazzle/musarchy@main#subdirectory=plugin"
PACMAN_PACKAGES=(bluez bluez-utils python python-dbus python-gobject curl ca-certificates acl)

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: install.sh [options]

  --from SOURCE     Install musegadget from SOURCE: a local linux/ checkout, a
                    wheel, or a pip/uv URL. Default: $DEFAULT_SOURCE
  --plugin-from SRC Install the musarchy plugin from SRC: a local plugin/
                    checkout, a wheel, or a pip/uv URL.
                    Default: $DEFAULT_PLUGIN_SOURCE
  --run-as USER     Account whose permissions your Muse's commands run with.
                    Default: a dedicated 'muse' account, created if missing
                    (no sudo rights, no password login).
  --desktop-user USER
                    Account that owns the graphical desktop session. The
                    desktop commands (desktop.run, desktop.windows,
                    desktop.notify) use this user's session. Default: the
                    user who ran the installer with sudo ($SUDO_USER).
  --sdk-token TOKEN Your mgst_ SDK token from gadgets.muse.ai. Every gadget
                    needs one to pair. Saved, readable only by root, in
                    $STATE_DIR/sdk_token.
  --yes             Don't ask for confirmation.
  --no-pair         Install without opening Bluetooth pairing.
  --uninstall       Remove musarchy. Keeps the device identity and pairing
                    in $STATE_DIR unless --purge is also given.
  -h, --help        Show this help.
EOF
}

# Prompts read the terminal, not stdin, so `curl ... | bash` still works.
ask() {
    local prompt="$1" answer
    if [ "$ASSUME_YES" = 1 ]; then return 0; fi
    if [ ! -r /dev/tty ]; then die "no terminal to confirm on; rerun with --yes"; fi
    printf '%s [Y/n] ' "$prompt" >/dev/tty
    read -r answer </dev/tty || true
    case "$answer" in ""|y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

systemd_running() { [ -d /run/systemd/system ]; }

# --- Checks ------------------------------------------------------------------

check_system() {
    [ "$(uname -s)" = Linux ] || die "musarchy runs on Linux."
    [ -r /etc/os-release ] || die "cannot identify this Linux distribution (/etc/os-release missing)."
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        arch) ;;
        *)
            case " ${ID_LIKE:-} " in
                *" arch "*) warn "$PRETTY_NAME is Arch-based but untested; continuing." ;;
                *) die "$PRETTY_NAME is not supported. musarchy needs Arch Linux (Omarchy)." ;;
            esac ;;
    esac
    command -v pacman >/dev/null || die "pacman not found; musarchy needs an Arch-based system."
    case "$(uname -m)" in
        x86_64|aarch64) ;;
        *) die "unsupported architecture: $(uname -m)" ;;
    esac
    if ! systemd_running; then
        warn "systemd is not running; the service will be installed but not started."
    fi
    if [ -z "$(ls /sys/class/bluetooth 2>/dev/null)" ]; then
        warn "no Bluetooth adapter found. You can install, but pairing with the Muse app needs Bluetooth LE."
    fi
}

ensure_account() {
    if [ -z "$RUN_AS" ]; then RUN_AS="muse"; fi
    if [ "$RUN_AS" = root ]; then
        die "running device commands as root is not supported; pick another account with --run-as."
    fi
    if ! id "$RUN_AS" >/dev/null 2>&1; then
        if [ "$RUN_AS" = "muse" ]; then
            say "Creating the dedicated 'muse' account: no sudo rights, no password login."
            as_root useradd -m -s /bin/bash -c "musarchy device account" muse
            as_root passwd -l muse >/dev/null
        else
            die "account '$RUN_AS' does not exist."
        fi
    fi

    local admin=""
    if as_root sudo -n -l -U "$RUN_AS" 2>/dev/null | grep -qE '\(ALL( : ALL)?\) (NOPASSWD: )?ALL'; then
        admin=" This account has administrator (sudo) rights, so your Muse will be able to do anything on this machine, including reading the device's own credentials."
    fi
    say "Your Muse will be able to run commands on this machine as '$RUN_AS', with that account's permissions.$admin"
    ask "Continue?" || die "cancelled. Rerun with --run-as to choose a different account."
}

# --- Install -----------------------------------------------------------------

install_packages() {
    local missing=() pkg
    for pkg in "${PACMAN_PACKAGES[@]}"; do
        pacman -Qq "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    case "$SOURCE $PLUGIN_SOURCE" in
        *git+*) pacman -Qq git >/dev/null 2>&1 || missing+=(git) ;;
    esac
    if [ "${#missing[@]}" -eq 0 ]; then return; fi
    say "Installing system packages: ${missing[*]}"
    as_root pacman -Sy --noconfirm --needed "${missing[@]}"
}

install_uv() {
    if [ -x "$PREFIX/bin/uv" ] && [ "$("$PREFIX/bin/uv" --version | awk '{print $2}')" = "$UV_VERSION" ]; then
        return
    fi
    say "Installing uv $UV_VERSION"
    as_root mkdir -p "$PREFIX/bin"
    curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" |
        as_root env UV_INSTALL_DIR="$PREFIX/bin" UV_NO_MODIFY_PATH=1 sh -s -- --quiet
}

system_python() {
    local candidate
    for candidate in /usr/bin/python3 /usr/bin/python; do
        if [ -x "$candidate" ]; then printf '%s' "$candidate"; return; fi
    done
    die "no system python found."
}

install_musegadget() {
    local uv="$PREFIX/bin/uv" sys_python
    sys_python="$(system_python)"
    # The system interpreter is required: dbus and gi come from pacman and are
    # built for it.
    if [ ! -x "$VENV/bin/python" ]; then
        say "Creating $VENV"
        as_root "$uv" venv --quiet --python "$sys_python" --system-site-packages "$VENV"
    fi
    say "Installing musegadget from $SOURCE"
    as_root "$uv" pip install --quiet --python "$VENV/bin/python" --no-deps --reinstall "$SOURCE"
    local data
    data="$("$VENV/bin/python" -c 'import musegadget, os; print(os.path.join(os.path.dirname(musegadget.__file__), "data"))')"
    as_root "$uv" pip install --quiet --python "$VENV/bin/python" --require-hashes \
        -r "$data/requirements.lock"
    as_root ln -sf "$VENV/bin/musegadget" /usr/local/bin/musegadget
    DATA_DIR="$data"
}

install_plugin() {
    say "Installing the musarchy plugin from $PLUGIN_SOURCE"
    as_root "$PREFIX/bin/uv" pip install --quiet --python "$VENV/bin/python" \
        --no-deps --reinstall "$PLUGIN_SOURCE"
    "$VENV/bin/python" -c "from musarchy_plugin.wiring import apply; apply()" ||
        die "the musarchy plugin failed to load; aborting before the service is touched."
}

configure_bluez() {
    # The Muse Android app writes (MTU - 3)-byte packets and fails above 512,
    # so keep the negotiated MTU at 256, as the ESP32 firmware does.
    local result
    result="$(as_root python3 - "$BLUEZ_CONF" <<'EOF'
import re, shutil, sys
path = sys.argv[1]
try:
    text = open(path).read()
except FileNotFoundError:
    text = ""
active = re.search(r"^\s*ExchangeMTU\s*=\s*(\d+)\s*$", text, re.M)
if active and int(active.group(1)) <= 256:
    print("unchanged"); sys.exit()
line = "ExchangeMTU = 256"
if active:
    text = text[:active.start()] + line + text[active.end():]
elif re.search(r"^\s*#\s*ExchangeMTU\s*=.*$", text, re.M):
    text = re.sub(r"^\s*#\s*ExchangeMTU\s*=.*$", line, text, count=1, flags=re.M)
elif re.search(r"^\[GATT\]\s*$", text, re.M):
    text = re.sub(r"^\[GATT\]\s*$", "[GATT]\n" + line, text, count=1, flags=re.M)
else:
    text = text.rstrip("\n") + ("\n\n" if text else "") + "[GATT]\n" + line + "\n"
if text != "":
    try:
        shutil.copy2(path, path + ".pre-musegadget")
    except FileNotFoundError:
        pass
open(path, "w").write(text)
print("changed")
EOF
)"
    if [ "$result" = changed ]; then
        say "Set BlueZ ExchangeMTU = 256 (backup: $BLUEZ_CONF.pre-musegadget)"
        if systemd_running; then as_root systemctl restart bluetooth; fi
    fi
    disable_bluez_battery
}

# BlueZ's battery plugin reads a connecting phone's battery level. iPhones
# answer that only over a bonded link, so BlueZ then asks the phone to bond,
# which this device refuses, and iOS pairing can drop. Gadgets never bond.
disable_bluez_battery() {
    systemd_running || return 0
    local unit_text result
    unit_text="$(systemctl cat bluetooth.service 2>/dev/null || true)"
    result="$(as_root python3 - "$BLUEZ_DROPIN" "$unit_text" <<'EOF'
import os, re, sys
path, unit_text = sys.argv[1], sys.argv[2]
# The last non-empty ExecStart= across the unit and its drop-ins is the one
# systemd runs. Leave anything quoted alone rather than risk rewriting it.
lines = re.findall(r"^ExecStart=(.*)$", unit_text, re.M)
command = next((l.strip() for l in reversed(lines) if l.strip()), "")
if not command or any(c in command for c in "\"'\\$%;"):
    print("skipped"); sys.exit()
args = command.split()
for i, arg in enumerate(args):
    inline = arg.startswith("--noplugin=")
    if inline or (arg in ("-P", "--noplugin") and i + 1 < len(args)):
        names = arg.split("=", 1)[1] if inline else args[i + 1]
        if "battery" in names.split(","):
            print("unchanged"); sys.exit()
        names = names + ",battery" if names else "battery"
        if inline:
            args[i] = "--noplugin=" + names
        else:
            args[i + 1] = names
        break
else:
    args.append("--noplugin=battery")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    f.write("# Written by the musarchy installer: never ask phones to bond.\n"
            "[Service]\nExecStart=\nExecStart=" + " ".join(args) + "\n")
print("changed")
EOF
)"
    case "$result" in
        changed)
            say "Turned off BlueZ's battery plugin so phones are never asked to bond ($BLUEZ_DROPIN)"
            as_root systemctl daemon-reload
            as_root systemctl restart bluetooth
            ;;
        skipped) say "Left BlueZ plugins as they are: could not read bluetooth.service's command line." ;;
    esac
}

save_sdk_token() {
    if [ -z "$SDK_TOKEN" ]; then
        if ! as_root test -s "$STATE_DIR/sdk_token"; then
            say "No SDK token yet. Get one at gadgets.muse.ai and rerun with --sdk-token; gadgets without one will stop pairing."
        fi
        return 0
    fi
    say "Saving your SDK token"
    as_root install -d -m 0700 "$STATE_DIR"
    printf '%s\n' "$SDK_TOKEN" | as_root install -m 0600 /dev/stdin "$STATE_DIR/sdk_token"
}

install_service() {
    say "Installing the musarchy service"
    # The unit runs the plugin entry point instead of the stock CLI, so the
    # Hyprland commands are registered before the service connects.
    sed -e "s/@RUN_AS@/$RUN_AS/" \
        -e "s|^ExecStart=.*|ExecStart=$VENV/bin/python -m musarchy_plugin run|" \
        "$DATA_DIR/musegadget.service" | as_root tee "$UNIT" >/dev/null
    install_hardening
    if systemd_running; then
        as_root systemctl daemon-reload
        as_root systemctl enable --now musegadget.service >/dev/null 2>&1
        as_root systemctl restart musegadget.service
    fi
}

install_desktop_access() {
    # The desktop commands need the graphical session, which belongs to the
    # person at the keyboard — usually not the run-as account. Point the
    # plugin at that user's session and let the run-as account reach it.
    local desktop_user="${DESKTOP_USER:-${SUDO_USER:-}}"
    [ -n "$desktop_user" ] || return 0
    if ! id "$desktop_user" >/dev/null 2>&1; then
        warn "desktop user '$desktop_user' does not exist; skipping desktop session setup."
        return 0
    fi
    if [ "$desktop_user" = "$RUN_AS" ]; then
        say "Desktop commands will use $RUN_AS's own session."
        return 0
    fi
    local uid
    uid="$(id -u "$desktop_user")"
    say "Desktop commands will use $desktop_user's graphical session (uid $uid)"
    as_root install -d -m 0755 "$DROPIN_DIR"
    as_root tee "$DROPIN_DIR/20-desktop-user.conf" >/dev/null <<EOF
[Service]
Environment=MUSEGADGET_DESKTOP_USER=$desktop_user
EOF
    # Let the run-as account reach the desktop user's session sockets
    # (Hyprland, Wayland, D-Bus). /run/user is recreated at each login,
    # so a path unit re-applies this whenever the session appears.
    as_root tee /usr/local/bin/musarchy-desktop-acl.sh >/dev/null <<EOF
#!/bin/bash
# Give the musarchy run-as account ($RUN_AS) access to $desktop_user's
# desktop session sockets. Safe to run repeatedly.
R=/run/user/$uid
[ -d "\$R" ] || exit 0
setfacl -m u:$RUN_AS:rx "\$R"
[ -d "\$R/hypr" ] && setfacl -R -m u:$RUN_AS:rwX "\$R/hypr"
[ -S "\$R/bus" ] && setfacl -m u:$RUN_AS:rw "\$R/bus"
for s in "\$R"/wayland-*; do
    [ -S "\$s" ] && setfacl -m u:$RUN_AS:rw "\$s"
done
EOF
    as_root chmod +x /usr/local/bin/musarchy-desktop-acl.sh
    as_root tee /etc/systemd/system/musarchy-desktop-acl.service >/dev/null <<'EOF'
[Unit]
Description=Grant musarchy run-as account access to the desktop session

[Service]
Type=oneshot
ExecStart=/usr/local/bin/musarchy-desktop-acl.sh
EOF
    as_root tee /etc/systemd/system/musarchy-desktop-acl.path >/dev/null <<EOF
[Unit]
Description=Watch for the desktop user's Hyprland session

[Path]
PathExists=/run/user/$uid/hypr
PathChanged=/run/user/$uid/hypr
Unit=musarchy-desktop-acl.service

[Install]
WantedBy=multi-user.target
EOF
    if systemd_running; then
        as_root systemctl daemon-reload
        as_root systemctl enable --now musarchy-desktop-acl.path >/dev/null 2>&1
        as_root /usr/local/bin/musarchy-desktop-acl.sh
    fi
}

install_hardening() {
    # Keep the service process itself tightly sandboxed. Commands still run
    # as the run-as account with that account's normal permissions; these
    # directives only restrict the service process. (Also kept as
    # systemd/10-musarchy-hardening.conf in the repo; keep the two in sync.)
    say "Applying service hardening"
    as_root install -d -m 0755 "$DROPIN_DIR"
    as_root tee "$DROPIN_DIR/10-musarchy-hardening.conf" >/dev/null <<'EOF'
# Musarchy service hardening. Commands run as the run-as account with that
# account's normal permissions; these restrict only the service process.
[Service]
NoNewPrivileges=true
ProtectSystem=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
PrivateTmp=true
EOF
}

pair() {
    if as_root test -s "$STATE_DIR/pairing.json"; then
        say "Already paired; the service will reconnect to your Muse."
        return
    fi
    if [ "$NO_PAIR" = 1 ]; then
        say "Skipping pairing. Run 'sudo musegadget pair' when you're ready."
        return
    fi
    cat <<EOF

Pair with your Muse:
  1. In the Muse app, turn on Settings > Devices > Developer mode.
  2. Add a device and choose the device named below.
  3. When asked for Wi-Fi, pick the network shown; no password is needed.

EOF
    as_root /usr/local/bin/musegadget pair || warn "not paired. Run 'sudo musegadget pair' to try again."
}

summary() {
    echo
    as_root /usr/local/bin/musegadget info
    cat <<EOF

Service:   sudo systemctl status musegadget
Logs:      sudo journalctl -u musegadget -f
Remove:    bash install.sh --uninstall
Plugin:    python -m musarchy_plugin --help  (via $VENV/bin/python)
EOF
}

# --- Uninstall ---------------------------------------------------------------

uninstall() {
    say "Removing musarchy"
    if systemd_running && [ -f "$UNIT" ]; then
        as_root systemctl disable --now musegadget.service >/dev/null 2>&1 || true
    fi
    if systemd_running && [ -f /etc/systemd/system/musarchy-desktop-acl.path ]; then
        as_root systemctl disable --now musarchy-desktop-acl.path >/dev/null 2>&1 || true
    fi
    as_root rm -f "$UNIT" /usr/local/bin/musegadget /usr/local/bin/musarchy-desktop-acl.sh
    as_root rm -f /etc/systemd/system/musarchy-desktop-acl.service /etc/systemd/system/musarchy-desktop-acl.path
    as_root rm -rf "$DROPIN_DIR"
    if systemd_running; then as_root systemctl daemon-reload; fi
    as_root rm -rf "$PREFIX"
    if [ "$PURGE" = 1 ]; then
        as_root rm -rf "$STATE_DIR"
        say "Removed the device identity and pairing too. Remove the device in the Muse app as well."
    else
        say "Kept the device identity and pairing in $STATE_DIR (use --purge to remove them)."
    fi
    if [ -f "$BLUEZ_DROPIN" ]; then
        as_root rm -f "$BLUEZ_DROPIN"
        if systemd_running; then
            as_root systemctl daemon-reload
            as_root systemctl restart bluetooth
        fi
        say "Turned BlueZ's battery plugin back on."
    fi
    if [ -f "$BLUEZ_CONF.pre-musegadget" ]; then
        say "BlueZ settings were left as they are; the original is at $BLUEZ_CONF.pre-musegadget."
    fi
}

main() {
    SOURCE="$DEFAULT_SOURCE" PLUGIN_SOURCE="$DEFAULT_PLUGIN_SOURCE"
    RUN_AS="" SDK_TOKEN="" ASSUME_YES=0 NO_PAIR=0 UNINSTALL=0 PURGE=0
    DESKTOP_USER=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --from) SOURCE="${2:?--from needs a value}"; shift 2 ;;
            --plugin-from) PLUGIN_SOURCE="${2:?--plugin-from needs a value}"; shift 2 ;;
            --run-as) RUN_AS="${2:?--run-as needs a value}"; shift 2 ;;
            --desktop-user) DESKTOP_USER="${2:?--desktop-user needs a value}"; shift 2 ;;
            --sdk-token) SDK_TOKEN="${2:?--sdk-token needs a value}"; shift 2 ;;
            --yes|-y) ASSUME_YES=1; shift ;;
            --no-pair) NO_PAIR=1; shift ;;
            --uninstall) UNINSTALL=1; shift ;;
            --purge) PURGE=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) usage >&2; die "unknown option: $1" ;;
        esac
    done
    if [ "$(id -u)" -ne 0 ]; then
        command -v sudo >/dev/null || die "run this as root, or install sudo."
        sudo true || die "this installer needs sudo."
    fi
    if [ "$UNINSTALL" = 1 ]; then uninstall; return; fi
    if [ -n "$SDK_TOKEN" ] && ! [[ "$SDK_TOKEN" =~ ^mgst_[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$ ]]; then
        die "that SDK token is not valid; copy it again from gadgets.muse.ai."
    fi
    if [ -d "$SOURCE" ]; then SOURCE="$(cd "$SOURCE" && pwd)"; fi
    if [ -d "$PLUGIN_SOURCE" ]; then PLUGIN_SOURCE="$(cd "$PLUGIN_SOURCE" && pwd)"; fi

    check_system
    ensure_account
    install_packages
    install_uv
    install_musegadget
    install_plugin
    configure_bluez
    save_sdk_token
    install_service
    install_desktop_access
    pair
    summary
}

# Everything runs from main, so a truncated download never runs a partial script.
main "$@"
