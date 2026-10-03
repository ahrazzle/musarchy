# Copyright (c) 2026 musarchy contributors.
# SPDX-License-Identifier: Apache-2.0
"""Service entry point: apply the musarchy plugin, then run the stock CLI.

The systemd unit starts the device with
``python -m musarchy_plugin run`` instead of ``musegadget run``. apply()
registers the Hyprland commands; control then passes to the unmodified
upstream CLI, so pairing, info and send-user-msg behave exactly as the SDK
documents them.
"""

from __future__ import annotations

from musarchy_plugin.wiring import apply
from musegadget.cli import main

if __name__ == "__main__":
    apply()
    raise SystemExit(main())
