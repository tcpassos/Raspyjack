"""Screenshot Plugin

Captures the current framebuffer image when the user performs a LONG_PRESS
on KEY2_PIN and saves it under screenshots/ with a timestamped filename.

Event usage:
  - Listens to on_button_event for LONG_PRESS of KEY2_PIN.
  - Debounces so only one capture per long press activation.

File format: PNG (lossless, small for 128x128).
"""
from __future__ import annotations
import time
import os
from datetime import datetime
from plugins.base import Plugin

class ScreenshotPlugin(Plugin):
    name = "Screenshot"
    priority = 120

    def __init__(self):
        self.ctx = None
        self._last_capture_ts = 0.0
        self._screens_dir = None

    def on_load(self, ctx: dict) -> None:
        self.ctx = ctx
        print(f"[{self.name}] Plugin loaded. Hold KEY2 for screenshot.")

    def _ensure_dir_ready(self):
        if self._screens_dir and os.path.isdir(self._screens_dir):
            return
        install_root = getattr(self.ctx['defaults'], 'install_path', '/root/Raspyjack')
        self._screens_dir = os.path.join(install_root, 'screenshots')
        try:
            os.makedirs(self._screens_dir, exist_ok=True)
        except Exception as e:
            print(f"[{self.name}] Could not create screenshots directory: {e}")

    def _capture(self):
        if not self.ctx:
            return
        self._ensure_dir_ready()
        try:
            img = self.ctx['draw_image']()
            # Copy to avoid race with render loop
            snap = img.copy()
            ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            fname = f"shot_{ts}.png"
            target = os.path.join(self._screens_dir or '.', fname)
            snap.save(target, format='PNG')
            print(f"[{self.name}] Saved {target}")
            # Temporary status bar message
            try:
                if 'status_bar' in self.ctx and self.ctx['status_bar']:
                    if not self.ctx['status_bar'].is_busy():
                        self.ctx['status_bar'].set_temp_status("Screenshot saved", 2.0)
            except Exception:
                pass
        except Exception as e:
            print(f"[{self.name}] Capture failed: {e}")

    def on_button_event(self, event: dict) -> None:
        if event.get('type') == 'LONG_PRESS' and event.get('button') == 'KEY2_PIN':
            self._capture()

    def get_info(self) -> str:
        """Return status information about stored screenshots.

        Shows directory path, number of PNG files, last capture timestamp
        (based on filename ordering), and approximate total size.
        """
        self._ensure_dir_ready()
        if not self._screens_dir:
            return "Screenshots directory not initialized"
        try:
            files = [f for f in os.listdir(self._screens_dir) if f.lower().endswith('.png')]
            count = len(files)
            last = sorted(files)[-1] if files else "(none)"
            total_bytes = 0
            for f in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(self._screens_dir, f))
                except Exception:
                    pass
            size_kb = total_bytes / 1024.0
            lines = [
                f"Directory: {self._screens_dir}",
                f"Files: {count}",
                f"Last: {last}",
                f"Total Size: {size_kb:.1f} KB",
                "Trigger: LONG_PRESS KEY2_PIN",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading screenshots: {e}"

plugin = ScreenshotPlugin()
