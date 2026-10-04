# Musarchy

Musarchy connects an Omarchy laptop to your Muse. Pair once in the Muse app.
Then your Muse can run commands on the laptop, move files, check its health,
list your open windows, and show notifications on your screen.

It is built from two open-source projects and forks neither. Omarchy stays
stock. Meta's device SDK stays pinned to one upstream commit. Musarchy is the
layer between them. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

Alpha. Tested on live Omarchy hardware (2026-10-04): pairing, all seven
commands, and the desktop commands under a real Hyprland session all work.
Bluetooth pairing with the app is untested.

## Quickstart

1. Install Omarchy 4 from the official ISO ([omarchy.org](https://omarchy.org)).
2. Get an SDK token at [gadgets.muse.ai](https://gadgets.muse.ai)
   (Account → SDK tokens).
3. On the laptop:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/ahrazzle/musarchy/main/install.sh -o install.sh
   less install.sh   # read it first
   bash install.sh --sdk-token mgst_...
   ```

4. Pair in the Muse app: Settings → Devices → Developer mode → Add Device.
   Choose the `MuseGadgetXXXXXX` name the installer printed.
   Full steps in [docs/PAIRING.md](docs/PAIRING.md).

Then ask your Muse things like: "What windows do I have open?" "How much
disk is free?" "Tell me on screen when the backup finishes."

## Commands

From Meta's Linux Device SDK (unchanged):

| Command | What it does |
|---|---|
| `system.run` | Run a shell command. Returns stdout, stderr, exit code. |
| `file.read` / `file.write` | Read and write files in chunks. |
| `device.health` | Uptime, load, memory, disk, temperature. |

Added by musarchy:

| Command | What it does |
|---|---|
| `desktop.run` | Run a command inside your graphical desktop session. Plain `system.run` has no display, so desktop tools fail under it. |
| `desktop.windows` | List open windows: app, title, workspace, focus state. |
| `desktop.notify` | Show a notification on your screen. |

Commands run as the `muse` account. It has no sudo rights and no password
login. Full model in [docs/SECURITY.md](docs/SECURITY.md).

The desktop commands need the graphical session, which belongs to the
person at the keyboard — usually not the `muse` account. The installer
detects that user (or take `--desktop-user`) and the plugin then uses
their session via `MUSEGADGET_DESKTOP_USER`, while commands still execute
as the run-as account. `desktop.notify` tries `notify-send` first and
falls back to Hyprland's built-in `hyprctl notify`.

## Layout

```
install.sh              Arch port of the SDK installer, plus the plugin install
plugin/                 musarchy-plugin: the three desktop commands
systemd/                service hardening drop-in
tests/                  unit tests (pytest, no SDK or desktop needed)
docs/                   architecture, pairing, security
```

## Develop

```bash
python3 -m pytest tests/ -q
bash -n install.sh
shellcheck install.sh
```

To hack on a live device: copy `plugin/` over, reinstall it into the venv,
restart the service. Your Muse sees new commands after the restart.

## Attribution

- Device agent: [muse-gadget-sdk](https://github.com/facebookincubator/muse-gadget-sdk)
  by Meta Platforms, Inc. Apache-2.0. Pinned commit in `install.sh`.
- Desktop: [Omarchy](https://github.com/omacom/omarchy) by David
  Heinemeier Hansson. MIT. Musarchy installs on stock Omarchy. It is not
  affiliated with the Omarchy project.

See NOTICE for details.

## License

Apache-2.0. See LICENSE.
