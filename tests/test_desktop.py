# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Hyprland desktop commands. No SDK, no desktop needed."""

from __future__ import annotations

import os
import time

import pytest

from conftest import FakeCompletedProcess, FakeExecutor, make_session_tree
from musarchy_plugin import desktop
from musarchy_plugin.desktop import (
    DesktopError,
    desktop_notify,
    desktop_run,
    desktop_uid,
    desktop_windows,
    session_env,
)


def test_session_env_discovers_wayland_and_hyprland(tmp_path):
    make_session_tree(str(tmp_path), uid=1000, sig="deadbeef")
    env = session_env(1000, runtime_base=str(tmp_path))
    assert env["HYPRLAND_INSTANCE_SIGNATURE"] == "deadbeef"
    assert env["WAYLAND_DISPLAY"] == "wayland-1"
    assert env["XDG_RUNTIME_DIR"] == os.path.join(str(tmp_path), "1000")
    assert env["DBUS_SESSION_BUS_ADDRESS"].startswith("unix:path=")


def test_session_env_picks_the_newest_instance(tmp_path):
    make_session_tree(str(tmp_path), uid=1000, sig="old")
    old_dir = os.path.join(str(tmp_path), "1000", "hypr", "old")
    new_dir = os.path.join(str(tmp_path), "1000", "hypr", "new")
    os.makedirs(new_dir)
    now = time.time()
    os.utime(old_dir, (now - 3600, now - 3600))
    os.utime(new_dir, (now, now))
    env = session_env(1000, runtime_base=str(tmp_path))
    assert env["HYPRLAND_INSTANCE_SIGNATURE"] == "new"


def test_session_env_without_desktop_raises(tmp_path):
    with pytest.raises(DesktopError, match="no Hyprland session"):
        session_env(1000, runtime_base=str(tmp_path))


def test_desktop_run_injects_the_session_env(tmp_path):
    make_session_tree(str(tmp_path), uid=1000, sig="abc123")
    ex = FakeExecutor()
    real_session_env = desktop.session_env
    desktop.session_env = lambda uid, runtime_base="/run/user": real_session_env(
        uid, runtime_base=str(tmp_path)
    )
    try:
        payload = desktop_run(ex, {"command": "echo hi"}, None)
    finally:
        desktop.session_env = real_session_env
    assert ex.last_env["WAYLAND_DISPLAY"] == "wayland-1"
    assert ex.last_env["HYPRLAND_INSTANCE_SIGNATURE"] == "abc123"
    assert payload["session"]["WAYLAND_DISPLAY"] == "wayland-1"
    assert payload["exit_code"] == 0


def test_desktop_run_requires_a_command():
    with pytest.raises(DesktopError, match="command is required"):
        desktop_run(FakeExecutor(), {}, None)
    with pytest.raises(DesktopError, match="command is required"):
        desktop_run(FakeExecutor(), {"command": "   "}, None)


def test_desktop_windows_lists_windows(monkeypatch, tmp_path):
    make_session_tree(str(tmp_path), uid=1000)
    real_session_env = desktop.session_env
    monkeypatch.setattr(
        desktop, "session_env",
        lambda uid, runtime_base="/run/user": real_session_env(uid, str(tmp_path)),
    )
    hyprctl_out = (
        '[{"address":"0x1a2b","class":"Alacritty","title":"nvim",'
        '"workspace":{"id":1,"name":"1"},"floating":false,'
        '"pid":4242,"focusHistoryID":0},'
        '{"address":"0x3c4d","class":"firefox","title":"Inbox",'
        '"workspace":{"id":2,"name":"2"},"floating":true,'
        '"pid":5150,"focusHistoryID":3}]'
    )
    seen = {}

    def fake_run(executor, argv, env_extra, timeout):
        seen["argv"] = argv
        seen["env"] = env_extra
        return FakeCompletedProcess(stdout=hyprctl_out)

    monkeypatch.setattr(desktop, "_as_account", fake_run)
    payload = desktop_windows(FakeExecutor(), {}, None)
    assert seen["argv"] == ["hyprctl", "clients", "-j"]
    assert seen["env"]["HYPRLAND_INSTANCE_SIGNATURE"]
    windows = payload["windows"]
    assert len(windows) == 2
    assert windows[0]["class"] == "Alacritty"
    assert windows[0]["focused"] is True
    assert windows[0]["workspace"] == {"id": 1, "name": "1"}
    assert windows[1]["floating"] is True
    assert windows[1]["focused"] is False


def test_desktop_windows_hyprctl_failure(monkeypatch, tmp_path):
    make_session_tree(str(tmp_path), uid=1000)
    real_session_env = desktop.session_env
    monkeypatch.setattr(
        desktop, "session_env",
        lambda uid, runtime_base="/run/user": real_session_env(uid, str(tmp_path)),
    )
    monkeypatch.setattr(
        desktop, "_as_account",
        lambda e, a, env, t: FakeCompletedProcess(returncode=1, stderr="nope"),
    )
    with pytest.raises(DesktopError, match="hyprctl failed"):
        desktop_windows(FakeExecutor(), {}, None)


