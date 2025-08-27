from __future__ import annotations
import os
import json
import requests
import threading
from datetime import datetime
from plugins.base import Plugin
from .helpers.discord_utils import get_discord_webhook_url, send_message_to_discord, send_file_to_discord

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

    def on_after_scan(self, label: str, args: list[str], result_path: str) -> None:
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

    def get_info(self) -> str:
        if get_discord_webhook_url():
            return "Discord webhook is configured."
        else:
            return "Discord webhook is NOT configured. See discord_webhook.txt."

plugin = DiscordNotifierPlugin()
