"""Core plugin abstractions for RaspyJack.

Life‑cycle / callback methods (all optional):

    on_load(context: dict) -> None
        Called once right after the plugin is instantiated and registered.
        `context` contains helper callables and shared state references.
        Currently provided keys (may expand):
            exec_payload(name)          -> run a payload script
            get_menu()                  -> current menu list
            is_responder_running()      -> bool
            is_mitm_running()           -> bool
            draw_image()                -> PIL base image (do not mutate globally)
            draw_obj()                  -> PIL ImageDraw for base image
            status_bar                  -> StatusBar instance (has set_temp_status, is_busy, etc.)

    on_unload() -> None
        Called during shutdown (Leave) so the plugin can release resources.

    on_tick(dt: float) -> None
        Called periodically from the stats loop (roughly every cycle). Use this
        for polling hardware or timers. Keep it short (non‑blocking!).

    on_button(name: str) -> None
        Invoked whenever a physical button is pressed. `name` is the key in
        PINS (e.g. "KEY_UP_PIN").

    on_render_overlay(image, draw) -> None
        Gives a chance to draw on the current PIL image right before it is
        pushed to the LCD. Do not clear the whole screen; draw only what you
        own (e.g., small HUD elements). You can call other helpers from
        context if needed.

    on_before_exec_payload(payload_name: str) -> None
        Fired just before a payload script is executed.

    on_after_exec_payload(payload_name: str, success: bool) -> None
        Fired after the payload returns (success indicates no exception in the
        wrapper, not inside the payload itself necessarily).

Design goals:
- Canonical package layout per plugin:

        plugins/
            my_plugin/
                __init__.py        # must expose `plugin` instance or Plugin subclass
                bin/                # optional: executable scripts to be exposed
                    MY_COMMAND      # becomes available under top-level bin/
                helpers/            # optional support modules imported by __init__
                ...

- Safe: all callbacks are wrapped in try/except so one misbehaving plugin
  does not break the main UI.
- Order: plugins have a `priority` (lower runs first for each dispatch).

Per-plugin bin exposure:
If a plugin package contains a `bin` directory, its executable files are
mirrored into the root `bin` directory (without overwriting existing files).
We attempt to create a small shim wrapper when running on non-Unix systems or
if symlinks are not permitted. This allows payloads to invoke plugin-provided
commands uniformly.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import time
import traceback
from types import ModuleType
from typing import List, Sequence
import os
import shutil


class Plugin:
    name: str = "BasePlugin"
    priority: int = 100  # lower = earlier
    # Will be filled with the plugin specific configuration block
    config: dict | None = None

    # --- Life‑cycle hooks -------------------------------------------------
    def on_load(self, ctx: dict) -> None: ...
    def on_unload(self) -> None: ...

    # --- Event hooks ------------------------------------------------------
    def on_tick(self, dt: float) -> None: ...
    def on_button(self, name: str) -> None: ...
    def on_render_overlay(self, image, draw) -> None: ...
    def on_before_exec_payload(self, payload_name: str) -> None: ...
    def on_after_exec_payload(self, payload_name: str, success: bool) -> None: ...
    def on_before_scan(self, label: str, args: list[str]) -> None: ...
    def on_after_scan(self, label: str, args: list[str], result_path: str) -> None: ...
    
    def get_info(self) -> str:
        return "No information available for this plugin."
    
    # --- Configuration system ---------------------------------------------
    def get_config_schema(self) -> dict:
        """Return configuration schema for this plugin.
        
        Returns a dictionary where keys are config names and values are config definitions.
        Currently only boolean configurations are supported.
        
        Example:
            {
                "auto_start": {
                    "type": "boolean",
                    "label": "Auto Start on Boot",
                    "description": "Automatically start this plugin when system boots",
                    "default": False
                },
                "debug_mode": {
                    "type": "boolean", 
                    "label": "Debug Mode",
                    "description": "Enable debug logging for this plugin",
                    "default": False
                }
            }
        """
        return {}
    
    def get_config_value(self, key: str, default=None):
        """Get current value of a configuration setting."""
        if not self.config:
            return default
        
        options = self.config.get('options', {})
        if key in options:
            return options[key]
        
        # Fallback to schema default if available
        schema = self.get_config_schema()
        if key in schema:
            return schema[key].get('default', default)
        
        return default
    
    def set_config_value(self, key: str, value) -> None:
        """Set a configuration value. Note: This only updates the in-memory config.
        Use PluginManager.save_plugin_config() to persist changes."""
        if not self.config:
            self.config = {}
        
        if 'options' not in self.config:
            self.config['options'] = {}
        
        self.config['options'][key] = value
    
    def on_config_changed(self, key: str, old_value, new_value) -> None:
        """Called when a configuration value changes. Override to react to config changes."""
        pass


@dataclass
class _LoadedPlugin:
    instance: Plugin
    module: ModuleType


class PluginManager:
    """Loads and dispatches events to registered plugins."""

    def __init__(self, verbose: bool = True):
        self._loaded: List[_LoadedPlugin] = []
        self._last_tick: float = time.time()
        self._ctx: dict = {}
        self.verbose = verbose
        # Internal synchronization
        import threading
        self._lock = threading.RLock()
        # Overlay snapshot (RGBA) updated after ticks
        from PIL import Image
        self._overlay_image = Image.new('RGBA', (128, 128), (0, 0, 0, 0))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_all(self, module_names: Sequence[str], context: dict) -> None:
        with self._lock:
            self._ctx = context
            for name in module_names:
                name = name.strip()
                if not name:
                    continue
                mod_qual = f"plugins.{name}"
                try:
                    mod = importlib.import_module(mod_qual)
                except Exception as e:
                    self._log(f"[PLUGIN] Failed to import '{mod_qual}': {e}")
                    self._log(traceback.format_exc())
                    continue

                instance = getattr(mod, "plugin", None)
                if instance is None:
                    for attr in dir(mod):
                        obj = getattr(mod, attr)
                        if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                            try:
                                instance = obj()
                            except Exception as e:
                                self._log(f"[PLUGIN] Could not instantiate {obj}: {e}")
                            break

                if instance is None:
                    self._log(f"[PLUGIN] No plugin object found in {mod_qual}")
                    continue

                try:
                    instance.on_load(context)
                except Exception as e:
                    self._log(f"[PLUGIN] on_load error in {instance.name}: {e}")
                    self._log(traceback.format_exc())
                    continue

                self._loaded.append(_LoadedPlugin(instance=instance, module=mod))

            self._loaded.sort(key=lambda lp: getattr(lp.instance, "priority", 100))
            if self.verbose:
                self._log("[PLUGIN] Loaded: " + ", ".join(p.instance.name for p in self._loaded) or "(none)")

    # ------------------------------------------------------------------
    # New configuration based loading
    # ------------------------------------------------------------------
    def load_from_config(self, config: dict, context: dict) -> None:
        """Load plugins from a config mapping.

        Expected structure (JSON example)::

            {
              "example_plugin": {
                "enabled": true,
                "priority": 50,
                "options": {"show_seconds": true}
              },
              "other_plugin": {
                "enabled": false
              }
            }

        Any plugin with enabled set to false (or missing) is skipped.
        """
        with self._lock:
            self._ctx = context
            for module_name, pconf in config.items():
                if not isinstance(pconf, dict):
                    continue
                if not pconf.get("enabled", False):
                    continue
                mod_qual = f"plugins.{module_name}"
                try:
                    mod = importlib.import_module(mod_qual)
                except Exception as e:
                    self._log(f"[PLUGIN] Failed to import '{mod_qual}': {e}")
                    continue

                instance = getattr(mod, "plugin", None)
                if instance is None:
                    for attr in dir(mod):
                        obj = getattr(mod, attr)
                        if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                            try:
                                instance = obj()
                            except Exception as e:
                                self._log(f"[PLUGIN] Could not instantiate {obj}: {e}")
                            break
                if instance is None:
                    self._log(f"[PLUGIN] No plugin object found in {mod_qual}")
                    continue

                if isinstance(pconf, dict):
                    if "priority" in pconf:
                        try:
                            instance.priority = int(pconf["priority"])
                        except Exception:
                            pass
                    instance.config = pconf
                    if "options" in pconf and isinstance(pconf["options"], dict):
                        instance.options = pconf["options"]

                try:
                    instance.on_load(context)
                except Exception as e:
                    self._log(f"[PLUGIN] on_load error in {instance.name}: {e}")
                    continue

                self._loaded.append(_LoadedPlugin(instance=instance, module=mod))
                # After successful load, expose bin tools if present
                try:
                    self._expose_plugin_bin(mod)
                except Exception as e:
                    self._log(f"[PLUGIN] bin expose error for {module_name}: {e}")

            self._loaded.sort(key=lambda lp: getattr(lp.instance, "priority", 100))
            if self.verbose:
                self._log("[PLUGIN] Loaded (config): " + ", ".join(p.instance.name for p in self._loaded) or "(none)")

    def unload_all(self) -> None:
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_unload()
                except Exception as e:
                    self._log(f"[PLUGIN] on_unload error in {lp.instance.name}: {e}")
            self._loaded.clear()

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------
    def dispatch_tick(self) -> None:
        with self._lock:
            now = time.time()
            dt = now - self._last_tick
            self._last_tick = now
            for lp in self._loaded:
                try:
                    lp.instance.on_tick(dt)
                except Exception:
                    self._log(f"[PLUGIN] tick error in {lp.instance.name}")

    def dispatch_button(self, name: str) -> None:
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_button(name)
                except Exception:
                    self._log(f"[PLUGIN] button error in {lp.instance.name}")

    def dispatch_render_overlay(self, image, draw) -> None:
        # This remains for legacy direct rendering paths; prefer overlay snapshot methods.
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_render_overlay(image, draw)
                except Exception:
                    self._log(f"[PLUGIN] render_overlay error in {lp.instance.name}")

    # --- Overlay snapshot pipeline ---------------------------------
    def rebuild_overlay(self, size: tuple[int, int] = (128, 128)) -> None:
        """Rebuild cached overlay by invoking plugins on a fresh RGBA layer."""
        from PIL import Image, ImageDraw
        tmp = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(tmp)
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_render_overlay(tmp, draw)
                except Exception:
                    self._log(f"[PLUGIN] rebuild_overlay error in {lp.instance.name}")
            self._overlay_image = tmp  # atomic swap

    def get_overlay(self):
        """Return last built overlay (do not mutate)."""
        return self._overlay_image

    def before_exec_payload(self, payload_name: str) -> None:
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_before_exec_payload(payload_name)
                except Exception:
                    self._log(f"[PLUGIN] before_exec error in {lp.instance.name}")

    def after_exec_payload(self, payload_name: str, success: bool) -> None:
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_after_exec_payload(payload_name, success)
                except Exception:
                    self._log(f"[PLUGIN] after_exec error in {lp.instance.name}")

    def before_scan(self, label: str, args: list[str]) -> None:
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_before_scan(label, args)
                except Exception:
                    self._log(f"[PLUGIN] before_scan error in {lp.instance.name}")

    def after_scan(self, label: str, args: list[str], result_path: str) -> None:
        with self._lock:
            for lp in self._loaded:
                try:
                    lp.instance.on_after_scan(label, args, result_path)
                except Exception:
                    self._log(f"[PLUGIN] after_scan error in {lp.instance.name}")

    def get_plugin_info(self, name: str) -> str:
        """Get info string from a specific plugin by name."""
        for lp in self._loaded:
            # Compare against the module name, not the class name
            module_short_name = lp.module.__name__.split('.')[-1]
            if module_short_name == name:
                try:
                    return lp.instance.get_info()
                except Exception as e:
                    self._log(f"[PLUGIN] get_info error in {lp.instance.name}: {e}")
                    return "Error getting info."
        return "Plugin not loaded."
    
    def get_plugin_config_schema(self, name: str) -> dict:
        """Get configuration schema for a specific plugin by name."""
        for lp in self._loaded:
            module_short_name = lp.module.__name__.split('.')[-1]
            if module_short_name == name:
                try:
                    return lp.instance.get_config_schema()
                except Exception as e:
                    self._log(f"[PLUGIN] get_config_schema error in {lp.instance.name}: {e}")
                    return {}
        return {}
    
    def get_plugin_config_value(self, plugin_name: str, config_key: str, default=None):
        """Get current configuration value for a plugin."""
        for lp in self._loaded:
            module_short_name = lp.module.__name__.split('.')[-1]
            if module_short_name == plugin_name:
                try:
                    return lp.instance.get_config_value(config_key, default)
                except Exception as e:
                    self._log(f"[PLUGIN] get_config_value error in {lp.instance.name}: {e}")
                    return default
        return default
    
    def set_plugin_config_value(self, plugin_name: str, config_key: str, value) -> bool:
        """Set configuration value for a plugin and notify of change."""
        for lp in self._loaded:
            module_short_name = lp.module.__name__.split('.')[-1]
            if module_short_name == plugin_name:
                try:
                    old_value = lp.instance.get_config_value(config_key)
                    lp.instance.set_config_value(config_key, value)
                    try:
                        lp.instance.on_config_changed(config_key, old_value, value)
                    except Exception as e:
                        self._log(f"[PLUGIN] on_config_changed error in {lp.instance.name}: {e}")
                    return True
                except Exception as e:
                    self._log(f"[PLUGIN] set_config_value error in {lp.instance.name}: {e}")
                    return False
        return False

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    # ------------------------------------------------------------------
    # Bin exposure helpers
    # ------------------------------------------------------------------
    def _expose_plugin_bin(self, module: ModuleType) -> None:
        """Expose executables from a plugin's bin/ directory into top-level bin/.
            - Detect plugin package path via module.__file__.
            - Look for sibling 'bin' directory.
            - For each entry (file) without extension (or any executable), create
            a symlink under project_root/bin if possible; otherwise create a
            small wrapper script that calls the source file with Python or shell.
            - Never overwrite existing targets; log and skip collisions.
        """
        mod_file = getattr(module, '__file__', None)
        if not mod_file:
            return
        plugin_dir = os.path.dirname(mod_file)
        bin_dir = os.path.join(plugin_dir, 'bin')
        if not os.path.isdir(bin_dir):
            return
        # project root assumed two levels up from plugins package file path
        # e.g., /path/Raspyjack/plugins/my_plugin/__init__.py
        project_root = plugin_dir
        while project_root and os.path.basename(project_root) != 'Raspyjack' and os.path.dirname(project_root) != project_root:
            project_root = os.path.dirname(project_root)
        top_bin = os.path.join(project_root, 'bin')
        if not os.path.isdir(top_bin):
            try:
                os.makedirs(top_bin, exist_ok=True)
            except Exception:
                return
        for name in os.listdir(bin_dir):
            src_path = os.path.join(bin_dir, name)
            if os.path.isdir(src_path):
                continue
            dest_path = os.path.join(top_bin, name)
            if os.path.exists(dest_path):
                # Do not overwrite existing global command
                continue
            
            # Ensure source file has execute permissions first
            try:
                os.chmod(src_path, 0o755)
            except Exception:
                pass
            
            try:
                # Try symlink first
                os.symlink(src_path, dest_path)
                self._log(f"[PLUGIN] Created symlink: bin/{name} -> {src_path}")
                # For symlinks, also ensure destination has correct permissions
                try:
                    os.chmod(dest_path, 0o755)
                except Exception:
                    pass
            except Exception:
                # Fallback: copy or create wrapper
                try:
                    shutil.copy2(src_path, dest_path)
                    self._log(f"[PLUGIN] Copied executable: bin/{name} from {src_path}")
                    # Ensure copied file has execute permissions
                    try:
                        os.chmod(dest_path, 0o755)
                    except Exception:
                        pass
                except Exception:
                    # Last resort: create python wrapper if src is .py
                    if src_path.endswith('.py'):
                        with open(dest_path, 'w', encoding='utf-8') as f:
                            f.write('#!/usr/bin/env python3\n')
                            f.write(f"import runpy, sys; sys.path.insert(0, '{plugin_dir}'); runpy.run_path('{src_path}', run_name='__main__')\n")
                        self._log(f"[PLUGIN] Created Python wrapper: bin/{name} for {src_path}")
                        try:
                            os.chmod(dest_path, 0o755)
                        except Exception:
                            pass

    @property
    def plugins(self) -> List[Plugin]:
        return [lp.instance for lp in self._loaded]
