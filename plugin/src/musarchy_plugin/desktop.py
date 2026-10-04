# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
"""Hyprland desktop primitives for the Muse device agent.

These functions implement musarchy's extra commands. They are deliberately
free of musegadget imports so they can be unit-tested without the SDK; the
wiring into COMMAND_SPECS and Executor.run lives in musarchy_plugin/__init__.py.

Conventions (matching upstream executor.py):
- functions take (executor, params, timeout_ms=None) and return a payload
  dict, or raise DesktopError for expected failures (bad parameters, no
  desktop session).
- anything that touches the machine runs through executor._child_options(),
  so it runs as the run-as account, never as the service account.
"""

from __future__ import annotations

import contextlib
import json
import os
import pwd
import subprocess

HYPRCTL_TIMEOUT_S = 15
NOTIFY_TIMEOUT_S = 10


class DesktopError(Exception):
    """An expected failure: bad parameters or no desktop session."""


def desktop_uid(executor) -> int:
    """Uid whose graphical session the desktop commands should use.

    Defaults to the run-as account. Set MUSEGADGET_DESKTOP_USER to a
    username (for example the person actually logged into the desktop)
    to point the desktop commands at that user's session instead, while
    commands still execute as the run-as account. Unknown usernames fall
    back to the run-as account.
    """
    name = os.environ.get("MUSEGADGET_DESKTOP_USER")
    if name:
        try:
            return pwd.getpwnam(name).pw_uid
        except KeyError:
            pass
    return executor.account.uid


def session_env(uid: int, runtime_base: str = "/run/user") -> dict[str, str]:
    """Find the Wayland/Hyprland session environment for a uid.

    Picks the most recently used Hyprland instance when several exist.
    Raises DesktopError when the user has no graphical session.
    """
    runtime = os.path.join(runtime_base, str(uid))
    hypr_dir = os.path.join(runtime, "hypr")
    try:
        entries = os.listdir(hypr_dir)
    except OSError:
        raise DesktopError(
            "no Hyprland session found for this user; is the desktop running?"
        ) from None
    sigs = [e for e in entries if os.path.isdir(os.path.join(hypr_dir, e))]
    if not sigs:
        raise DesktopError(
            "no Hyprland session found for this user; is the desktop running?"
        )
    sig = max(sigs, key=lambda e: os.path.getmtime(os.path.join(hypr_dir, e)))
    env = {
        "XDG_RUNTIME_DIR": runtime,
        "HYPRLAND_INSTANCE_SIGNATURE": sig,
    }
    try:
        sockets = sorted(
            e for e in os.listdir(runtime)
            if e.startswith("wayland-") and not e.endswith(".lock")
        )
    except OSError:
        sockets = []
    if sockets:
        env["WAYLAND_DISPLAY"] = sockets[0]
    bus = os.path.join(runtime, "bus")
    if os.path.exists(bus):
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + bus
    return env


def _as_account(executor, argv: list[str], env_extra: dict,
                timeout: int) -> subprocess.CompletedProcess:
    """Run argv as the run-as account with extra environment variables."""
    options = executor._child_options()
    options["env"] = {**options["env"], **env_extra}
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, **options
    )


@contextlib.contextmanager
def _extra_env(executor, extra: dict):
    """Temporarily add environment variables to the account's child env."""
    original = executor._child_options

    def patched():
        options = original()
        options["env"] = {**options["env"], **extra}
        return options

    executor._child_options = patched
    try:
        yield
    finally:
        executor._child_options = original


def desktop_run(executor, params: dict, timeout_ms=None) -> dict:
    """system.run, but inside the user's graphical (Hyprland/Wayland) session.

    Plain system.run has no display environment, so GUI tools (hyprctl,
    notify-send, graphical apps) fail under it. This injects the session
    environment first, then reuses system.run's timeout and output handling.
    """
    command = params.get("command")
    if not isinstance(command, str) or not command.strip():
        raise DesktopError("command is required")
    env = session_env(desktop_uid(executor))
    with _extra_env(executor, env):
        result = executor.system_run(params, timeout_ms)
    if not result.get("ok"):
        raise DesktopError(result.get("error", "command failed"))
    payload = dict(result["payload"])
    payload["session"] = {
        key: env[key]
        for key in ("WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE")
        if key in env
    }
    return payload


def desktop_windows(executor, params: dict, timeout_ms=None) -> dict:
    """List open windows on the Hyprland desktop via hyprctl."""
    env = session_env(desktop_uid(executor))
    proc = _as_account(executor, ["hyprctl", "clients", "-j"], env, HYPRCTL_TIMEOUT_S)
    if proc.returncode != 0:
        raise DesktopError("hyprctl failed: " + proc.stderr.strip()[:300])
    try:
        clients = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise DesktopError("hyprctl returned output that is not JSON")
    windows = []
    for client in clients:
        workspace = client.get("workspace") or {}
        windows.append({
            "address": client.get("address"),
            "class": client.get("class"),
            "title": client.get("title"),
            "workspace": {"id": workspace.get("id"), "name": workspace.get("name")},
            "floating": bool(client.get("floating")),
            "pid": client.get("pid"),
            "focused": client.get("focusHistoryID") == 0,
        })
    return {"windows": windows}


def desktop_notify(executor, params: dict, timeout_ms=None) -> dict:
    """Show a desktop notification.

    Tries notify-send first (rich notifications through the session's
    notification daemon). Falls back to Hyprland's built-in
    `hyprctl notify`, which also works when the agent runs as a different
    user than the desktop owner and the session bus refuses the
    connection, or when no notification daemon is running.
    """
    summary = params.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise DesktopError("summary is required")
    body = params.get("body") or ""
    if not isinstance(body, str):
        raise DesktopError("body must be a string")
    urgency = params.get("urgency", "normal")
    if urgency not in ("low", "normal", "critical"):
        raise DesktopError("urgency must be low, normal or critical")
    expire_ms = params.get("expire_ms")
    if expire_ms is not None:
        try:
            expire_ms = int(expire_ms)
        except (TypeError, ValueError):
            raise DesktopError("expire_ms must be an integer") from None
    env = session_env(desktop_uid(executor))
    argv = ["notify-send", "--app-name=Musarchy", "--urgency=" + urgency]
    if expire_ms is not None:
        argv.append("--expire-time=" + str(expire_ms))
    argv += [summary, body]
    proc = _as_account(executor, argv, env, NOTIFY_TIMEOUT_S)
    if proc.returncode == 0:
        return {"notified": True}
    notify_err = proc.stderr.strip()[:300]
    # notify-send needs the session bus; when the agent runs as another
    # user the bus may refuse the connection. The compositor's own
    # notifications need only the Hyprland socket, which we already have.
    icon = {"low": 1, "normal": 2, "critical": 3}[urgency]
    time_ms = expire_ms if expire_ms is not None else 5000
    message = summary if not body else summary + "\n" + body
    fallback = ["hyprctl", "notify", str(icon), str(time_ms), "rgb(ff5555)", message]
    proc = _as_account(executor, fallback, env, NOTIFY_TIMEOUT_S)
    if proc.returncode != 0:
        raise DesktopError(
            "notify-send failed: " + notify_err
            + "; hyprctl notify failed: " + proc.stderr.strip()[:300]
        )
    return {"notified": True}
