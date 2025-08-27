from __future__ import annotations
import time
from plugins.base import Plugin

class TemperaturePlugin(Plugin):
    name = "Temperature"
    priority = 30

    def on_load(self, ctx: dict) -> None:
        self.ctx = ctx
        opts = getattr(self, 'options', {}) or {}
        self.refresh_interval = float(opts.get('refresh_interval', 2.0))
        self.color = opts.get('text_color', 'white')
        self.show_unit = bool(opts.get('show_unit', True))
        self._last_poll = 0.0
        self.temperature = 0.0
        self.ok = self._check_sensor()

    def _check_sensor(self) -> bool:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", 'r') as f:
                f.read()
            return True
        except Exception as e:
            print(f"[{self.name}] Sensor not found: {e}")
            return False

    def _read_temp(self) -> float:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read()) / 1000.0

    def on_tick(self, dt: float) -> None:
        if not self.ok:
            return
        now = time.time()
        if now - self._last_poll >= self.refresh_interval:
            self._last_poll = now
            try:
                self.temperature = self._read_temp()
            except Exception as e:
                print(f"[{self.name}] Read error: {e}")
                self.temperature = 0.0

    def on_render_overlay(self, image, draw) -> None:
        if not self.ok:
            return
        try:
            if 'status_bar' in self.ctx and self.ctx['status_bar'].is_busy():
                return
        except Exception:
            pass
        unit = "°C" if self.show_unit else ""
        temp_text = f"{self.temperature:.0f}{unit}"
        font = self.ctx.get('font', None)
        draw.text((2, 0), temp_text, fill=self.color, font=font)

plugin = TemperaturePlugin()
