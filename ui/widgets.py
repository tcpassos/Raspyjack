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
from gpio_config import gpio_config


class WidgetContext:
    """Context object that holds all the dependencies needed by widgets."""
    
    def __init__(self, draw, lcd, image, color_scheme, get_button_func, 
                 fonts: Dict[str, Any], default_settings=None):
        self.draw = draw
        self.lcd = lcd  
        self.image = image
        self.color = color_scheme
        self.get_button = get_button_func
        self.fonts = fonts
        self.default = default_settings or self._create_default_settings()
    
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
    
    def update_display(self):
        """Update the LCD display with current image."""
        self.ctx.lcd.LCD_ShowImage(self.ctx.image, 0, 0)


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
    
    def show(self, text: str, wait: bool = True):
        """Show an information dialog."""
        self.ctx.draw.rectangle([3, 14, 124, 124], fill="#00A321")
        
        # Handle multi-line text
        lines = text.split('\n')
        y_offset = 45 - (len(lines) - 1) * 6  # Center vertically
        
        for i, line in enumerate(lines):
            try:
                text_width = self.ctx.fonts['default'].getbbox(line)[2]
            except (AttributeError, KeyError):
                text_width = len(line) * 6
            
            text_x = max(5, (128 - text_width) // 2)
            self.ctx.draw.text((text_x, y_offset + i * 12), line, 
                              fill="#000000", font=self.ctx.fonts.get('default'))
        
        self.update_display()
        
        if wait:
            time.sleep(0.25)
            self.ctx.get_button()


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
    
    def show(self, lines: List[str], title: str = "", wrap_width: int = 24):
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
        render_offset = self.ctx.default.updown_pos
        self.ctx.color.draw_menu_background()
        time.sleep(0.4)

        import RPi.GPIO as GPIO
        while GPIO.input(gpio_config.key_press_pin):
            render_up = False
            render_down = False

            self.ctx.draw.rectangle(
                    [
                        (self.ctx.default.start_text[0]-5, 1+ self.ctx.default.start_text[1] + self.ctx.default.text_gap * 0),
                        (120, self.ctx.default.start_text[1] + self.ctx.default.text_gap * 5)
                    ],
                    fill=self.ctx.color.background
                )
            self._draw_up_down(value, render_offset[2], render_up, render_down, self.ctx.color.selected_text)
            self.ctx.draw.text(( 5,60), f"IP:{prefix}.", fill=self.ctx.color.selected_text)

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
                break

            self._draw_up_down(value=value, offset=render_offset[2], up=render_up, down=render_down, render_color=self.ctx.color.selected_text)
            time.sleep(0.1)
        return value


class ColorPicker(ValuePickerWidget):
    """RGB color picker widget."""
    
    def show(self, initial_color: str = "#000000") -> str:
        """Show color picker and return selected color as hex string."""
        self.ctx.color.draw_menu_background()
        time.sleep(0.4)
        i_rgb = 0
        render_offset = self.ctx.default.updown_pos
        final_color = initial_color
        desired_color = list(int(final_color[i:i+2], 16) for i in (1, 3, 5))

        import RPi.GPIO as GPIO
        while GPIO.input(gpio_config.key_press_pin):
            render_up = False
            render_down = False
            final_color='#%02x%02x%02x' % (desired_color[0],desired_color[1],desired_color[2])

            self.ctx.draw.rectangle([(self.ctx.default.start_text[0]-5, 1+ self.ctx.default.start_text[1] + self.ctx.default.text_gap * 0),(120, self.ctx.default.start_text[1] + self.ctx.default.text_gap * 0 + 10)], fill=final_color)
            self.ctx.draw.rectangle([(self.ctx.default.start_text[0]-5, 3+ self.ctx.default.start_text[1] + self.ctx.default.text_gap * 6),(120, self.ctx.default.start_text[1] + self.ctx.default.text_gap * 6 + 12)], fill=final_color)

            self._draw_up_down(desired_color[0],render_offset[0],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 0])
            self._draw_up_down(desired_color[1],render_offset[1],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 1])
            self._draw_up_down(desired_color[2],render_offset[2],render_up,render_down,(self.ctx.color.text, self.ctx.color.selected_text)[i_rgb == 2])

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
            time.sleep(0.1)
        return final_color


# Factory functions for easy widget creation
def create_dialog(context: WidgetContext) -> Dialog:
    """Create a dialog widget."""
    return Dialog(context)

def create_info_dialog(context: WidgetContext) -> InfoDialog:
    """Create an info dialog widget."""
    return InfoDialog(context)

def create_yes_no_dialog(context: WidgetContext) -> YesNoDialog:
    """Create a yes/no dialog widget."""
    return YesNoDialog(context)

def create_scrollable_text(context: WidgetContext) -> ScrollableText:
    """Create a scrollable text widget."""
    return ScrollableText(context)

def create_ip_value_picker(context: WidgetContext) -> IpValuePicker:
    """Create an IP value picker widget."""
    return IpValuePicker(context)

def create_color_picker(context: WidgetContext) -> ColorPicker:
    """Create an RGB color picker widget."""
    return ColorPicker(context)


# Convenience functions for backward compatibility
def dialog(context: WidgetContext, text: str, wait: bool = True):
    """Show a simple dialog."""
    return create_dialog(context).show(text, wait)

def dialog_info(context: WidgetContext, text: str, wait: bool = True):
    """Show an info dialog."""
    return create_info_dialog(context).show(text, wait)

def yn_dialog(context: WidgetContext, question: str = "Are you sure?", 
              yes_text: str = "Yes", no_text: str = "No", second_line: str = "") -> bool:
    """Show a yes/no dialog."""
    return create_yes_no_dialog(context).show(question, yes_text, no_text, second_line)

def ip_value_picker(context: WidgetContext, prefix: str = "", initial_value: int = 1) -> int:
    """Show an IP value picker and return selected value."""
    return create_ip_value_picker(context).show(prefix, initial_value)

def color_picker(context: WidgetContext, initial_color: str = "#000000") -> str:
    """Show a color picker and return the chosen color as a hex string."""
    return create_color_picker(context).show(initial_color)


__all__ = [
    'WidgetContext', 'BaseWidget', 'ValuePickerWidget', 'Dialog', 'InfoDialog', 'YesNoDialog', 
    'ScrollableText', 'IpValuePicker', 'ColorPicker',
    'create_dialog', 'create_info_dialog', 'create_yes_no_dialog', 
    'create_scrollable_text', 'create_ip_value_picker', 'create_color_picker',
    'dialog', 'dialog_info', 'yn_dialog', 'ip_value_picker', 'color_picker'
]