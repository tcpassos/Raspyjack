# 🧩 Plugin System - RaspyJack

Modular plugin system for RaspyJack that allows adding functionality without modifying the main code.

## 📋 Table of Contents
- [Installation](#-installation)
- [Plugin Structure](#-plugin-structure)
- [Plugin Template](#-plugin-template)
- [Configuration](#-configuration)
- [Available Callbacks](#-available-callbacks)
- [Context Helpers](#-context-helpers)
- [Bin Commands](#-bin-commands)
- [Complete Examples](#-complete-examples)
- [Development](#-development)
- [Event Bus](#-event-bus)
- [Plugin Dependencies](#-plugin-dependencies)
- [Plugin Menu Actions](#-plugin-menu-actions)
 - [Persisting Configuration Changes](#-persisting-configuration-changes)

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

## 📥 Installation

There are **two ways** to add new plugins:

### 1. Manual (development) install
Place your plugin folder under `plugins/` (e.g. `plugins/my_plugin/`) with an `__init__.py` that exposes a `plugin` instance. Restart RaspyJack.

### 2. Archive auto‑install (recommended for deployment)
Drop a compressed archive into the installer directory:

```
plugins/install/
    my_plugin.zip
    toolpack.tar.gz
```

Supported archive types: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`

On startup RaspyJack will:
1. Scan `plugins/install/` for supported archives
2. Safely extract each into a temp directory (path traversal protected)
3. Detect the first package directory containing `__init__.py`
4. Move it into `plugins/<plugin_name>/` (appends `_new`, `_new2`, etc. if name already exists)
5. Add a default config entry (disabled) to `plugins_conf.json`
6. Rename/move the archive:
     - `<name>.done` in `plugins/install/processed/` if successful
     - `<name>.invalid` if no plugin package found
     - `<name>.error` if extraction failed

Example session log excerpt:
```
[PLUGIN] Installed plugin 'status_plugin' from 'status_plugin.zip' -> status_plugin
[PLUGIN] Added new plugin 'status_plugin' to config with defaults (enabled = False)
```

After installation: enable via UI → `Plugins` → select plugin → `Enable Plugin` → `Save & Restart`.

### Packaging a plugin
From inside `plugins/` run (examples):
```bash
zip -r my_plugin.zip my_plugin
tar czf my_plugin.tar.gz my_plugin
```
Copy the archive to `plugins/install/` and restart.

---

## 🧪 Plugin Template

A fully documented reference implementation is provided in `plugins/example_plugin/`.

Template contents:
```
example_plugin/
    __init__.py          # Exposes plugin instance
    _impl.py             # All hook examples + config schema
    helpers/             # (Optional) support modules
        util_example.py
    bin/                 # (Optional) executable tools (auto-exposed to top-level bin/)
        EXAMPLE_CMD
    README.md            # Local docs (optional)
```

### Creating a new plugin from the template
1. Copy the folder:
     ```bash
     cp -r plugins/example_plugin plugins/my_new_plugin
     ```
2. Rename class `ExamplePlugin` → `MyNewPlugin` inside `_impl.py`
3. Change `name = "MyNewPlugin"` and optionally `priority`
4. Adjust `get_config_schema()` with your boolean options
5. Remove hooks you don't need to keep it lean
6. (Optional) Add commands under `bin/` and helpers under `helpers/`
7. Restart RaspyJack → plugin auto‑discovered (disabled by default)
8. Enable in UI → `Plugins` menu

### Exposed features in template
- All lifecycle + event hooks implemented
- Example configuration schema with two boolean flags
- Demonstrates overlay drawing, tick updates, button handling
- `get_info()` output for info viewer
- Sample bin command (`EXAMPLE_CMD`)

### Recommendations when adapting
- Keep overlay output short to avoid conflicts
- Use `on_config_changed()` for recalculating cache/state
- Avoid blocking operations in hooks; spawn threads if needed
- Prefix print logs with `[YourPlugin]` for clarity

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

Plugins declare configuration options via `get_config_schema()`. Each option has:

```
{
    "type": "boolean" | "string" | "list" | "number",
    "label": "Short label",
    "description": "Longer help text",
    "default": <value matching type>
}
```

CURRENT UI LIMITATION:
    Only `boolean` options are rendered as toggleable items in the on-device menu.
    Non-boolean types (`string`, `list`) are still fully supported in the schema,
    auto-added to `plugins_conf.json`, and retrievable through
    `get_config_value()`, but must be edited manually in the JSON file until the
    menu gains editors for those types.

Type semantics:
    - `boolean`: True/False toggle (visible in UI)
    - `string`: Arbitrary text (edit JSON manually)
    - `list`: Typically list of strings (edit JSON manually). Example: payload names.
    - `number`: JSON number (int ou float). Ajuste via arquivo JSON.

Example (multi-type):
```python
def get_config_schema(self):
        return {
                "enable_feature": {
                        "type": "boolean",
                        "label": "Enable Feature",
                        "description": "Turn feature on/off",
                        "default": True
                },
                "interface": {
                        "type": "string",
                        "label": "Interface",
                        "description": "Network interface to monitor (edit JSON)",
                        "default": "eth0"
                },
                "connect_payloads": {
                        "type": "list",
                        "label": "Connect Payloads",
                        "description": "Payloads to run on connect (edit JSON)",
                        "default": []
        },
        "interval_secs": {
            "type": "number",
            "label": "Interval Seconds",
            "description": "Polling interval (edit JSON)",
            "default": 5
                }
        }
```

Below is a simpler boolean-only example used by older plugins:

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

## 🚦 Event Bus

An in-process event bus lets plugins publish and subscribe to named events without
tight coupling.

### Emitting an Event
```python
self.context['plugin_manager'].emit_event('ethernet.connected', interface='eth0', ip='192.168.0.10')
```

### Subscribing to an Event
```python
def on_eth(event_name, data):
        print('Ethernet connected:', data)

def on_load(self, ctx):
        mgr = ctx.get('plugin_manager')
        mgr.subscribe_event('ethernet.connected', on_eth)
```

Handler signature: `handler(event_name: str, data: dict)`.

Current events (core / example):
    - `ethernet.connected` { interface, ip }
    - `ethernet.disconnected` { interface, ip=None }

You can freely define your own event names (recommend dot notation: `module.topic`).

---

## 🔗 Plugin Dependencies

A plugin can declare other plugin modules it depends on via a class attribute `requires`:

```python
class NetActionPlugin(Plugin):
        name = "NetActionPlugin"
        priority = 210
        requires = ['ethernet_hook']  # directory/module names
```

Dependency loading behavior:
 1. Loader makes multiple passes attempting to load enabled plugins.
 2. A plugin is only instantiated once all entries in `requires` are loaded.
 3. If after passes some dependencies remain unmet, the plugin is skipped and a log line is printed.

Best Practices:
    - Keep dependency list short and focused.
    - Emit events from dependency plugins instead of exposing internal attributes.
    - Use `get_plugin_instance(name)` only if you need direct API access.

---

## 🧷 Plugin Menu Actions

Plugins can inject custom actions into their own submenu without modifying core code.

### API
Implement `provide_menu_items(self) -> list` in your plugin class.

Return a list whose entries are any of:
1. `MenuItem` instances (preferred)
2. Tuples `(label, callable)`
3. Tuples `(label, callable, icon)` where `icon` is a Font Awesome glyph string
4. Tuples `(label, callable, icon, description)` adding a short help text

If at least one valid item is returned a separator `─ Actions ─` is inserted before them.

Called every time the Plugins menu is rebuilt, so keep it fast and side‑effect free.

### Example
```python
from plugins.base import Plugin

class NetToolsPlugin(Plugin):
    name = "net_tools"

    def provide_menu_items(self):
        return [
            ("Run Quick Scan", lambda: self.ctx['exec_payload']('auto_nmap_scan.py'), '\\uf002', "Shortcut to payload"),
            ("Show Status", self._show_status, '\\uf05a'),
            # Or explicit MenuItem if you need advanced args
            # MenuItem("Custom Action", lambda: ... , icon='\\uf0ad', description="Does something")
        ]

    def _show_status(self):
        sb = self.ctx.get('status_bar') if self.ctx else None
        if sb:
            sb.set_temp_status("NetTools OK", ttl=2)
```

### Notes
* Icons use the same Font Awesome font already loaded (pass raw unicode string, eg: `"\uf05a"`).
* Invalid tuple shapes are ignored safely.
* When disabled, a plugin's custom actions are not shown.

---

## 💾 Persisting Configuration Changes

Plugins sometimes need to update their configuration (e.g. after an interactive
picker). You can modify the in-memory value with `set_config_value()` but to
save it permanently to `plugins_conf.json` use the helper:

```python
self.persist_option('icon_horizontal_pos', 42)
```

### API
```python
persist_option(key: str, value: Any, create_if_missing: bool = True) -> bool
```

Behavior:
- Tries to load + update the central `plugins_conf.json` using runtime helpers.
- Returns `True` on apparent success, `False` otherwise.
- Creates the plugin entry if missing and `create_if_missing=True`.

This is preferred over re‑implementing JSON writes inside each plugin.

### Example (excerpt from Ethernet plugin)
```python
new_val = numeric_picker(wctx, label="ETH X", min_value=0, max_value=120, initial_value=current_int, step=1)
self.set_config_value('icon_horizontal_pos', new_val)      # update in memory
self.persist_option('icon_horizontal_pos', new_val)         # persist to disk
```

If you need to update multiple keys atomically, consider reading the current
config via runtime helpers and writing back once. A future helper may provide
batch persistence if needed.

---

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

def provide_menu_items(self) -> list:
    """Return optional custom menu items for this plugin's submenu.

    Return [] (or omit) for no extra actions. Accepts MenuItem objects or
    tuples (label, callable[, icon[, description]]). Called whenever plugin
    menus are rebuilt. Keep it lightweight (no blocking work)."""
    return []
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
- `widget_context` - The active `WidgetContext` (pass to pickers/dialogs)

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