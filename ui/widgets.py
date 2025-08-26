#!/usr/bin/env python3
"""
UI Widget System for Raspyjack
------------------------------------------
This module provides reusable UI components that can be used across different
programs. All widgets are designed to be independent and require minimal dependencies.
"""

import time
import textwrap
from typing import List, Any, Dict
import os
try:
    from ui.framebuffer import fb
except Exception:
    fb = None
from gpio_config import gpio_config


class WidgetContext:
    """Context object that holds all the dependencies needed by widgets."""
    
    def __init__(self, draw, lcd, image, color_scheme, get_button_func, 
                 fonts: Dict[str, Any], default_settings=None, status_bar=None, plugin_manager=None):
        self.draw = draw
        self.lcd = lcd  
        self.image = image
        self.color = color_scheme
        self.get_button = get_button_func
        self.fonts = fonts
        self.default = default_settings or self._create_default_settings()
        self.status_bar = status_bar
        self.plugin_manager = plugin_manager
        self.fb = fb
    
    def _create_default_settings(self):
        """Create default settings if none provided."""
        class DefaultSettings:
            start_text = [12, 22]
            text_gap = 14
        return DefaultSettings()


class BaseWidget:
    """Base class for all widgets."""
    
    def __init__(self, context: WidgetContext):
        self.ctx = context

    def persist_base_frame(self):
        """Persist the current context image as the new base frame.

        Widgets mutate the shared image buffer; for the background render loop
        to keep showing the latest widget content (and properly layer plugin
        overlays), the frame must be stored as persistent. Using a dedicated
        helper clarifies intent and centralizes the commit semantics.
        """
        if getattr(self.ctx, 'fb', None):
            try:
                working, _ = self.ctx.fb.begin(clone=False)
                self.ctx.fb.commit(working, persist=True)
            except Exception:
                try:
                    # Fallback: leave image as-is; background loop will still try to flush
                    pass
                except Exception:
                    pass
    
    def update_display(self):
        """Persist current widget frame; background loop handles actual LCD flush.

        This avoids tearing caused by concurrent direct LCD writes.
        """
        # Status bar over widget base
        if getattr(self.ctx, 'status_bar', None):
            try:
                font = self.ctx.fonts.get('default')
                self.ctx.status_bar.render(self.ctx.draw, font)
            except Exception:
                pass
        # Persist base frame so background loop retains updated widget content
        self.persist_base_frame()
        # Do not composite plugin overlay or flush here; central render loop will do it

    def blit_full(self, source_img, with_status: bool = False):
        """Copy a prepared Image onto the widget's backing image & persist.

        Args:
            source_img: PIL Image sized to LCD dimensions.
            with_status: If True, re-render status bar after blit.
        """
        try:
            # Paste onto context base image
            self.ctx.image.paste(source_img)
            if with_status and getattr(self.ctx, 'status_bar', None):
                try:
                    font = self.ctx.fonts.get('default')
                    self.ctx.status_bar.render(self.ctx.draw, font)
                except Exception:
                    pass
            self.persist_base_frame()
        except Exception:
            # As last resort push directly
            try:
                self.ctx.lcd.LCD_ShowImage(source_img, 0, 0)
            except Exception:
                pass


class ValuePickerWidget(BaseWidget):
    """Base class for widgets that need value picking controls (up/down arrows)."""
    
    def _draw_up_down(self, value, offset=0, up=False, down=False, render_color=None):
        """Helper method to draw up/down controls. Shared by all value picker widgets."""
        if render_color is None:
            render_color = self.ctx.color.text
            
        # Draw up triangle
        self.ctx.draw.polygon([(offset, 53), (10 + offset, 35), (20+offset, 53)],
            outline=self.ctx.color.gamepad, 
            fill=(self.ctx.color.background, self.ctx.color.gamepad_fill)[up])
        
        # Draw down triangle  
        self.ctx.draw.polygon([(10+offset, 93), (20+offset, 75), (offset, 75)],
            outline=self.ctx.color.gamepad, 
            fill=(self.ctx.color.background, self.ctx.color.gamepad_fill)[down])

        # Draw value display
        self.ctx.draw.rectangle([(offset + 2, 60), (offset+30, 70)], 
                               fill=self.ctx.color.background)
        self.ctx.draw.text((offset + 2, 60), str(value), fill=render_color,
                          font=self.ctx.fonts.get('default'))
    
    def _check_gpio_exit_condition(self) -> bool:
        """Check GPIO exit condition. Shared by widgets that use direct GPIO access."""
        try:
            import RPi.GPIO as GPIO
            return GPIO.input(gpio_config.key_press_pin) == 0
        except:
            # Fallback - always return False so widget continues
            return False


