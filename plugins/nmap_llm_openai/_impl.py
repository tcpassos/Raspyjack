from __future__ import annotations
import time
from typing import Any, Dict

from plugins.base import Plugin

class NmapLLMOpenAIPlugin(Plugin):
    name = "Nmap LLM OpenAI Plugin"
    priority = 100

    # Internal state variables
    def __init__(self):
        self.ctx: Dict[str, Any] | None = None

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
            # Verifica se pip está instalado
            try:
                import pip # type: ignore
            except ImportError:
                try:
                    subprocess.check_call(["apt", "install", "python3-pip", "-y"])
                except Exception:
                    pass
            # Tenta instalar openai
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
        from ui.widgets import explorer, dialog_info, display_scrollable_info
        import os
        scan_file = explorer(wctx, os.path.join(os.getcwd(), 'loot', 'Nmap'), extensions='.txt')
        if not scan_file:
            return
        with open(scan_file, 'r', encoding='utf-8') as f:
            scan_text = f.read()
        nmap_command = f"Manual file: {os.path.basename(scan_file)}"
        ai_result = self.openai_helper.analyze_nmap_scan(scan_text, nmap_command)
        out_name = os.path.splitext(os.path.basename(scan_file))[0] + '_ai.txt'
        out_path = os.path.join(os.getcwd(), 'loot', 'Nmap', out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(ai_result)
        dialog_info(wctx, f"AI analysis saved as:\n{out_name}", wait=True, center=True)
        display_scrollable_info(wctx, lines=ai_result.splitlines(), title="AI Analysis")

    def provide_menu_items(self):
        items = []
        if self.features_enabled:
            items.append(("Analyze Nmap Scan File", self._menu_analyze_scan_file, '\uf0eb', "Select a Nmap scan file and analyze with AI"))
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
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                scan_text = f.read()
        except Exception as e:
            dialog_info(wctx, f"Error reading scan file: {e}", wait=True, center=True)
            return
        nmap_command = ' '.join(args) if args else label
        ai_result = self.openai_helper.analyze_nmap_scan(scan_text, nmap_command)
        out_name = os.path.splitext(os.path.basename(result_path))[0] + '_ai.txt'
        out_path = os.path.join(os.path.dirname(result_path), out_name)
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(ai_result)
        except Exception as e:
            dialog_info(wctx, f"Error saving AI analysis: {e}", wait=True, center=True)
            return
        if yn_dialog(wctx, question="Open AI analysis?", yes_text="Yes", no_text="No", second_line=out_name):
            scrollable_text(wctx, out_path, title="AI Analysis")

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
            "- Manual and automatic Nmap scan analysis",
            "- AI result saved in loot/Nmap",
            "- PROMPT_OPENAI CLI tool",
            "- Configurable model and language",
            "",
            "Author: tcpassos"
        ]
        return '\n'.join(lines)
# Expose plugin instance for auto-discovery
plugin = NmapLLMOpenAIPlugin()
