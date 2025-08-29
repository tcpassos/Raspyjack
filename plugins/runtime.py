"""Runtime helper functions for RaspyJack plugin management.

This module centralizes all logic related to discovering plugins, loading
configuration, auto-populating defaults based on each plugin's config schema,
reloading plugins, and running the periodic plugin tick loop.

Having this logic here keeps `raspyjack.py` slimmer and focused on UI/core.
"""
from __future__ import annotations

import json
import os
import time
import importlib
from typing import Dict, Any, Optional

from .base import PluginManager, Plugin  # Re-use existing abstractions

# ----------------------------------------------------------------------------
# Configuration helpers
# ----------------------------------------------------------------------------

def _plugins_config_path(install_path: str) -> str:
    return os.path.join(install_path, 'plugins', 'plugins_conf.json')


def load_plugins_conf(install_path: str) -> Dict[str, Any]:
    """Load plugins configuration and auto-discover new plugins.

    Any new plugin package (directory with `__init__.py` under `plugins/`)
    not present in the config file will be imported so its schema can be
    read and a default entry created (disabled by default).
    """
    cfg_path = _plugins_config_path(install_path)
    try:
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    plugins_root = os.path.join(install_path, 'plugins')
    if not os.path.isdir(plugins_root):  # No plugins directory yet
        return cfg

    updated = False
    for name in os.listdir(plugins_root):
        plugin_path = os.path.join(plugins_root, name)
        if not os.path.isdir(plugin_path):
            continue
        if name.startswith('_'):
            continue  # Skip hidden/private
        if name == 'base':
            continue  # Skip core base module
        init_file = os.path.join(plugin_path, '__init__.py')
        if not os.path.isfile(init_file):
            continue  # Not a Python package
        if name in cfg:
            continue  # Already configured
        # Attempt import to read schema
        try:
            mod = importlib.import_module(f'plugins.{name}')
        except Exception as e:
            print(f"[PLUGIN] Auto-discovery import failed for '{name}': {e}")
            continue
        instance = getattr(mod, 'plugin', None)
        if instance is None:
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                    try:
                        instance = obj()
                    except Exception:
                        instance = None
                    break
        if instance is None:
            print(f"[PLUGIN] Auto-discovery could not locate plugin object in '{name}'")
            continue
        # Build default options from schema
        options = {}
        try:
            schema = instance.get_config_schema() if hasattr(instance, 'get_config_schema') else {}
            if isinstance(schema, dict):
                for key, meta in schema.items():
                    if isinstance(meta, dict):
                        options[key] = meta.get('default')
        except Exception as e:
            print(f"[PLUGIN] Failed reading schema for '{name}': {e}")
        entry = {
            "enabled": False,
            "priority": getattr(instance, 'priority', 100)
        }
        if options:
            entry['options'] = options
        cfg[name] = entry
        updated = True
        print(f"[PLUGIN] Added new plugin '{name}' to config with defaults (enabled = False)")
    if updated:
        save_plugins_conf(cfg, install_path)
    return cfg


def save_plugins_conf(cfg: Dict[str, Any], install_path: str) -> None:
    """Persist plugin configuration to disk."""
    try:
        path = _plugins_config_path(install_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[PLUGIN] Failed saving plugins_conf: {e}")

# ----------------------------------------------------------------------------
# Loading / reloading
# ----------------------------------------------------------------------------

def reload_plugins(current_manager: Optional[PluginManager], install_path: str, context: dict) -> PluginManager:
    """Reload all enabled plugins based on config.

    Returns a (possibly new) PluginManager instance with plugins loaded.
    """
    cfg = load_plugins_conf(install_path)
    manager = current_manager or PluginManager()
    try:
        if current_manager is not None:
            manager.unload_all()
    except Exception:
        pass
    if hasattr(manager, 'load_from_config'):
        manager.load_from_config(cfg, context)
    else:
        names = [k for k, v in cfg.items() if isinstance(v, dict) and v.get('enabled')]
        manager.load_all(names, context)
    return manager

# ----------------------------------------------------------------------------
# Tick loop
# ----------------------------------------------------------------------------

def plugin_tick_loop(manager_ref_provider, stop_event, interval: float = 0.5) -> None:
    """Continuously dispatch plugin ticks.

    manager_ref_provider can be either a PluginManager instance or a callable
    returning one (so we can see newly set globals). This keeps the loop alive
    even if the manager changes at runtime.
    """
    last_overlay = 0.0
    OVERLAY_REFRESH = 1.0  # seconds
    while not stop_event.is_set():
        try:
            manager = manager_ref_provider() if callable(manager_ref_provider) else manager_ref_provider
            if manager is not None:
                manager.dispatch_tick()
                now = time.time()
                if now - last_overlay >= OVERLAY_REFRESH:
                    last_overlay = now
                    try:
                        manager.rebuild_overlay()
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(interval)

__all__ = [
    'load_plugins_conf', 'save_plugins_conf', 'reload_plugins', 'plugin_tick_loop'
]