class Dialog(BaseWidget):
    """Simple message dialog widget."""
    
    def show(self, text: str, wait: bool = True, ok_text: str = "OK"):
        """Show a simple dialog with message and OK button."""
        # Draw dialog background
        self.ctx.draw.rectangle([7, 35, 120, 95], fill="#ADADAD")
        
        # Calculate text position (center horizontally)
        try:
            text_width = self.ctx.fonts['default'].getbbox(text)[2]
        except (AttributeError, KeyError):
            text_width = len(text) * 6  # Fallback calculation
        
        text_x = max(10, (128 - text_width) // 2)
        self.ctx.draw.text((text_x, 45), text, fill="#000000", font=self.ctx.fonts.get('default'))
        
        # Draw OK button
        self.ctx.draw.rectangle([45, 65, 70, 80], fill="#FF0000")
        self.ctx.draw.text((50, 68), ok_text, fill=self.ctx.color.selected_text, 
                          font=self.ctx.fonts.get('default'))
        
        self.update_display()
        
        if wait:
            time.sleep(0.25)
            self.ctx.get_button()


class InfoDialog(BaseWidget):
    """Information dialog widget with green background."""
    
    def show(self, text: str, wait: bool = True, timeout: float = 2.0, center: bool = True):
        """Show an information dialog.

        Args:
            text: Multi-line string (\n separated).
            wait: If True, block for 'timeout' seconds after rendering.
            timeout: Duration to display when wait=True.
            center: If True, horizontally center each line; else left-align.
        """
        self.ctx.draw.rectangle([3, 14, 124, 124], fill="#00A321")
        
        lines = text.split('\n')
        y_offset = 45 - (len(lines) - 1) * 6  # Approx vertical centering
        for i, raw_line in enumerate(lines):
            line = raw_line.rstrip() if center else raw_line.lstrip()  # trim opposite side to avoid manual spacing artifacts
            try:
                text_width = self.ctx.fonts['default'].getbbox(line)[2]
            except (AttributeError, KeyError):
                text_width = len(line) * 6
            if center:
                text_x = max(5, (128 - text_width) // 2)
            else:
                text_x = 5
            self.ctx.draw.text((text_x, y_offset + i * 12), line, fill="#000000", font=self.ctx.fonts.get('default'))
        self.update_display()
        if wait:
            time.sleep(timeout)


class YesNoDialog(BaseWidget):
    """Yes/No confirmation dialog widget."""
    
    def show(self, question: str = "Are you sure?", yes_text: str = "Yes", 
             no_text: str = "No", second_line: str = "") -> bool:
        """Show yes/no dialog and return True for Yes, False for No."""
        
        # Draw dialog background
        self.ctx.draw.rectangle([7, 35, 120, 95], fill="#ADADAD")
        
        # Draw question text
        try:
            text_width = self.ctx.fonts['default'].getbbox(question)[2]
        except (AttributeError, KeyError):
            text_width = len(question) * 6
        
        text_x = max(10, (128 - text_width) // 2)
        self.ctx.draw.text((text_x, 40), question, fill="#000000", 
                          font=self.ctx.fonts.get('default'))
        
        # Draw second line if provided
        if second_line:
            self.ctx.draw.text((12, 52), second_line, fill="#000000", 
                              font=self.ctx.fonts.get('default'))
        
        self.update_display()
        time.sleep(0.25)
        
        answer_yes = False
        
        while True:
            # Draw Yes button
            yes_bg = self.ctx.color.select if answer_yes else "#ADADAD"
            yes_fg = self.ctx.color.selected_text if answer_yes else "#000000"
            self.ctx.draw.rectangle([15, 65, 45, 80], fill=yes_bg)
            self.ctx.draw.text((20, 68), yes_text, fill=yes_fg, 
                              font=self.ctx.fonts.get('default'))

            # Draw No button  
            no_bg = self.ctx.color.select if not answer_yes else "#ADADAD"
            no_fg = self.ctx.color.selected_text if not answer_yes else "#000000"
            self.ctx.draw.rectangle([76, 65, 106, 80], fill=no_bg)
            self.ctx.draw.text((86, 68), no_text, fill=no_fg, 
                              font=self.ctx.fonts.get('default'))
            
            self.update_display()

            button = self.ctx.get_button()
            
            # Handle button input - use pin names from gpio_config
            if button in ["KEY_LEFT_PIN", "KEY1_PIN"]:
                answer_yes = True
            elif button in ["KEY_RIGHT_PIN", "KEY3_PIN"]:
                answer_yes = False
            elif button in ["KEY2_PIN", "KEY_PRESS_PIN"]:
                return answer_yes
            
            time.sleep(0.1)


class ScrollableText(BaseWidget):
    """Scrollable text display widget."""
    
    def show(self, lines: List[str], title: str = "", wrap_width: int = 22):
        """Display scrollable text with automatic line wrapping."""
        
        # Wrap long lines
        wrapped_lines = []
        for line in lines:
            if not line.strip():
                wrapped_lines.append('')
            else:
                wrapped = textwrap.wrap(line, width=wrap_width, 
                                      replace_whitespace=False, drop_whitespace=False)
                wrapped_lines.extend(wrapped if wrapped else [''])
        
        if not wrapped_lines:
            wrapped_lines = ["No content to display"]
        
        WINDOW = 7  # lines visible simultaneously
        total = len(wrapped_lines)
        index = 0   # current position
        offset = 0  # window offset

        while True:
            # Calculate window for scrolling
            if index < offset:
                offset = index
            elif index >= offset + WINDOW:
                offset = index - WINDOW + 1

            # Get visible window
            window = wrapped_lines[offset:offset + WINDOW]

            # Draw display
            self.ctx.color.draw_menu_background()
            
            # Draw title if provided
            if title:
                self.ctx.draw.text((5, 15), title, fill=self.ctx.color.selected_text, 
                                  font=self.ctx.fonts.get('default'))
                start_y = 30
            else:
                start_y = self.ctx.default.start_text[1]
            
            for i, line in enumerate(window):
                fill = self.ctx.color.selected_text if i == (index - offset) else self.ctx.color.text
                
                # Highlight current line
                if i == (index - offset):
                    self.ctx.draw.rectangle(
                        (self.ctx.default.start_text[0] - 5,
                         start_y + self.ctx.default.text_gap * i,
                         120,
                         start_y + self.ctx.default.text_gap * i + 10),
                        fill=self.ctx.color.select
                    )
                
                # Draw the text
                self.ctx.draw.text(
                    (self.ctx.default.start_text[0],
                     start_y + self.ctx.default.text_gap * i),
                    line,
                    font=self.ctx.fonts.get('default'),
                    fill=fill
                )

            self.update_display()
            time.sleep(0.12)

            # Handle button input
            btn = self.ctx.get_button()
            if btn == "KEY_DOWN_PIN":
                index = (index + 1) % total  # wrap to beginning
            elif btn == "KEY_UP_PIN":
                index = (index - 1) % total  # wrap to end
            elif btn in ("KEY_LEFT_PIN", "KEY3_PIN", "KEY_PRESS_PIN"):
                return  # Exit


class IpValuePicker(ValuePickerWidget):
    """IP value picker widget for selecting a single IP octet (0-255)."""
    
    def show(self, prefix: str = "", initial_value: int = 1) -> int:
        """Show IP value picker and return selected value."""
        value = initial_value
        up_down_offset = 75
        self.ctx.color.draw_menu_background()
        time.sleep(0.25)

        while True:
            render_up = False
            render_down = False

            # Clear area for text
            self.ctx.draw.rectangle([
                (self.ctx.default.start_text[0]-5, 1 + self.ctx.default.start_text[1]),
                (120, self.ctx.default.start_text[1] + self.ctx.default.text_gap * 6)
            ], fill=self.ctx.color.background)

            # Draw arrows and current value
            self._draw_up_down(value, up_down_offset, render_up, render_down, self.ctx.color.selected_text)
            self.ctx.draw.text((5, 60), f"IP:{prefix}.", fill=self.ctx.color.selected_text,
                               font=self.ctx.fonts.get('default'))

            self.update_display()

            button = self.ctx.get_button()
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
                return value

            # Redraw with movement highlight
            self._draw_up_down(value=value, offset=up_down_offset, up=render_up, down=render_down,
                               render_color=self.ctx.color.selected_text)
            self.update_display()
            time.sleep(0.08)


class ColorPicker(ValuePickerWidget):
    """RGB color picker widget."""
    
    def show(self, initial_color: str = "#000000") -> str:
        """Show color picker and return selected color as hex string."""
        self.ctx.color.draw_menu_background()
        self.ctx.color.draw_border()
        time.sleep(0.4)
        i_rgb = 0
        render_offset = self.ctx.default.updown_pos
        final_color = initial_color
        desired_color = list(int(final_color[i:i+2], 16) for i in (1, 3, 5))

        while True:
            # Clear full background each frame to avoid residual menu content
            self.ctx.color.draw_menu_background()
            self.ctx.color.draw_border()
            render_up = False
            render_down = False
            final_color='#%02x%02x%02x' % (desired_color[0],desired_color[1],desired_color[2])

            self.ctx.draw.rectangle([(self.ctx.default.start_text[0]-5, 1+ self.ctx.default.start_text[1] + self.ctx.default.text_gap * 0),(120, self.ctx.default.start_text[1] + self.ctx.default.text_gap * 0 + 10)], fill=final_color)
            self.ctx.draw.rectangle([(self.ctx.default.start_text[0]-5, 3+ self.ctx.default.start_text[1] + self.ctx.default.text_gap * 6),(120, self.ctx.default.start_text[1] + self.ctx.default.text_gap * 6 + 12)], fill=final_color)

            self._draw_up_down(desired_color[0],render_offset[0],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 0])
            self._draw_up_down(desired_color[1],render_offset[1],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 1])
            self._draw_up_down(desired_color[2],render_offset[2],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 2])
            
            self.update_display()

            button = self.ctx.get_button()
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

            self._draw_up_down(desired_color[i_rgb],render_offset[i_rgb],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 0])
            self.update_display() # Update display after processing button
            time.sleep(0.1)
        return final_color


