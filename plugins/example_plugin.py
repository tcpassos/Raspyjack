"""Example RaspyJack plugin.

Demonstrates how to:
    * poll time in on_tick
    * draw a small overlay widget (clock) in top right corner
    * react to a button press (KEY3_PIN toggles seconds display)

Configuration now lives in ``plugins/plugins_conf.json``::

        {
            "example_plugin": {
                "enabled": true,
                "priority": 50,
                "options": {"show_seconds": false, "text_color": "white"}
            }
        }

Options used:
    * show_seconds (bool) – initial display mode
    * text_color (str) – PIL color name/hex for the overlay text
"""
from __future__ import annotations

import time
from .base import Plugin


class ExamplePlugin(Plugin):
    name = "ExampleClock"
    priority = 50

    def on_load(self, ctx: dict) -> None:
        self.ctx = ctx
        # Read configuration options (provided by manager via instance.config)
        opts = getattr(self, 'options', {}) or {}
        self.show_seconds = bool(opts.get('show_seconds', False))
        self.text_color = opts.get('text_color', 'white')
        self._last_fmt = ""
        self._last_update = 0
        self.current_time_str = "--:--"
        print("[ExampleClock] Loaded")

    def on_button(self, name: str) -> None:
        if name == "KEY3_PIN":  # toggle seconds display
            self.show_seconds = not self.show_seconds
            print(f"[ExampleClock] Seconds {'ON' if self.show_seconds else 'OFF'}")

    def on_tick(self, dt: float) -> None:
        # update formatted time once per second (or every 0.2s if seconds shown)
        now = time.time()
        interval = 0.2 if self.show_seconds else 1.0
        if now - self._last_update >= interval:
            self._last_update = now
            fmt = "%H:%M:%S" if self.show_seconds else "%H:%M"
            self.current_time_str = time.strftime(fmt)

    def on_render_overlay(self, image, draw) -> None:
        # Skip if status bar already showing a message (avoid clutter)
        try:
            if 'status_bar' in getattr(self, 'ctx', {}) and self.ctx['status_bar'].is_busy():
                return
        except Exception:
            pass
        w, h = image.size
        center_x = w // 2
        text_x = center_x - 30
        # Draw a tiny time widget
        draw.text((text_x, 0), self.current_time_str, fill=self.text_color)


plugin = ExamplePlugin()
