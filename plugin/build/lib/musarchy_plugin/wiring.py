# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
"""Wire musarchy's commands into the upstream device agent.

Extends the SDK's COMMAND_SPECS and wraps Executor.run, following the
SDK's own "Adding a command" recipe from its AGENTS.md. The upstream
package is never modified, so it can be upgraded by changing the pinned
commit in install.sh.
"""

from __future__ import annotations

import logging

from musegadget import executor as _executor

from musarchy_plugin import desktop

log = logging.getLogger(__name__)

COMMAND_SPECS = {
    "desktop.run": {
        "description": (
            "Run a shell command inside the user's graphical Hyprland/Wayland "
            "session and return its stdout, stderr and exit code. Use this "
            "instead of system.run for anything that needs the display: "
            "hyprctl, notify-send, launching graphical apps. Output over "
            "96 KiB per stream is truncated."
        ),
        "required": {
            "command": {"type": "string", "description": "Shell command line to run."},
        },
        "optional": {
            "cwd": {"type": "string", "description": "Working directory. Default: the account's home."},
            "timeout_ms": {"type": "integer", "description": "Kill the command after this long. Default 120000, max 600000."},
        },
        "timeout_ms": 605000,
    },
    "desktop.windows": {
        "description": (
            "List the open windows on the Hyprland desktop: address, app "
            "class, title, workspace, floating state, pid and focus state."
        ),
        "required": {},
        "optional": {},
    },
    "desktop.notify": {
        "description": (
            "Show a desktop notification on the user's screen."
        ),
        "required": {
            "summary": {"type": "string", "description": "Notification headline."},
        },
        "optional": {
            "body": {"type": "string", "description": "Notification body text."},
            "urgency": {"type": "string", "description": "low, normal or critical. Default: normal."},
            "expire_ms": {"type": "integer", "description": "How long the notification stays up, in milliseconds."},
        },
    },
}

_COMMANDS = {
    "desktop.run": desktop.desktop_run,
    "desktop.windows": desktop.desktop_windows,
    "desktop.notify": desktop.desktop_notify,
}


def _wrap(name, fn):
    def handler(self, params, timeout_ms=None):
        try:
            return _executor.ok(fn(self, params, timeout_ms))
        except desktop.DesktopError as exc:
            return _executor.error(str(exc))
        except Exception as exc:
            log.exception("%s failed", name)
            return _executor.error(f"{type(exc).__name__}: {exc}")

    return handler


def apply() -> None:
    """Register musarchy's commands. Safe to call more than once."""
    run = _executor.Executor.run
    if getattr(run, "_musarchy_wrapped", False):
        return

    def run_with_desktop(self, command, params, timeout_ms=None):
        fn = _COMMANDS.get(command)
        if fn is not None:
            return _wrap(command, fn)(self, params, timeout_ms)
        return run(self, command, params, timeout_ms)

    run_with_desktop._musarchy_wrapped = True  # noqa: SLF001
    _executor.Executor.run = run_with_desktop
    _executor.COMMAND_SPECS.update(COMMAND_SPECS)
