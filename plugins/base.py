"""Core plugin abstractions for RaspyJack.

Life‑cycle / callback methods (all optional):

    on_load(context: dict) -> None
        Called once right after the plugin is instantiated and registered.
        `context` contains helper callables and shared state references.

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
- Simple, single file plugin possible.
- Safe: all callbacks are wrapped in try/except so one misbehaving plugin
  does not break the main UI.
- Order: plugins have a `priority` (lower runs first for each dispatch).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import time
import traceback
from types import ModuleType
from typing import Callable, List, Optional, Sequence


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

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_all(self, module_names: Sequence[str], context: dict) -> None:
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

            # Strategy 1: explicit `plugin` variable
            instance = getattr(mod, "plugin", None)

            # Strategy 2: first subclass of Plugin
            if instance is None:
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                        try:
                            instance = obj()
                        except Exception as e:  # instantiation failure
                            self._log(f"[PLUGIN] Could not instantiate {obj}: {e}")
                        break

            if instance is None:
                self._log(f"[PLUGIN] No plugin object found in {mod_qual}")
                continue

            # Call on_load
            try:
                instance.on_load(context)
            except Exception as e:
                self._log(f"[PLUGIN] on_load error in {instance.name}: {e}")
                self._log(traceback.format_exc())
                continue  # skip registering

            self._loaded.append(_LoadedPlugin(instance=instance, module=mod))

        # Order by priority
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

            # Apply per-plugin config (priority override + options storage)
            if isinstance(pconf, dict):
                if "priority" in pconf:
                    try:
                        instance.priority = int(pconf["priority"])
                    except Exception:
                        pass
                # Store whole config (including options) for plugin access
                instance.config = pconf
                # Convenience: direct .options attribute if present
                if "options" in pconf and isinstance(pconf["options"], dict):
                    instance.options = pconf["options"]

            try:
                instance.on_load(context)
            except Exception as e:
                self._log(f"[PLUGIN] on_load error in {instance.name}: {e}")
                continue

            self._loaded.append(_LoadedPlugin(instance=instance, module=mod))

        self._loaded.sort(key=lambda lp: getattr(lp.instance, "priority", 100))
        if self.verbose:
            self._log("[PLUGIN] Loaded (config): " + ", ".join(p.instance.name for p in self._loaded) or "(none)")

    def unload_all(self) -> None:
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
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        for lp in self._loaded:
            try:
                lp.instance.on_tick(dt)
            except Exception:
                self._log(f"[PLUGIN] tick error in {lp.instance.name}")

    def dispatch_button(self, name: str) -> None:
        for lp in self._loaded:
            try:
                lp.instance.on_button(name)
            except Exception:
                self._log(f"[PLUGIN] button error in {lp.instance.name}")

    def dispatch_render_overlay(self, image, draw) -> None:
        for lp in self._loaded:
            try:
                lp.instance.on_render_overlay(image, draw)
            except Exception:
                self._log(f"[PLUGIN] render_overlay error in {lp.instance.name}")

    def before_exec_payload(self, payload_name: str) -> None:
        for lp in self._loaded:
            try:
                lp.instance.on_before_exec_payload(payload_name)
            except Exception:
                self._log(f"[PLUGIN] before_exec error in {lp.instance.name}")

    def after_exec_payload(self, payload_name: str, success: bool) -> None:
        for lp in self._loaded:
            try:
                lp.instance.on_after_exec_payload(payload_name, success)
            except Exception:
                self._log(f"[PLUGIN] after_exec error in {lp.instance.name}")

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    @property
    def plugins(self) -> List[Plugin]:
        return [lp.instance for lp in self._loaded]
