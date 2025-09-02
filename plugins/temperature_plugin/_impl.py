from __future__ import annotations
import time
from plugins.base import Plugin

class TemperaturePlugin(Plugin):

    def on_load(self, ctx: dict) -> None:
        self.ctx = ctx
        opts = getattr(self, 'options', {}) or {}
        
        # Fixed refresh interval (no config option)
        self.refresh_interval = 2.0
        
        self.color = opts.get('text_color', 'white')
        self.show_unit = self.get_config_value("show_unit", True)
        self.enable_display = self.get_config_value("enable_display", True)
        
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
        if not self.ok or not self.get_config_value("enable_display", True):
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
        if not self.ok or not self.get_config_value("enable_display", True):
            return
            
        try:
            if 'status_bar' in self.ctx and self.ctx['status_bar'].is_busy():
                return
        except Exception:
            pass
            
        unit = "°C" if self.get_config_value("show_unit", True) else ""
        temp_text = f"{self.temperature:.0f}{unit}"
        
        font = self.ctx.get('font', None)
        draw.text((2, 0), temp_text, fill=self.color, font=font)
    
    def on_config_changed(self, key: str, old_value, new_value) -> None:
        """React to configuration changes."""
        if key == "enable_display":
            status = "enabled" if new_value else "disabled"
            print(f"[{self.name}] Temperature display {status}")
        elif key == "show_unit":
            status = "shown" if new_value else "hidden"
            print(f"[{self.name}] Temperature unit {status}")
    
    def get_info(self) -> str:
        if not self.ok:
            return "Temperature sensor not available\nPath: /sys/class/thermal/thermal_zone0/temp\nStatus: Sensor not found"
        
        # Get current configuration
        enable_display = self.get_config_value("enable_display", True)
        show_unit = self.get_config_value("show_unit", True)
        
        status_lines = [
            f"Current Temperature: {self.temperature:.1f}°C",
            f"Sensor Status: Active",
            "",
            "Current Configuration:",
            f"• HUD Display: {'ON' if enable_display else 'OFF'}",
            f"• Show Unit: {'ON' if show_unit else 'OFF'}",
            "",
            f"Display Color: {self.color}",
            f"Refresh Interval: {self.refresh_interval}s",
            f"Last Poll: {time.strftime('%H:%M:%S', time.localtime(self._last_poll))}"
        ]
        
        return "\n".join(status_lines)

plugin = TemperaturePlugin()
