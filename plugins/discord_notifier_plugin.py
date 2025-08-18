"""
Plugin to send Nmap scan results to a Discord webhook.
"""
from __future__ import annotations
import os
import json
import requests
import threading
from datetime import datetime
from .base import Plugin

def get_discord_webhook_url():
    """
    Read Discord webhook URL from configuration file.
    Ignores lines with '#' and only considers lines starting with the webhook URL pattern.
    """
    webhook_file = "/root/Raspyjack/discord_webhook.txt"
    try:
        if os.path.exists(webhook_file):
            with open(webhook_file, 'r') as f:
                for line in f:
                    # Ignore comments
                    if '#' in line:
                        continue
                    
                    # Clean up the line
                    webhook_url = line.strip()
                    
                    # Check if it's a valid webhook URL
                    if webhook_url.startswith("https://discord.com/api/webhooks/"):
                        print(f"[DiscordNotifier] Found webhook URL.")
                        return webhook_url
    except Exception as e:
        print(f"[DiscordNotifier] Error reading Discord webhook: {e}")
    return None

def _send_notification(webhook_url: str, scan_label: str, file_path: str, target_network: str, interface: str):
    """The actual sending logic."""
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            print(f"[DiscordNotifier] Scan file is missing or empty: {file_path}")
            return

        embed = {
            "title": f"🔍 Nmap Scan Complete: {scan_label}",
            "description": f"**Target Network:** `{target_network}`\n**Interface:** `{interface}`\n**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "color": 0x00ff00,  # Green
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

        if response.status_code >= 200 and response.status_code < 300:
            print("[DiscordNotifier] Webhook with file sent successfully.")
        else:
            print(f"[DiscordNotifier] Webhook failed: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"[DiscordNotifier] Error sending webhook: {e}")


class DiscordNotifierPlugin(Plugin):
    name = "DiscordNotifier"
    priority = 200  # Run after most other things

    def on_after_scan(self, label: str, args: list[str], result_path: str) -> None:
        """Called after an Nmap scan is complete."""
        webhook_url = get_discord_webhook_url()
        if not webhook_url:
            return  # Not configured

        # We need the target network and interface, which are not in the callback args.
        # For now, we'll get them again. A future improvement could be to add them to the callback.
        try:
            from wifi.raspyjack_integration import get_best_interface, get_nmap_target_network
            interface = get_best_interface()
            target_network = get_nmap_target_network(interface)
        except Exception:
            interface = "eth0"
            target_network = "unknown"

        # Run in a separate thread to avoid blocking the UI
        thread = threading.Thread(
            target=_send_notification,
            args=(webhook_url, label, result_path, target_network, interface),
            daemon=True
        )
        thread.start()

    def get_info(self) -> str:
        """Check if the Discord webhook is configured."""
        if get_discord_webhook_url():
            return "Discord webhook is configured."
        else:
            return "Discord webhook is NOT configured. See discord_webhook.txt."

plugin = DiscordNotifierPlugin()
