# Example Plugin Template

Well‑documented reference implementation for creating new RaspyJack plugins.
Copy this directory (`example_plugin`) and rename it to start a new plugin.

## Directory Layout
```
example_plugin/
  __init__.py          # Exposes the plugin instance
  _impl.py             # Main implementation (hooks, config, logic)
  README.md            # This documentation
  bin/                 # Optional shell/python executables exposed to top-level bin/
    EXAMPLE_CMD        # Sample command (symlinked/copied to Raspyjack/bin)
  helpers/             # Optional support modules
    util_example.py    # Example helper function(s)
```

## Quick Start
1. Duplicate this folder and rename it, e.g. `my_new_plugin`.
2. Edit `_impl.py`: rename `ExamplePlugin` and adjust `name` + `priority`.
3. Adjust `get_config_schema()` to declare your configuration options.
4. Implement any lifecycle hooks you need.
5. Start RaspyJack; the new plugin will be auto‑detected and added to `plugins_conf.json` (disabled by default).
6. Enable it via: Menu > Plugins > your_plugin > Enable Plugin, then Save & Restart.

## Configuration Schema
Return a dictionary describing each option:
```python
def get_config_schema(self) -> dict:
    return {
        "show_counter": {
            "type": "boolean",
            "label": "Show Counter HUD",
            "description": "Display a simple incrementing counter on screen",
            "default": True,
        }
    }
```
The auto‑discovery process writes schema defaults into `plugins_conf.json` like:
```json
"my_new_plugin": {
  "enabled": false,
  "priority": 150,
  "options": { "show_counter": true }
}
```
You can safely hand‑edit `priority` and `enabled`. Options should usually be toggled via the UI so the plugin receives `on_config_changed()` callbacks.

## Hook Reference
| Hook | Purpose |
|------|---------|
| `on_load(ctx)` | Initialize resources. `ctx` provides helpers (payload execution, status bar, drawing access, etc.). |
| `on_unload()` | Clean up resources, close files, stop threads. |
| `on_tick(dt)` | Periodic lightweight updates. Avoid blocking. |
| `on_button(name)` | React to hardware button presses. |
| `on_render_overlay(image, draw)` | Draw small overlay elements (text/icon). Do not clear whole screen. |
| `on_before_exec_payload(name)` | Called before a payload is executed. |
| `on_after_exec_payload(name, success)` | After payload completion. |
| `on_before_scan(label, args)` | Before an Nmap scan starts. |
| `on_after_scan(label, args, result_path)` | After scan finishes; can parse or notify. |
| `on_config_changed(key, old, new)` | Respond to UI configuration toggles. |
| `get_info()` | Return multi‑line status string for the info viewer. |

## Adding Executables (bin/)
Any executable file placed under your plugin's `bin/` directory will be:
1. Symlinked into the top-level `bin/` directory if possible
2. Otherwise copied (with execute bit set)

This lets payloads call them uniformly, e.g. `./bin/EXAMPLE_CMD`.

## Best Practices
- Keep overlay rendering minimal (avoid flicker, cooperate with other plugins)
- Guard hardware access with try/except
- Avoid global imports for heavy libs inside hooks; import lazily
- Use `on_config_changed` to recompute derived state
- Consider adding a `get_info()` for user diagnostics

## Troubleshooting
- Plugin not showing? Ensure folder has `__init__.py` and a `plugin` instance
- Config not updating? Verify UI Save & Restart step if enabling/disabling
- Hooks not firing? Check console for `[PLUGIN]` error messages

## License
Use a license compatible with the main project or inherit the existing license terms.
