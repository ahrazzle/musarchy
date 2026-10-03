# Architecture

Musarchy connects two projects: Omarchy (the desktop) and Meta's Muse Linux
Device SDK (the agent). It forks neither. It is a layer on top of both.

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

Forking Omarchy means carrying their release schedule. Every update becomes
a merge conflict. Forking the device SDK means carrying their pairing and
protocol code. Musarchy avoids both. It installs on stock Omarchy 4 from the
official ISO. It installs the device SDK from one pinned upstream commit.
Upgrading either side is a version bump in `install.sh`.

## How the plugin reaches the service

The upstream systemd unit starts `musegadget run`. The musarchy installer
changes that one line to `python -m musarchy_plugin run`. The plugin's entry
point registers the extra commands, then hands control to the unmodified
upstream CLI. Pairing, `info`, and `send-user-msg` run on the stock binary.
They behave exactly as the SDK documents.

The plugin (`musarchy-plugin`) installs into the same venv as the SDK. It
has no extra dependencies. `desktop.py` imports nothing from the SDK, so the
desktop logic is unit-testable on any machine.

## The three new commands

- `desktop.run`: `system.run` with your desktop session variables added
  (`WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`, and the rest). Plain
  `system.run` runs without a display, so desktop tools fail under it. This
  reuses `system.run`'s timeout and output handling instead of duplicating it.
- `desktop.windows`: parsed `hyprctl clients -j`. Read-only.
- `desktop.notify`: `notify-send` wrapper for on-screen notifications.

Session discovery reads `/run/user/<uid>/hypr/` and picks the most recently
used session. When the desktop is not running, the commands return a plain
error instead of hanging.

## What musarchy changes vs upstream

1. Arch Linux support. Omarchy is Arch. The SDK installer only handles
   Debian and Ubuntu.
2. A dedicated `muse` account by default, instead of the installing user.
   The agent never inherits your sudo rights.
3. The plugin and its three commands.
4. A systemd hardening drop-in for the service process.
5. Docs.
