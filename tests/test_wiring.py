# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the plugin wiring: specs registered, dispatch works, upstream kept."""

from __future__ import annotations

import pytest

import conftest


@pytest.fixture(scope="module")
def wired():
    package, executor_mod, calls = conftest.stub_musegadget()
    from musarchy_plugin import wiring

    wiring.apply()
    return wiring, executor_mod, calls


def test_command_specs_registered(wired):
    wiring, executor_mod, _ = wired
    for name in ("desktop.run", "desktop.windows", "desktop.notify"):
        spec = executor_mod.COMMAND_SPECS[name]
        assert spec["description"]
        assert isinstance(spec["required"], dict)
        assert isinstance(spec["optional"], dict)
    # Every parameter documents its type and description, per the SDK's recipe.
    for spec in wiring.COMMAND_SPECS.values():
        for group in ("required", "optional"):
            for param in spec[group].values():
                assert param["type"] and param["description"]


def test_dispatch_reaches_new_commands(wired, monkeypatch):
    wiring, executor_mod, _ = wired

    seen = {}
    monkeypatch.setitem(
        wiring._COMMANDS,
        "desktop.notify",
        lambda executor, params, timeout_ms=None: seen.update(params=params) or {"notified": True},
    )
    ex = executor_mod.Executor()
    result = ex.run("desktop.notify", {"summary": "hi"})
    assert result == {"ok": True, "payload": {"notified": True}}
    assert seen["params"] == {"summary": "hi"}


def test_upstream_commands_still_work(wired):
    _, executor_mod, calls = wired
    ex = executor_mod.Executor()
    result = ex.run("system.run", {"command": "echo hi"})
    assert result == {"ok": True, "payload": {"echo": "system.run"}}
    assert calls[-1][0] == "system.run"


def test_desktop_errors_become_error_results(wired):
    _, executor_mod, _ = wired
    ex = executor_mod.Executor()
    # No desktop session here, so desktop.windows must fail gracefully,
    # not raise through the service.
    result = ex.run("desktop.windows", {})
    assert result["ok"] is False
    assert "no Hyprland session" in result["error"]


def test_apply_is_idempotent(wired):
    wiring, executor_mod, _ = wired
    before = executor_mod.Executor.run
    wiring.apply()
    wiring.apply()
    assert executor_mod.Executor.run is before
    # And double-wrapping did not stack: one dispatch only.
    ex = executor_mod.Executor()
    result = ex.run("desktop.notify", {"summary": "x"})
    assert result["ok"] is False  # no session, but exactly one error layer
