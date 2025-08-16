"""Battery status overlay plugin for Waveshare UPS HAT (C).

Reads INA219 over I2C and renders a tiny battery icon + percentage in the
upper‑right corner without disturbing the existing status line.

Configuration example (plugins_conf.json):
{
  "battery_status_plugin": {
    "enabled": true,
    "priority": 40,
    "options": {
      "i2c_bus": 1,
      "address": 0x43,
      "refresh_interval": 2.0,      # seconds between sensor polls
      "voltage_min": 3.0,           # 0% reference (V)
      "voltage_max": 4.2            # 100% reference (V)
    }
  }
}
"""
from __future__ import annotations
import time

try:
    import smbus  # type: ignore
except Exception:  # Allow running without I2C libs
    smbus = None

from .base import Plugin

# INA219 registers / constants (subset needed)
_REG_CONFIG       = 0x00
_REG_SHUNTVOLTAGE = 0x01
_REG_BUSVOLTAGE   = 0x02
_REG_POWER        = 0x03
_REG_CURRENT      = 0x04
_REG_CALIBRATION  = 0x05

class _INA219:
    """Minimal INA219 helper (only what we need)."""
    def __init__(self, i2c_bus: int = 1, addr: int = 0x43):
        if smbus is None:
            raise RuntimeError("smbus not available")
        self.bus = smbus.SMBus(i2c_bus)
        self.addr = addr
        self._current_lsb = 0.1524
        self._power_lsb = 0.003048
        self._cal_value = 26868
        self._configure()

    def _write(self, reg: int, value: int):
        self.bus.write_i2c_block_data(self.addr, reg, [(value >> 8) & 0xFF, value & 0xFF])

    def _read16(self, reg: int) -> int:
        data = self.bus.read_i2c_block_data(self.addr, reg, 2)
        return (data[0] << 8) | data[1]

    def _configure(self):
        # Write calibration then config (values copied from reference code)
        self._write(_REG_CALIBRATION, self._cal_value)
        # Config bitfield assembled same as reference (16V, gain /2, 12bit x32 samples both, continuous)
        config = (0x00 << 13) | (0x01 << 11) | (0x0D << 7) | (0x0D << 3) | 0x07
        self._write(_REG_CONFIG, config)

    def bus_voltage(self) -> float:
        self._write(_REG_CALIBRATION, self._cal_value)
        # discard first read then convert
        _ = self._read16(_REG_BUSVOLTAGE)
        value = self._read16(_REG_BUSVOLTAGE)
        return (value >> 3) * 0.004

    def shunt_voltage(self) -> float:
        self._write(_REG_CALIBRATION, self._cal_value)
        value = self._read16(_REG_SHUNTVOLTAGE)
        if value > 32767:
            value -= 65535
        return value * 0.00001  # 0.01mV -> V

    def current_a(self) -> float:
        value = self._read16(_REG_CURRENT)
        if value > 32767:
            value -= 65535
        return (value * self._current_lsb) / 1000.0

    def power_w(self) -> float:
        self._write(_REG_CALIBRATION, self._cal_value)
        value = self._read16(_REG_POWER)
        if value > 32767:
            value -= 65535
        return value * self._power_lsb

class BatteryStatusPlugin(Plugin):
    name = "BatteryStatus"
    priority = 40  # draw before clock (which was 50)

    def on_load(self, ctx: dict) -> None:
        self.ctx = ctx
        opts = getattr(self, 'options', {}) or {}
        self.addr = int(opts.get('address', 0x43))
        self.bus_num = int(opts.get('i2c_bus', 1))
        self.refresh_interval = float(opts.get('refresh_interval', 2.0))
        self.v_min = float(opts.get('voltage_min', 3.0))
        self.v_max = float(opts.get('voltage_max', 4.2))
        self._last_poll = 0.0
        self.percent = None
        self.ok = False
        try:
            self.sensor = _INA219(self.bus_num, self.addr)
            self.ok = True
        except Exception as e:
            print(f"[BatteryStatus] Disabled (I2C init failed): {e}")
            self.sensor = None

    def on_tick(self, dt: float) -> None:
        if not self.ok or self.sensor is None:
            return
        now = time.time()
        if now - self._last_poll < self.refresh_interval:
            return
        self._last_poll = now
        try:
            v = self.sensor.bus_voltage()  # load voltage
            pct = (v - self.v_min) / (self.v_max - self.v_min) * 100.0
            pct = max(0.0, min(100.0, pct))
            self.percent = pct
        except Exception as e:
            print(f"[BatteryStatus] read error: {e}")
            self.percent = None

    def on_render_overlay(self, image, draw) -> None:
        # Skip if we don't yet have a reading
        if self.percent is None:
            return
        # Skip if status bar already showing a message (avoid clutter)
        try:
            if 'status_bar' in getattr(self, 'ctx', {}) and self.ctx['status_bar'].is_busy():
                return
        except Exception:
            pass
        w, h = image.size
        # Battery icon dimensions
        icon_w = 18
        icon_h = 8
        x2 = w - 4
        x1 = x2 - icon_w
        y1 = 0
        y2 = y1 + icon_h
        # Outline
        draw.rectangle((x1, y1, x2 - 3, y2), outline="white", fill=None)
        # Tip
        draw.rectangle((x2 - 3, y1 + 2, x2, y2 - 2), outline="white", fill="white")
        # Fill level
        inner_w = icon_w - 6
        fill_w = int(inner_w * (self.percent / 100.0))
        if fill_w > 0:
            draw.rectangle((x1 + 2, y1 + 2, x1 + 2 + fill_w, y2 - 2), fill="white")
        # Percentage text (small, right-aligned above or below)
        pct_text = f"{int(self.percent):02d}%"
        text_x = x1 - 3 - (len(pct_text) * 5)
        if text_x < 0:
            text_x = 0
        draw.text((text_x, y1), pct_text, fill="white")

plugin = BatteryStatusPlugin()
