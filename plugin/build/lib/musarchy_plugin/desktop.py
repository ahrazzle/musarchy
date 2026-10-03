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
import subprocess

HYPRCTL_TIMEOUT_S = 15
NOTIFY_TIMEOUT_S = 10


class DesktopError(Exception):
    """An expected failure: bad parameters or no desktop session."""


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
    env = session_env(executor.account.uid)
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
    env = session_env(executor.account.uid)
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
    """Show a desktop notification with notify-send."""
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
    env = session_env(executor.account.uid)
    argv = ["notify-send", "--app-name=Musarchy", "--urgency=" + urgency]
    if expire_ms is not None:
        argv.append("--expire-time=" + str(expire_ms))
    argv += [summary, body]
    proc = _as_account(executor, argv, env, NOTIFY_TIMEOUT_S)
    if proc.returncode != 0:
        raise DesktopError("notify-send failed: " + proc.stderr.strip()[:300])
    return {"notified": True}
