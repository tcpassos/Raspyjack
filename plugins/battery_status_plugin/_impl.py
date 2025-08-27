from __future__ import annotations
import time

try:
    import smbus  # type: ignore
except Exception:  # Allow running without I2C libs
    smbus = None

from plugins.base import Plugin

_REG_CONFIG       = 0x00
_REG_SHUNTVOLTAGE = 0x01
_REG_BUSVOLTAGE   = 0x02
_REG_POWER        = 0x03
_REG_CURRENT      = 0x04
_REG_CALIBRATION  = 0x05

class _INA219:
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
        self._write(_REG_CALIBRATION, self._cal_value)
        config = (0x00 << 13) | (0x01 << 11) | (0x0D << 7) | (0x0D << 3) | 0x07
        self._write(_REG_CONFIG, config)

    def bus_voltage(self) -> float:
        self._write(_REG_CALIBRATION, self._cal_value)
        _ = self._read16(_REG_BUSVOLTAGE)
        value = self._read16(_REG_BUSVOLTAGE)
        return (value >> 3) * 0.004

    def shunt_voltage(self) -> float:
        self._write(_REG_CALIBRATION, self._cal_value)
        value = self._read16(_REG_SHUNTVOLTAGE)
        if value > 32767:
            value -= 65535
        return value * 0.00001

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
    priority = 40

    def get_config_schema(self) -> dict:
        """Return configuration schema for Battery Status plugin."""
        return {
            "show_percentage": {
                "type": "boolean",
                "label": "Show Battery Percentage",
                "description": "Display battery percentage text in overlay",
                "default": True
            },
            "show_icon": {
                "type": "boolean",
                "label": "Show Battery Icon",
                "description": "Display battery icon graphic in overlay", 
                "default": True
            },
            "enable_monitoring": {
                "type": "boolean",
                "label": "Enable Battery Monitoring",
                "description": "Enable battery status monitoring and overlay display",
                "default": True
            }
        }

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
        if not self.ok or self.sensor is None or not self.get_config_value("enable_monitoring", True):
            return
        now = time.time()
        if now - self._last_poll < self.refresh_interval:
            return
        self._last_poll = now
        try:
            v = self.sensor.bus_voltage()
            pct = (v - self.v_min) / (self.v_max - self.v_min) * 100.0
            pct = max(0.0, min(100.0, pct))
            self.percent = pct
        except Exception as e:
            print(f"[BatteryStatus] read error: {e}")
            self.percent = None

    def on_render_overlay(self, image, draw) -> None:
        if (self.percent is None or 
            not self.get_config_value("enable_monitoring", True) or 
            (not self.get_config_value("show_percentage", True) and not self.get_config_value("show_icon", True))):
            return
            
        try:
            if 'status_bar' in getattr(self, 'ctx', {}) and self.ctx['status_bar'].is_busy():
                return
        except Exception:
            pass
            
        w, h = image.size
        
        # Show battery icon if enabled
        if self.get_config_value("show_icon", True):
            icon_w = 18
            icon_h = 8
            x2 = w - 4
            x1 = x2 - icon_w
            y1 = 0
            y2 = y1 + icon_h
            draw.rectangle((x1, y1, x2 - 3, y2), outline="white", fill=None)
            draw.rectangle((x2 - 3, y1 + 2, x2, y2 - 2), outline="white", fill="white")
            inner_w = icon_w - 6
            fill_w = int(inner_w * (self.percent / 100.0))
            if fill_w > 0:
                draw.rectangle((x1 + 2, y1 + 2, x1 + 2 + fill_w, y2 - 2), fill="white")
            
            # Show percentage text if enabled
            if self.get_config_value("show_percentage", True):
                pct_text = f"{int(self.percent):02d}%"
                text_x = x1 - 3 - (len(pct_text) * 5)
                if text_x < 0:
                    text_x = 0
                draw.text((text_x, y1), pct_text, fill="white")
        elif self.get_config_value("show_percentage", True):
            # Show only percentage text (no icon)
            pct_text = f"{int(self.percent):02d}%"
            text_x = w - 30
            draw.text((text_x, 0), pct_text, fill="white")

    def on_config_changed(self, key: str, old_value, new_value) -> None:
        """React to configuration changes."""
        if key == "enable_monitoring":
            status = "enabled" if new_value else "disabled"
            print(f"[{self.name}] Battery monitoring {status}")
        elif key == "show_percentage":
            status = "enabled" if new_value else "disabled"
            print(f"[{self.name}] Percentage display {status}")
        elif key == "show_icon":
            status = "enabled" if new_value else "disabled"
            print(f"[{self.name}] Icon display {status}")
    
    def get_info(self) -> str:
        if not self.ok or self.sensor is None:
            info_lines = [
                "Battery monitoring unavailable",
                f"I2C Bus: {self.bus_num}",
                f"Address: 0x{self.addr:02X}",
                "Status: Sensor not found",
                "",
                "Requirements:",
                "• INA219 current sensor",
                "• I2C connection",
                "• smbus Python library"
            ]
            return "\n".join(info_lines)
        
        try:
            voltage = self.sensor.bus_voltage()
            current = self.sensor.current_a()
            power = self.sensor.power_w()
            shunt_v = self.sensor.shunt_voltage()
        except Exception as e:
            voltage = current = power = shunt_v = 0.0
        
        # Get current configuration
        enable_monitoring = self.get_config_value("enable_monitoring", True)
        show_percentage = self.get_config_value("show_percentage", True)
        show_icon = self.get_config_value("show_icon", True)
        
        info_lines = [
            f"Battery Level: {self.percent:.1f}%" if self.percent is not None else "Battery Level: Reading...",
            f"Bus Voltage: {voltage:.3f}V",
            f"Current: {current:.3f}A",
            f"Power: {power:.3f}W",
            f"Shunt Voltage: {shunt_v:.3f}V",
            "",
            "Current Configuration:",
            f"• Monitoring: {'ON' if enable_monitoring else 'OFF'}",
            f"• Show Percentage: {'ON' if show_percentage else 'OFF'}",
            f"• Show Icon: {'ON' if show_icon else 'OFF'}",
            "",
            "Hardware Configuration:",
            f"I2C Address: 0x{self.addr:02X}",
            f"I2C Bus: {self.bus_num}",
            f"Refresh Rate: {self.refresh_interval}s",
            f"Voltage Range: {self.v_min}V - {self.v_max}V",
            "",
            f"Sensor Status: {'Active' if self.ok else 'Error'}",
            f"Last Update: {time.strftime('%H:%M:%S', time.localtime(self._last_poll))}"
        ]
        return "\n".join(info_lines)

plugin = BatteryStatusPlugin()