class FileExplorer(BaseWidget):
    """Simple scrollable file/directory explorer widget."""

    def show(self, start_path: str = "/", extensions: str = "", confirm_open: bool = True) -> str:
        """Run the explorer interaction.

        Args:
            start_path: Initial directory path.
            extensions: Pipe-separated filter (e.g. ".txt|.log"). If empty, no filtering.
            confirm_open: If True, ask user to confirm opening a file. If False, return immediately.
        Returns:
            Selected file path or empty string if user exits/cancels.
        """
        current_path = os.path.abspath(start_path or "/")
        filter_exts = [e for e in extensions.split('|') if e] if extensions else []

        while True:
            try:
                dirs = []
                files = []
                try:
                    for entry in os.listdir(current_path):
                        full = os.path.join(current_path, entry)
                        if os.path.isdir(full):
                            dirs.append(entry)
                        elif os.path.isfile(full):
                            if not filter_exts or any(entry.endswith(ext) for ext in filter_exts):
                                files.append(entry)
                except Exception:
                    return ""
                dirs.sort(); files.sort()
                items = ["../"] + [d + "/" for d in dirs] + files

                # Reuse menu-based selector so navigation behavior is consistent
                from ui.menu import Menu, MenuItem, ListRenderer
                menu_items = [MenuItem(str(i), str(i)) for i in items]
                renderer = ListRenderer(self.ctx)
                menu = Menu(self.ctx, renderer)
                menu.set_items(menu_items)
                menu.set_title(current_path)
                sel = menu.run_interactive(exit_keys=["KEY_LEFT_PIN", "KEY3_PIN"])
                if sel is None:
                    return ""
                if sel == "../":
                    parent = os.path.dirname(current_path.rstrip('/')) or "/"
                    current_path = parent
                    continue
                full_sel = os.path.join(current_path, sel)
                if sel.endswith('/') and os.path.isdir(full_sel):
                    current_path = full_sel
                    continue
                # It's a file candidate
                if not confirm_open:
                    return full_sel
                if yn_dialog(self.ctx, question="Open this file?", yes_text="Yes", no_text="No", second_line=sel[:20]):
                    return full_sel
            except Exception:
                return ""

