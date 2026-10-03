# Security

Musarchy gives your Muse the ability to run commands on your laptop. That
is the point of the project, and it is also the entire risk. This page
describes the threat model and what the installer does about it.

## What your Muse can do

Everything the `muse` account can do. That account is deliberately boring:
no sudo rights, no password login, a normal home directory. Your Muse can
run shell commands, read and write files, list your windows, and show
notifications as that account. It cannot touch other users' files, install
system packages, or read the device credentials in `/var/lib/musegadget`
(root-only, mode 0700).

If you override the account with `--run-as` and pick one with sudo, your
Muse gets sudo too. The installer warns you when that is the case. Do not
do this on a machine you care about unless you understand the tradeoff.

## What the installer hardens

- **Dedicated account.** The default is a fresh `muse` user, not you.
  Upstream's installer defaults to the installing user, which on Omarchy
  usually has sudo.
- **Service sandbox.** A systemd drop-in restricts the service process
  itself (`NoNewPrivileges`, `ProtectSystem`, kernel and tmp
  restrictions). Commands are unaffected; they run as the `muse`
  account either way.
- **Token storage.** The SDK token lives at
  `/var/lib/musegadget/sdk_token`, readable only by root.
- **BlueZ.** The installer caps the GATT MTU at 256 (the Android app
  breaks above 512) and disables BlueZ's battery plugin so phones are
  never asked to bond. Pairing opens only when you run the installer or
  `sudo musegadget pair` on the machine itself.

## What is not protected

- **Physical and network trust.** Pairing has no manufacturer
  verification and cannot stop an active man-in-the-middle. Pair on a
  network you trust.
- **Malicious commands.** There is no allowlist. If your Muse is
  compromised, or you ask it to do something destructive as the `muse`
  account, it can. Keep backups.
- **The `muse` account's own data.** Anything that account can read,
  your Muse can read. Do not store secrets in its home directory.

## Reporting issues

Open an issue on GitHub. Do not post SDK tokens, pairing files, or logs
containing them.
