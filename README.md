# Musarchy

Omarchy x Muse. A Muse-connected Linux desktop.

Musarchy installs on stock Omarchy 4 and adds an always-on Muse device
agent: your Muse can run commands on the laptop, move files, check its
health, and — through three musarchy commands — see your windows, run
things in your graphical session, and show notifications. Pair once from
the Muse app and it stays connected across reboots.

It is not a fork of anything. Omarchy stays stock, Meta's device SDK stays
pinned to an upstream commit, and musarchy is the layer between them. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

Alpha. The Arch port, the plugin, and the unit tests are done and checked
here. What has **not** been tested yet: a live install on Arch/Omarchy,
Bluetooth pairing with the Muse app, and the service running under a real
Hyprland session. See [docs/PAIRING.md](docs/PAIRING.md) and
[docs/SECURITY.md](docs/SECURITY.md) before you install.

## Quickstart

1. Install Omarchy 4 from the official ISO
   ([omarchy.org](https://omarchy.org), source at
   [github.com/omacom/omarchy](https://github.com/omacom/omarchy)).
2. Get an SDK token at [gadgets.muse.ai](https://gadgets.muse.ai)
   (Account > SDK tokens).
3. On the laptop:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/ahrazzle/musarchy/main/install.sh -o install.sh
   less install.sh   # read it first
   bash install.sh --sdk-token mgst_...
   ```

4. Pair in the Muse app: Settings > Devices > Developer mode, Add Device,
   choose the `MuseGadgetXXXXXX` name the installer printed.
   Full steps in [docs/PAIRING.md](docs/PAIRING.md).

Then ask your Muse things like:

> What windows do I have open?
> Open a terminal and tail the musarchy log.
> Notify me on screen when the backup finishes.

## Commands

From Meta's Linux Device SDK (unchanged):

| Command | What it does |
|---|---|
| `system.run` | Run a shell command, return stdout/stderr/exit code |
| `file.read` / `file.write` | Read and write files in 64 KiB chunks |
| `device.health` | Uptime, load, memory, disk, temperature |

Added by musarchy:

| Command | What it does |
|---|---|
| `desktop.run` | `system.run` inside your Hyprland/Wayland session (hyprctl, GUI apps) |
| `desktop.windows` | List open windows: app, title, workspace, focus state |
| `desktop.notify` | Show a desktop notification |

Commands run as the dedicated `muse` account (no sudo, no password
login). Read [docs/SECURITY.md](docs/SECURITY.md) for the full model.

## Layout

```
install.sh              Arch port of the SDK installer + plugin install
plugin/                 musarchy-plugin: the three desktop commands
systemd/                service hardening drop-in (source of truth)
tests/                  unit tests (pytest, no SDK or desktop needed)
docs/                   architecture, pairing, security
```

## Develop

```bash
python3 -m pytest tests/ -q        # plugin unit tests
bash -n install.sh                 # syntax check
shellcheck install.sh              # upstream keeps it ShellCheck-clean; so do we
```

To hack on a live device: copy `plugin/` over, reinstall it into the venv
(`sudo /opt/musegadget/venv/bin/pip install --no-deps --force-reinstall ./plugin`),
restart the service. Muse sees new commands after the service restarts.

## Attribution

- Device agent: [muse-gadget-sdk](https://github.com/facebookincubator/muse-gadget-sdk)
  by Meta Platforms, Inc., Apache-2.0. Pinned commit in `install.sh`.
- Desktop: [Omarchy](https://github.com/omacom/omarchy) by David
  Heinemeier Hansson, MIT. Musarchy installs on stock Omarchy and is not
  affiliated with or endorsed by the Omarchy project.

See NOTICE for details.

## License

Apache-2.0. See LICENSE.