class ImageBrowser(BaseWidget):
    """Interactive image browser widget using explorer for navigation."""

    def show(self, start_path: str = "/root/", extensions: str = ".gif|.png|.bmp|.jpg|.jpeg") -> None:
        from ui.framebuffer import fb
        from gpio_config import gpio_config as _gpio_cfg
        import time, os
        from PIL import Image
        EDGE_BUTTONS = globals().get('EDGE_BUTTONS', set())
        _button_prev = globals().get('_button_prev', {})
        LCD = self.ctx.lcd
        path = start_path
        while True:
            img_path = explorer(self.ctx, path, extensions=extensions)
            if not img_path:
                break
            try:
                # Hide status bar only while rendering the image itself
                status_was_visible = False
                if getattr(self.ctx, 'status_bar', None) and not self.ctx.status_bar.is_hidden():
                    status_was_visible = True
                    self.ctx.status_bar.hide()
                with Image.open(img_path) as img:
                    canvas = Image.new("RGB", (LCD.width, LCD.height), "BLACK")
                    img.thumbnail((LCD.width, LCD.height))
                    px = (LCD.width - img.width) // 2
                    py = (LCD.height - img.height) // 2
                    canvas.paste(img, (px, py))
                    self.blit_full(canvas, with_status=False)
                self.ctx.get_button()
                if status_was_visible and getattr(self.ctx, 'status_bar', None):
                    self.ctx.status_bar.show()
            except Exception as e:
                dialog_info(self.ctx, f"Error opening image:\n{e}", wait=True)
            path = os.path.dirname(img_path)

