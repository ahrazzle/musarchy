# Architecture

Musarchy is a polymerization of two projects: Omarchy (the desktop) and
Meta's Muse Linux Device SDK (the agent). Neither is forked. Musarchy is a
layer that sits on top of both.

```
+------------------------------- laptop -------------------------------+
|  Omarchy 4 (Arch + Hyprland)      stock install, official ISO        |
|                                                                      |
|  musegadget service               Meta's device agent, pinned commit |
|    run as root, holds BLE + credentials                              |
|      |                                                               |
|      +-- musarchy plugin          desktop.run / windows / notify     |
|                                                                      |
|  commands run as `muse`           dedicated account, no sudo         |
+----------------------------------------------------------------------+
        |  encrypted Noise session
        v
   your Muse (phone app)
```

## Why not a fork

Forking Omarchy would mean carrying their release cadence: every Quattro
update becomes a merge conflict. Forking the device SDK would mean carrying
their pairing and protocol code. Musarchy owns neither problem. It installs
on stock Omarchy 4 from the official ISO, and it installs the device SDK
from a pinned upstream commit. Upgrading either side is a version bump in
`install.sh`, not a rebase.

## How the plugin reaches the service

The upstream systemd unit starts `musegadget run`. Musarchy's installer
rewrites that one line to `python -m musarchy_plugin run`. The plugin's
`__main__` calls `wiring.apply()` (which extends `COMMAND_SPECS` and
wraps `Executor.run`, exactly the way the SDK's own AGENTS.md describes
adding a command), then hands control to the unmodified upstream CLI.
Pairing, `info`, and `send-user-msg` run on the stock binary and behave
exactly as the SDK documents them.

The plugin package (`musarchy-plugin`) is installed into the same venv as
the SDK, with no extra dependencies. `desktop.py` imports nothing from
the SDK, so the desktop logic is unit-testable on any machine.

## The three new commands

- `desktop.run`: `system.run` with the user's Hyprland/Wayland session
  environment injected (`WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`,
  `XDG_RUNTIME_DIR`, session D-Bus). Plain `system.run` runs headless, so
  GUI tools fail under it. This reuses `system.run`'s timeout and output
  handling through a temporary environment patch, so none of that logic
  is duplicated.
- `desktop.windows`: parsed `hyprctl clients -j`. Read-only.
- `desktop.notify`: `notify-send` wrapper for on-screen notifications.

Session discovery reads `/run/user/<uid>/hypr/` and picks the most
recently used Hyprland instance. When the desktop is not running, the
commands fail with a plain error instead of hanging.

## What musarchy changes vs upstream

1. Arch Linux support (Omarchy is Arch; the SDK installer is Debian-only).
2. A dedicated `muse` account by default instead of the installing user,
   so the agent never inherits your sudo rights.
3. The plugin and its three commands.
4. A systemd hardening drop-in for the service process.
5. Docs for the whole thing.
