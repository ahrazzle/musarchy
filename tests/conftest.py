# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures: a stub Executor that behaves like the SDK's."""

from __future__ import annotations

import os
import sys
import types

PLUGIN_SRC = os.path.join(os.path.dirname(__file__), "..", "plugin", "src")
sys.path.insert(0, os.path.abspath(PLUGIN_SRC))


class FakeAccount:
    def __init__(self, uid=1000, gid=1000, name="tester", home="/home/tester"):
        self.uid = uid
        self.gid = gid
        self.name = name
        self.home = home


class FakeExecutor:
    """Duck-typed stand-in for musegadget.executor.Executor."""

    def __init__(self, account=None):
        self.account = account or FakeAccount()
        self.last_env = None

    def _child_options(self):
        return {"env": {"PATH": "/usr/bin:/bin", "HOME": self.account.home}}

    def system_run(self, params, timeout_ms):
        # Record the environment the command would have run with.
        self.last_env = dict(self._child_options()["env"])
        return {
            "ok": True,
            "payload": {
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "truncated": False,
                "duration_ms": 1,
            },
        }


def make_session_tree(base, uid=1000, sig="abc123", wayland="wayland-1"):
    """Build a fake /run/user/<uid> tree with a Hyprland session."""
    runtime = os.path.join(base, str(uid))
    hypr = os.path.join(runtime, "hypr", sig)
    os.makedirs(hypr)
    if wayland:
        open(os.path.join(runtime, wayland), "w").close()
    open(os.path.join(runtime, "bus"), "w").close()
    return runtime


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def stub_musegadget():
    """Install a minimal musegadget.executor stub into sys.modules.

    Returns (package, executor_module). Lets the wiring test import
    musarchy_plugin without the real SDK.
    """
    calls = []

    class StubExecutor:
        def __init__(self):
            self.account = FakeAccount()

        def run(self, command, params, timeout_ms=None):
            calls.append((command, params, timeout_ms))
            return {"ok": True, "payload": {"echo": command}}

    executor_mod = types.ModuleType("musegadget.executor")
    executor_mod.COMMAND_SPECS = {}
    executor_mod.Executor = StubExecutor
    executor_mod.ok = lambda payload: {"ok": True, "payload": payload}
    executor_mod.error = lambda message: {"ok": False, "error": message}

    package = types.ModuleType("musegadget")
    package.executor = executor_mod
    sys.modules["musegadget"] = package
    sys.modules["musegadget.executor"] = executor_mod
    return package, executor_mod, calls