# Convenience helper functions (direct instantiation)
def dialog(context: WidgetContext, text: str, wait: bool = True):
    """Show a simple dialog."""
    return Dialog(context).show(text, wait)

def dialog_info(context: WidgetContext, text: str, wait: bool = True, timeout: float = 2.0, center: bool = True):
    """Show an info dialog (optionally centered)."""
    return InfoDialog(context).show(text, wait=wait, timeout=timeout, center=center)

def yn_dialog(context: WidgetContext, question: str = "Are you sure?", 
              yes_text: str = "Yes", no_text: str = "No", second_line: str = "") -> bool:
    """Show a yes/no dialog."""
    return YesNoDialog(context).show(question, yes_text, no_text, second_line)

def ip_value_picker(context: WidgetContext, prefix: str = "", initial_value: int = 1) -> int:
    """Show an IP value picker and return selected value."""
    return IpValuePicker(context).show(prefix, initial_value)

def color_picker(context: WidgetContext, initial_color: str = "#000000") -> str:
    """Show a color picker and return the chosen color as a hex string."""
    return ColorPicker(context).show(initial_color)

def display_scrollable_info(context: WidgetContext, lines: List[str], title: str = "Info"):
    """Display scrollable information text."""
    ScrollableText(context).show(lines, title=title)

def explorer(context: WidgetContext, path: str = "/", extensions: str = "", confirm_open: bool = True) -> str:
    """Show a file explorer and return the selected file path or empty string.

    confirm_open controls whether a confirmation dialog is displayed before
    returning a selected file.
    """
    return FileExplorer(context).show(path, extensions, confirm_open=confirm_open)

def browse_images(context: WidgetContext, start_path: str = "/root/", extensions: str = ".gif|.png|.bmp|.jpg|.jpeg") -> None:
    """Convenience wrapper that creates an ImageBrowser and displays images."""
    ImageBrowser(context).show(start_path=start_path, extensions=extensions)

__all__ = [
    'WidgetContext', 'BaseWidget', 'ValuePickerWidget', 'Dialog', 'InfoDialog', 'YesNoDialog', 
    'ScrollableText', 'IpValuePicker', 'ColorPicker',
    'dialog', 'dialog_info', 'yn_dialog', 'ip_value_picker', 'color_picker',
    'display_scrollable_info', 'FileExplorer', 'explorer', 'ImageBrowser', 'browse_images'
]