def test_desktop_windows_bad_json(monkeypatch, tmp_path):
    make_session_tree(str(tmp_path), uid=1000)
    real_session_env = desktop.session_env
    monkeypatch.setattr(
        desktop, "session_env",
        lambda uid, runtime_base="/run/user": real_session_env(uid, str(tmp_path)),
    )
    monkeypatch.setattr(
        desktop, "_as_account",
        lambda e, a, env, t: FakeCompletedProcess(stdout="not json"),
    )
    with pytest.raises(DesktopError, match="not JSON"):
        desktop_windows(FakeExecutor(), {}, None)


def test_desktop_notify_sends_notification(monkeypatch, tmp_path):
    make_session_tree(str(tmp_path), uid=1000)
    real_session_env = desktop.session_env
    monkeypatch.setattr(
        desktop, "session_env",
        lambda uid, runtime_base="/run/user": real_session_env(uid, str(tmp_path)),
    )
    seen = {}
    monkeypatch.setattr(
        desktop, "_as_account",
        lambda e, argv, env, t: seen.update(argv=argv) or FakeCompletedProcess(),
    )
    payload = desktop_notify(
        FakeExecutor(),
        {"summary": "Backup done", "body": "All green", "urgency": "low"},
        None,
    )
    assert payload == {"notified": True}
    assert seen["argv"][:3] == ["notify-send", "--app-name=Musarchy", "--urgency=low"]
    assert seen["argv"][-2:] == ["Backup done", "All green"]


def test_desktop_notify_validates_params():
    with pytest.raises(DesktopError, match="summary is required"):
        desktop_notify(FakeExecutor(), {}, None)
    with pytest.raises(DesktopError, match="urgency must be"):
        desktop_notify(FakeExecutor(), {"summary": "x", "urgency": "extreme"}, None)
    with pytest.raises(DesktopError, match="expire_ms must be an integer"):
        desktop_notify(FakeExecutor(), {"summary": "x", "expire_ms": "soon"}, None)


def test_desktop_notify_failure(monkeypatch, tmp_path):
    make_session_tree(str(tmp_path), uid=1000)
    real_session_env = desktop.session_env
    monkeypatch.setattr(
        desktop, "session_env",
        lambda uid, runtime_base="/run/user": real_session_env(uid, str(tmp_path)),
    )
    monkeypatch.setattr(
        desktop, "_as_account",
        lambda e, a, env, t: FakeCompletedProcess(returncode=1, stderr="no daemon"),
    )
    with pytest.raises(DesktopError, match="notify-send failed"):
        desktop_notify(FakeExecutor(), {"summary": "x"}, None)


def test_desktop_uid_defaults_to_run_as_account(monkeypatch):
    monkeypatch.delenv("MUSEGADGET_DESKTOP_USER", raising=False)
    ex = FakeExecutor()
    ex.account.uid = 1001
    assert desktop_uid(ex) == 1001


def test_desktop_uid_honors_env_override(monkeypatch):
    import types

    def fake_getpwnam(name):
        if name == "shahid":
            return types.SimpleNamespace(pw_uid=1000)
        raise KeyError(name)

    monkeypatch.setenv("MUSEGADGET_DESKTOP_USER", "shahid")
    monkeypatch.setattr(desktop.pwd, "getpwnam", fake_getpwnam)
    ex = FakeExecutor()
    ex.account.uid = 1001
    assert desktop_uid(ex) == 1000


def test_desktop_uid_unknown_user_falls_back(monkeypatch):
    monkeypatch.setenv("MUSEGADGET_DESKTOP_USER", "nobody-here")
    ex = FakeExecutor()
    ex.account.uid = 1001
    assert desktop_uid(ex) == 1001


def _patched_session(monkeypatch, tmp_path):
    make_session_tree(str(tmp_path), uid=1000)
    real_session_env = desktop.session_env
    monkeypatch.setattr(
        desktop, "session_env",
        lambda uid, runtime_base="/run/user": real_session_env(uid, str(tmp_path)),
    )


def test_desktop_notify_falls_back_to_hyprctl(monkeypatch, tmp_path):
    _patched_session(monkeypatch, tmp_path)
    calls = []

    def fake_run(executor, argv, env, timeout):
        calls.append(argv)
        if argv[0] == "notify-send":
            return FakeCompletedProcess(returncode=1, stderr="bus refused")
        return FakeCompletedProcess()

    monkeypatch.setattr(desktop, "_as_account", fake_run)
    payload = desktop_notify(
        FakeExecutor(),
        {"summary": "Hi", "body": "there", "urgency": "critical", "expire_ms": 7000},
        None,
    )
    assert payload == {"notified": True}
    assert len(calls) == 2
    assert calls[1][:4] == ["hyprctl", "notify", "3", "7000"]
    assert calls[1][-1] == "Hi\nthere"


def test_desktop_notify_both_fail(monkeypatch, tmp_path):
    _patched_session(monkeypatch, tmp_path)
    monkeypatch.setattr(
        desktop, "_as_account",
        lambda e, a, env, t: FakeCompletedProcess(returncode=1, stderr="nope"),
    )
    with pytest.raises(DesktopError, match="notify-send failed.*hyprctl notify failed"):
        desktop_notify(FakeExecutor(), {"summary": "x"}, None)
