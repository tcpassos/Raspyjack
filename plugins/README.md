# 🧩 Plugin System - RaspyJack

Modular plugin system for RaspyJack that allows adding functionality without modifying the main code.

## 📋 Table of Contents
- [Plugin Structure](#-plugin-structure)
- [Configuration](#-configuration)
- [Available Callbacks](#-available-callbacks)
- [Context Helpers](#-context-helpers)
- [Bin Commands](#-bin-commands)
- [Complete Examples](#-complete-examples)
- [Development](#-development)

---

## 📁 Plugin Structure

Each plugin is a **Python package** with standardized structure:

```
plugins/
  my_plugin/
    __init__.py        # Entry point (required)
    _impl.py          # Plugin implementation (recommended)
    bin/              # Globally exposed executables (optional)
      MY_COMMAND
      OTHER_CMD
    helpers/          # Auxiliary modules (optional)
      utils.py
      constants.py
    config.json       # Specific configuration (optional)
    README.md         # Plugin documentation (optional)
```

### `__init__.py` File (Required)
```python
from ._impl import plugin
```

### `_impl.py` File (Implementation)
```python
from plugins.base import Plugin

class MyPlugin(Plugin):
    name = "MyPlugin"
    priority = 100
    
    def on_load(self, context):
        print(f"[{self.name}] Plugin loaded!")
    
    def get_info(self):
        return "My custom plugin"

plugin = MyPlugin()
```

---

## ⚙️ Configuration

Configure plugins in `plugins/plugins_conf.json`:

```json
{
  "my_plugin": {
    "enabled": true,
    "priority": 50,
    "options": {
      "interval": 5,
      "text_color": "white",
      "show_details": false
    }
  },
  "discord_notifier_plugin": {
    "enabled": true,
    "priority": 200,
    "options": {
      "nmap_notifications": true
    }
  }
}
```

### Configuration Fields:
- **`enabled`**: `true/false` - Enable/disable plugin
- **`priority`**: `number` - Execution order (lower = first)
- **`options`**: `object` - Plugin-specific settings

### Plugin Configuration Schema

Plugins can expose boolean configurations that appear as checkboxes in the UI menu:

```python
class MyPlugin(Plugin):
    def get_config_schema(self) -> dict:
        """Define plugin configuration options for UI."""
        return {
            "enable_feature": {
                "type": "boolean",
                "label": "Enable Feature",
                "description": "Enable this plugin feature",
                "default": True
            },
            "show_notifications": {
                "type": "boolean", 
                "label": "Show Notifications",
                "description": "Display notifications in UI",
                "default": False
            }
        }
    
    def get_config_value(self, key: str, default=None):
        """Get current configuration value."""
        if hasattr(self, 'config') and self.config:
            return self.config.get('options', {}).get(key, default)
        return default
    
    def set_config_value(self, key: str, value) -> None:
        """Set configuration value (handled by PluginManager)."""
        pass
    
    def on_config_changed(self, key: str, old_value, new_value) -> None:
        """Called when configuration changes via UI."""
        print(f"[{self.name}] Config {key}: {old_value} -> {new_value}")
```

### UI Integration

Configuration options automatically appear in the plugin submenu as interactive checkboxes:

- **✅ Menu Integration**: Boolean configs become CheckboxMenuItem instances
- **🔄 Real-time Updates**: Changes are immediately saved and applied
- **💾 Persistent Storage**: Settings saved to `plugins_conf.json`
- **🔔 Callbacks**: `on_config_changed()` called when values change

### Accessing Configuration in Plugin:
```python
def on_load(self, context):
    # Use get_config_value() with defaults
    self.interval = self.get_config_value("interval", 10)
    self.enabled = self.get_config_value("enable_feature", True)
    print(f"Configured interval: {self.interval}")

def on_tick(self, dt):
    # Check configuration before actions
    if not self.get_config_value("enable_feature", True):
        return  # Feature disabled
    
    # Your plugin logic here
    pass
```

---

## 🔄 Available Callbacks

All callbacks are **optional**. Implement only what you need:

### Lifecycle
```python
def on_load(self, context: dict) -> None:
    """Called once when loading the plugin"""
    self.context = context
    print("Plugin initialized!")

def on_unload(self) -> None:
    """Called when unloading (shutdown)"""
    print("Plugin finalized!")
```

### Periodic Events
```python
def on_tick(self, dt: float) -> None:
    """Called periodically (~1x per second)"""
    # IMPORTANT: Keep fast and non-blocking!
    self.counter += dt
```

### Hardware Interaction
```python
def on_button(self, name: str) -> None:
    """Called when physical button is pressed"""
    if name == "KEY_UP_PIN":
        print("UP button pressed!")
```

### Rendering
```python
def on_render_overlay(self, image, draw) -> None:
    """Draw overlay on HUD"""
    # Draw only small elements (HUD)
    draw.text((100, 10), "Status: OK", fill='green')
```

### Payload Execution
```python
def on_before_exec_payload(self, payload_name: str) -> None:
    """Before executing payload"""
    print(f"Executing: {payload_name}")

def on_after_exec_payload(self, payload_name: str, success: bool) -> None:
    """After payload execution"""
    status = "✅" if success else "❌"
    print(f"{status} {payload_name}")
```

### Scans (Nmap)
```python
def on_before_scan(self, label: str, args: list[str]) -> None:
    """Before Nmap scan"""
    print(f"Starting scan: {label}")

def on_after_scan(self, label: str, args: list[str], result_path: str) -> None:
    """After Nmap scan completion"""
    print(f"Scan saved to: {result_path}")
```

### Information
```python
def get_info(self) -> str:
    """Return plugin status/info for UI"""
    return "Plugin working perfectly!"
```

---

## 🛠 Context Helpers

The `context` parameter in `on_load()` provides access to system functionality:

```python
def on_load(self, context):
    self.context = context
    
    # Execute payload
    self.context['exec_payload']('my_script.py')
    
    # Check system state
    if self.context['is_responder_running']():
        print("Responder is active")
    
    # Access graphical interface
    menu = self.context['get_menu']()
    status_bar = self.context['status_bar']
    status_bar.set_temp_status("Plugin active", 3)
    
    # Draw on screen
    image = self.context['draw_image']()  # PIL base Image
    draw = self.context['draw_obj']()     # PIL ImageDraw
```

### Available Context Keys:
- `exec_payload(name)` - Execute payload script
- `get_menu()` - Get current menu
- `is_responder_running()` - Responder status
- `is_mitm_running()` - MITM status
- `draw_image()` - PIL base image
- `draw_obj()` - PIL ImageDraw object
- `status_bar` - StatusBar instance

---

## 📦 Bin Commands

Plugins can expose globally executable commands:

### 1. Create Executable
```bash
# plugins/my_plugin/bin/MY_CMD
#!/usr/bin/env python3
"""My custom command"""

from plugins.my_plugin.helpers.utils import do_something

def main():
    print("Running my command!")
    do_something()

if __name__ == "__main__":
    main()
```

### 2. Automatic Exposure
When plugin is loaded, `MY_CMD` becomes available at:
- `bin/MY_CMD` (symlink or copy)
- Can be used by other payloads

### 3. Exposure Logs
```
[PLUGIN] Created symlink: bin/MY_CMD -> /path/to/plugins/my_plugin/bin/MY_CMD
```

### 4. Automatic PYTHONPATH
Scripts executed via `payload_executor.py` have automatic access to modules:
```python
# Works automatically in payloads
from plugins.my_plugin.helpers.utils import function
```

---

## 🎯 Complete Examples

### Example 1: Simple Status Plugin
```
plugins/
  status_plugin/
    __init__.py
    _impl.py
```

**`__init__.py`:**
```python
from ._impl import plugin
```

**`_impl.py`:**
```python
from plugins.base import Plugin
import time

class StatusPlugin(Plugin):
    name = "Status"
    priority = 30
    
    def on_load(self, context):
        self.start_time = time.time()
    
    def on_render_overlay(self, image, draw):
        uptime = int(time.time() - self.start_time)
        draw.text((0, 0), f"Uptime: {uptime}s", fill='white')
    
    def get_info(self):
        return f"Active for {int(time.time() - self.start_time)} seconds"

plugin = StatusPlugin()
```

### Example 2: Plugin with Bin Commands
```
plugins/
  tools_plugin/
    __init__.py
    _impl.py
    bin/
      SCAN_PORTS
      CHECK_HOST
    helpers/
      scanner.py
```

**`bin/SCAN_PORTS`:**
```python
#!/usr/bin/env python3
import sys
from plugins.tools_plugin.helpers.scanner import scan_host

def main():
    if len(sys.argv) < 2:
        print("Usage: SCAN_PORTS <host>")
        sys.exit(1)
    
    host = sys.argv[1]
    ports = scan_host(host)
    print(f"Open ports on {host}: {ports}")

if __name__ == "__main__":
    main()
```

**`helpers/scanner.py`:**
```python
import socket

def scan_host(host, ports=[22, 80, 443]):
    open_ports = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        if result == 0:
            open_ports.append(port)
        sock.close()
    return open_ports
```

### Example 3: Plugin with UI Configuration System
```
plugins/
  configurable_plugin/
    __init__.py
    _impl.py
```

**`_impl.py`:**
```python
from plugins.base import Plugin
import time

class ConfigurablePlugin(Plugin):
    name = "ConfigurablePlugin"
    priority = 50
    
    def __init__(self):
        super().__init__()
        self.counter = 0
        self.last_notify = 0
    
    def get_config_schema(self) -> dict:
        """Define UI configuration options."""
        return {
            "enable_monitoring": {
                "type": "boolean",
                "label": "Enable Monitoring",
                "description": "Enable background monitoring",
                "default": True
            },
            "show_overlay": {
                "type": "boolean",
                "label": "Show HUD Overlay", 
                "description": "Display information on screen",
                "default": True
            },
            "enable_notifications": {
                "type": "boolean",
                "label": "Enable Notifications",
                "description": "Show status notifications",
                "default": False
            }
        }
    
    def on_load(self, context):
        self.context = context
        print(f"[{self.name}] Loaded with configuration system")
    
    def on_tick(self, dt):
        # Check if monitoring is enabled
        if not self.get_config_value("enable_monitoring", True):
            return
        
        self.counter += dt
        
        # Check if notifications are enabled
        if self.get_config_value("enable_notifications", False):
            if time.time() - self.last_notify > 10:  # Every 10 seconds
                print(f"[{self.name}] Monitoring active: {self.counter:.1f}s")
                self.last_notify = time.time()
    
    def on_render_overlay(self, image, draw):
        # Check if overlay is enabled
        if not self.get_config_value("show_overlay", True):
            return
        
        if self.get_config_value("enable_monitoring", True):
            draw.text((100, 20), f"Monitor: {self.counter:.1f}s", fill='yellow')
    
    def on_config_changed(self, key: str, old_value, new_value):
        """React to configuration changes immediately."""
        print(f"[{self.name}] Config changed: {key} = {new_value}")
        
        if key == "enable_monitoring":
            if new_value:
                print(f"[{self.name}] Monitoring enabled")
                self.counter = 0  # Reset counter
            else:
                print(f"[{self.name}] Monitoring disabled")
        
        elif key == "show_overlay":
            status = "enabled" if new_value else "disabled"
            print(f"[{self.name}] HUD overlay {status}")
        
        elif key == "enable_notifications":
            status = "enabled" if new_value else "disabled"
            print(f"[{self.name}] Notifications {status}")
    
    def get_info(self):
        # Show current configuration status
        monitoring = self.get_config_value("enable_monitoring", True)
        overlay = self.get_config_value("show_overlay", True)
        notifications = self.get_config_value("enable_notifications", False)
        
        info_lines = [
            f"Counter: {self.counter:.1f}s",
            "",
            "Configuration:",
            f"• Monitoring: {'ON' if monitoring else 'OFF'}",
            f"• HUD Overlay: {'ON' if overlay else 'OFF'}",
            f"• Notifications: {'ON' if notifications else 'OFF'}",
        ]
        return "\n".join(info_lines)

plugin = ConfigurablePlugin()
```

**Configuration appears automatically in menu:**
```
Plugins → ConfigurablePlugin →
  ✓ Enable Plugin
  Show Information
  ─ Configuration ─
  [X] Enable Monitoring      ← CheckboxMenuItem
  [X] Show HUD Overlay       ← CheckboxMenuItem  
  [ ] Enable Notifications   ← CheckboxMenuItem
```

### Example 4: Simplified Plugin Configurations

Current included plugins use simplified, focused configurations:

**Discord Plugin** (`discord_notifier_plugin`):
```python
def get_config_schema(self):
    return {
        "nmap_notifications": {
            "type": "boolean",
            "label": "Nmap Notifications", 
            "description": "Send Discord notifications when Nmap scans complete",
            "default": True
        }
    }
```

**Temperature Plugin** (`temperature_plugin`):
```python
def get_config_schema(self):
    return {
        "enable_display": {
            "type": "boolean",
            "label": "Show Temperature HUD",
            "description": "Display temperature in corner of screen", 
            "default": True
        },
        "show_unit": {
            "type": "boolean",
            "label": "Show Temperature Unit",
            "description": "Display °C unit with temperature value",
            "default": True
        }
    }
```

**Battery Plugin** (`battery_status_plugin`):
```python
def get_config_schema(self):
    return {
        "show_percentage": {
            "type": "boolean",
            "label": "Show Battery Percentage",
            "description": "Display battery percentage in overlay",
            "default": True
        },
        "show_icon": {
            "type": "boolean", 
            "label": "Show Battery Icon",
            "description": "Display battery status icon",
            "default": True
        },
        "enable_monitoring": {
            "type": "boolean",
            "label": "Enable Battery Monitoring", 
            "description": "Monitor battery status via I2C",
            "default": True
        }
    }
```

---

## 🚀 Development

### Recommended Structure
1. **Separate logic**: Use `_impl.py` for implementation
2. **Organized helpers**: Group utilities in `helpers/`
3. **Useful commands**: Expose tools via `bin/`
4. **Flexible configuration**: Use `options` for customizations

### Best Practices
- ✅ **Fast callbacks**: `on_tick()` should be non-blocking
- ✅ **Error handling**: Always use try/except
- ✅ **Informative logs**: Use `print()` for debugging
- ✅ **Spaced priorities**: Use 10, 20, 30... for easy insertions
- ✅ **Default configuration**: Always provide default values
- ✅ **Configuration schema**: Define clear config schemas for UI integration
- ✅ **Boolean configs**: Use boolean types for checkbox integration
- ✅ **Descriptive labels**: Provide user-friendly labels for config options
- ✅ **Config validation**: Check config values before using them
- ✅ **Change notifications**: Implement `on_config_changed()` for immediate updates

### Configuration Guidelines
- **Use clear labels**: "Enable Feature" not "feature_enabled"
- **Provide descriptions**: Help users understand each option
- **Sensible defaults**: Plugins should work out-of-the-box
- **Check before use**: Always validate config values in callbacks
- **Handle changes**: Implement `on_config_changed()` for real-time updates

### Plugin Lifecycle with Configuration
```python
1. Plugin loaded → on_load() called
2. Config schema retrieved → get_config_schema()
3. UI menu built with checkboxes
4. User toggles checkbox → on_toggle callback
5. Config updated and saved → set_config_value()
6. Plugin notified → on_config_changed()
7. Plugin behavior adapts immediately
```

---

## 📝 Included Plugins

### `battery_status_plugin`
- **Function**: Monitor system battery with INA219 sensor
- **HUD**: Shows percentage, icon, and voltage status
- **Configuration Options**:
  - `show_percentage`: Display battery percentage (default: true)
  - `show_icon`: Show battery icon indicator (default: true) 
  - `enable_monitoring`: Enable battery monitoring (default: true)
- **Info Display**: Real-time voltage, current, and power readings

### `temperature_plugin` 
- **Function**: Monitor CPU temperature with thermal sensors
- **HUD**: Temperature display in corner overlay
- **Configuration Options**:
  - `enable_display`: Show temperature in HUD (default: true)
  - `show_unit`: Display °C unit with temperature (default: true)
- **Info Display**: Current CPU temperature and sensor status

### `discord_notifier_plugin`
- **Function**: Send Discord notifications for completed Nmap scans
- **Commands**: `DISCORD_MESSAGE`, `DISCORD_EXFIL`
- **Configuration Options**:
  - `nmap_notifications`: Send notifications when scans complete (default: true)
- **Features**: 
  - Automatic file attachments
  - Embedded scan results with timestamps
  - Webhook configuration via `discord_webhook.txt`
  - Network interface detection

### Plugin Menu Navigation

Access plugin configurations through the main menu:

1. **Main Menu** → **Plugins**
2. Select plugin (shows ✓ if enabled, ✗ if disabled)
3. **Plugin Submenu** options:
   - `Enable/Disable Plugin` - Toggle plugin activation
   - `Show Information` - View plugin status and details
   - `─ Configuration ─` - Separator for config options
   - **Checkbox Options** - Interactive boolean settings
4. **Save & Restart** - Apply changes and reload plugins

### Configuration Management

- **Real-time Updates**: Checkbox changes immediately update plugin behavior
- **Persistent Storage**: All settings saved to `plugins_conf.json`
- **Plugin Reload**: Use "Save & Restart" to apply enable/disable changes
- **Default Values**: Plugins provide sensible defaults for all options

---

**💡 Tip**: Study existing plugins in `plugins/` to see practical implementation examples!

---

*Developed for RaspyJack - Educational offensive security toolkit*