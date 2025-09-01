from __future__ import annotations
from typing import Any, Dict

from plugins.base import Plugin

class OpenAIIntegrationPlugin(Plugin):
    name = "openai_integration_plugin"
    priority = 100

    # Internal state variables
    def __init__(self):
        self.ctx: Dict[str, Any] | None = None
        self.prompt_verbosity: str = 'normal'  # minimal|normal|full
        self._verbosity_item = None  # MenuItem instance for dynamic label

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def get_config_schema(self) -> dict:
        return {
            "api_key": {
                "type": "string",
                "label": "API Key",
                "description": "Your API key for accessing the service",
                "default": "",
            },
            "language": {
                "type": "string",
                "label": "Language",
                "description": "Preferred language for responses",
                "default": "en"
            },
            "model": {
                "type": "string",
                "label": "Model",
                "description": "Preferred language for responses",
                "default": "gpt-5-nano"
            },
            "auto_analyze_scans": {
                "type": "boolean",
                "label": "Auto Analyze Scans",
                "description": "Automatically analyze Nmap scans using LLM after completion",
                "default": False,
            },
            "prompt_verbosity": {
                "type": "string",
                "label": "Prompt Verbosity",
                "description": "Verbosity level for AI prompts (minimal|normal|full)",
                "default": "normal",
            }
        }

    def on_load(self, ctx: dict) -> None:
        self.ctx = ctx
        # Ensure openai dependency is installed
        try:
            import openai # type: ignore
            openai_installed = True
        except ImportError:
            import subprocess
            import sys
            # Check if pip is installed
            try:
                import pip # type: ignore
            except ImportError:
                try:
                    subprocess.check_call(["apt", "install", "python3-pip", "-y"])
                except Exception:
                    pass
            # Try installing openai
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "--break-system-packages"])
                import openai # type: ignore
                openai_installed = True
            except Exception:
                openai_installed = False
        try:
            from .helpers.openai_helper import OpenAIHelper
            self.has_openai = openai_installed
        except ImportError:
            self.has_openai = False
        self.api_key = self.get_config_value("api_key", "")
        self.language = self.get_config_value("language", "en")
        self.model = self.get_config_value("model", "gpt-5-nano")
        self.features_enabled = self.has_openai and bool(self.api_key)
        if self.features_enabled:
            self.openai_helper = OpenAIHelper(self.api_key, self.language, self.model)
        else:
            self.openai_helper = None
        # Load verbosity from persisted config if available
        try:
            self.prompt_verbosity = self.get_config_value('prompt_verbosity', 'normal') or 'normal'
            if self.prompt_verbosity not in ('minimal','normal','full'):
                self.prompt_verbosity = 'normal'
        except Exception:
            self.prompt_verbosity = 'normal'

    # ---------------- Verbosity handling -----------------
    def _cycle_verbosity(self):
        order = ['minimal','normal','full']
        try:
            idx = order.index(self.prompt_verbosity)
        except ValueError:
            idx = 1
        self.prompt_verbosity = order[(idx + 1) % len(order)]
        # Persist via base class helper
        try:
            self.persist_option('prompt_verbosity', self.prompt_verbosity)
        except Exception:
            pass
        # Update dynamic menu item label if present
        try:
            if self._verbosity_item is not None:
                self._verbosity_item.label = f"Verbosity: {self.prompt_verbosity}"
        except Exception:
            pass
        # Feedback on LCD
        wctx = self.ctx.get('widget_context') if self.ctx else None
        if wctx:
            try:
                from ui.widgets import dialog_info
                dialog_info(wctx, f"Verbosity -> {self.prompt_verbosity}", wait=True, center=True)
            except Exception:
                pass

    def _menu_analyze_scan_file(self):
        if not self.features_enabled:
            wctx = self.ctx.get('widget_context') if self.ctx else None
            if wctx:
                from ui.widgets import dialog_info
                dialog_info(wctx, "OpenAI features not enabled.\nCheck API key and dependency.", wait=True, center=True)
            return
        wctx = self.ctx.get('widget_context') if self.ctx else None
        if not wctx:
            return
        from ui.widgets import explorer, dialog_info, scrollable_text
        import os
        # Root path resolution centralized
        root_path = self._get_root_path()
        if not root_path:
            dialog_info(wctx, "Missing install_path in context", wait=True, center=True)
            return

        # Select scan file
        scan_file = explorer(wctx, os.path.join(root_path, 'loot'), extensions='.txt')
        if not scan_file:
            return

        # Select prompt file
        dialog_info(wctx, "Select prompt file\nfor analysis.", wait=True, center=True)
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        prompt_selected_path = explorer(wctx, prompts_dir, extensions='.txt')
        if not prompt_selected_path:
            # User cancelled prompt selection -> abort
            return
        prompt_base = os.path.splitext(os.path.basename(prompt_selected_path))[0]
        try:
            with open(prompt_selected_path, 'r', encoding='utf-8') as pf:
                prompt_content = pf.read()
        except Exception as e:
            dialog_info(wctx, f"Error reading prompt file: {e}", wait=True, center=True)
            return

        # Run analysis
        ai_result = self.openai_helper.analyze_file(scan_file, prompt_content, wctx=wctx)

        # Save output
        out_name = os.path.splitext(os.path.basename(scan_file))[0] + f'_{prompt_base}_ai.txt'
        ai_dir = self._get_ai_output_dir(root_path)
        os.makedirs(ai_dir, exist_ok=True)
        out_path = os.path.join(ai_dir, out_name)
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(ai_result)
        except Exception as e:
            dialog_info(wctx, f"Error saving analysis: {e}", wait=True, center=True)
            return

        # Feedback & display
        dialog_info(wctx, f"Prompt: {prompt_base}\nSaved: {out_name}", wait=True, center=True)
        scrollable_text(wctx, lines=ai_result.splitlines(), title="AI Analysis")

    def _menu_show_last_ai_report(self):
        """Open the most recently saved AI report (loot/AI/ai_*.txt)."""
        if not self.features_enabled:
            return
        wctx = self.ctx.get('widget_context') if self.ctx else None
        if not wctx:
            return
        from ui.widgets import dialog_info, scrollable_text
        import os, glob
        root_path = self._get_root_path()
        if not root_path:
            dialog_info(wctx, "Missing install_path in context", wait=True, center=True)
            return
        ai_dir = self._get_ai_output_dir(root_path)
        try:
            pattern = os.path.join(ai_dir, '*.txt')
            files = [f for f in glob.glob(pattern) if os.path.isfile(f)]
        except Exception:
            files = []
        if not files:
            dialog_info(wctx, "No AI report found", wait=True, center=True)
            return
        latest = max(files, key=lambda p: os.path.getmtime(p))
        print(f"[DEBUG] Latest AI report: {latest}")
        # Show using existing scrollable file viewer
        try:
            scrollable_text(wctx, latest, title="Last AI Report")
        except Exception:
            # Fallback: read manually
            try:
                with open(latest, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().splitlines()
                from ui.widgets import scrollable_text
                scrollable_text(wctx, content, title="Last AI Report")
            except Exception as e:
                dialog_info(wctx, f"Error opening report:\n{str(e)[:18]}", wait=True, center=True)

    def provide_menu_items(self):
        items = []
        if self.features_enabled:
            items.append(("Analyze file with AI", self._menu_analyze_scan_file, '\uf0eb', "Select file and analyze with AI"))
            from ui.menu import MenuItem  # lazy import to avoid cycle
            if self._verbosity_item is None:
                self._verbosity_item = MenuItem(f"Verbosity: {self.prompt_verbosity}", self._cycle_verbosity, '\uf031', "Cycle output verbosity")
            else:
                # Refresh label in case value changed externally
                self._verbosity_item.label = f"Verbosity: {self.prompt_verbosity}"
            items.append(self._verbosity_item)
            items.append(("Last AI Report", self._menu_show_last_ai_report, '\uf15c', "View most recent AI output"))
        return items

    def on_after_scan(self, label, args, result_path):
        if not self.features_enabled:
            return
        if not self.get_config_value("auto_analyze_scans", False):
            return
        wctx = self.ctx.get('widget_context') if self.ctx else None
        if not wctx:
            return
        from ui.widgets import dialog_info, yn_dialog, scrollable_text
        import os
        # Read scan file
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                # We pass the path to analyze_file so only need path here
                pass
        except Exception as e:
            dialog_info(wctx, f"Error reading scan file: {e}", wait=True, center=True)
            return
        # Infer prompt base & load content
        category = self._infer_prompt_category(label, args or [])
        prompt_base = f"{category}_{self.prompt_verbosity}"
        prompt_content = self._load_prompt_content(prompt_base)
        # Run analysis (file path provided, helper reads file content itself)
        ai_result = self.openai_helper.analyze_file(result_path, prompt_content, wctx=wctx)
        # Save with prompt base in name
        out_name = os.path.splitext(os.path.basename(result_path))[0] + f'_{prompt_base}_ai.txt'
        root_path = self._get_root_path()
        ai_dir = self._get_ai_output_dir(root_path) if root_path else os.path.dirname(result_path)
        try:
            os.makedirs(ai_dir, exist_ok=True)
        except Exception:
            pass
        out_path = os.path.join(ai_dir, out_name)
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(ai_result)
        except Exception as e:
            dialog_info(wctx, f"Error saving AI analysis: {e}", wait=True, center=True)
            return
        if yn_dialog(wctx, question="Open AI analysis?", yes_text="Yes", no_text="No", second_line=out_name):
            scrollable_text(wctx, out_path, title=f"AI Analysis ({prompt_base})")

    def get_info(self):
        lines = [
            f"Plugin: {self.name}",
            f"Enabled: {'Yes' if self.features_enabled else 'No'}",
            f"Model: {self.model}",
            f"Language: {self.language}",
            f"Auto Analyze: {'Yes' if self.get_config_value('auto_analyze_scans', False) else 'No'}",
            f"API Key: {'Set' if self.api_key else 'Not Set'}",
            f"OpenAI Dependency: {'OK' if self.has_openai else 'Missing'}",
            "",
            "Features:",
            "- Manual and automatic scan/file analysis (Nmap + extensible)",
            "- AI result saved in loot directories",
            "- PROMPT_OPENAI CLI tool",
            "- Configurable model and language",
            "",
            "Author: tcpassos"
        ]
        return '\n'.join(lines)
    
    # --- Internal helpers -------------------------------------------------
    def _infer_prompt_category(self, label: str, args: list[str]) -> str:
        """Infer prompt category ONLY (discovery|vectors|vulns) ignoring verbosity.

        Priority:
        1. Vulnerability related (scripts containing 'vuln'/'vulners') -> nmap_vulns
        2. Aggressive / OS / service enumeration (-A, -O, -sV) -> nmap_vectors
        3. UDP focused (-sU) -> nmap_discovery
        4. Full port surface (-p-) -> nmap_discovery
        5. Ping sweep (-sn) -> nmap_discovery
        Default: nmap_discovery
        """
        a = ' '.join(args).lower() if args else label.lower()
        if 'vuln' in a or 'vulners' in a:
            return 'nmap_vulns'
        if ' -a' in f' {a}' or ' -o' in f' {a}' or '-sv'.lower() in a:
            return 'nmap_vectors'
        if '-su' in a:
            return 'nmap_discovery'
        if '-p-' in a:
            return 'nmap_discovery'
        if ' -sn' in f' {a}' or 'ping sweep' in a:
            return 'nmap_discovery'
        return 'nmap_discovery'

    def _load_prompt_content(self, prompt_base: str) -> str:
        import os
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts', 'nmap')
        path = os.path.join(prompts_dir, f'{prompt_base}.txt')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            # Minimal fallback inline prompt
            return (
                'GOAL: Compact discovery summary.\n'
                'OUTPUT: IP | ports_count | key_service (one line each).\n'
                'FOCUS: live hosts with notable services.'
            )
    
    # --- Path helpers ----------------------------------------------------
    def _get_root_path(self) -> str | None:
        """Return install root path from context defaults or None."""
        try:
            if self.ctx and 'defaults' in self.ctx:
                defaults = self.ctx['defaults']
                val = getattr(defaults, 'install_path', None)
                if val is None and isinstance(defaults, dict):
                    val = defaults.get('install_path')
                return val
        except Exception:
            return None
        return None

    def _get_ai_output_dir(self, root_path: str) -> str:
        """Return path to AI output directory under given root."""
        import os
        return os.path.join(root_path, 'loot', 'AI')
# Expose plugin instance for auto-discovery
plugin = OpenAIIntegrationPlugin()
