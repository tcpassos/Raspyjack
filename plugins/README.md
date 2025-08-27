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
      "timestamp_format": "%Y-%m-%d %H:%M:%S"
    }
  }
}
```

### Configuration Fields:
- **`enabled`**: `true/false` - Enable/disable plugin
- **`priority`**: `number` - Execution order (lower = first)
- **`options`**: `object` - Plugin-specific settings

### Accessing Configuration in Plugin:
```python
def on_load(self, context):
    if self.config:
        self.interval = self.config.get("options", {}).get("interval", 10)
        print(f"Configured interval: {self.interval}")
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

### Example 3: Plugin with Configuration
```json
{
  "tools_plugin": {
    "enabled": true,
    "priority": 60,
    "options": {
      "timeout": 2,
      "ports": [22, 80, 443, 8080],
      "log_scans": true
    }
  }
}
```

**In plugin:**
```python
def on_load(self, context):
    opts = self.config.get("options", {})
    self.timeout = opts.get("timeout", 1)
    self.ports = opts.get("ports", [80, 443])
    self.log_scans = opts.get("log_scans", False)
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

---

## 📝 Included Plugins

### `battery_status_plugin`
- **Function**: Monitor system battery
- **HUD**: Shows percentage and status
- **Configuration**: Check interval

### `temperature_plugin` 
- **Function**: Monitor CPU temperature
- **HUD**: Visual alert if overheating
- **Configuration**: Temperature threshold

### `discord_notifier_plugin`
- **Function**: Discord notifications for scans
- **Commands**: `DISCORD_MESSAGE`, `DISCORD_EXFIL`
- **Configuration**: Webhook URL

---

**💡 Tip**: Study existing plugins in `plugins/` to see practical implementation examples!

---

*Developed for RaspyJack - Educational offensive security toolkit*