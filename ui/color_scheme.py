"""Color scheme management for RaspyJack UI.

This module defines the `ColorScheme` class which encapsulates all theme
(colors) used by the application in a clean, Pythonic and self‑contained
implementation.

Index mapping:
    0 -> background
    1 -> border
    2 -> text
    3 -> selected_text
    4 -> select (selection background)
    5 -> gamepad (outline)
    6 -> gamepad_fill (pressed fill)

The drawing operations require a PIL.ImageDraw.Draw object. Instead of
storing a direct reference, the class accepts a `draw_ref` callable
returning the current draw object. This keeps the class decoupled from global
variables while preserving existing usage patterns (e.g. lambdas capturing the global `draw`).
"""
from __future__ import annotations
from typing import Callable, Dict

__all__ = ["ColorScheme"]


class ColorScheme:
    """Encapsulates theme colors and rendering helpers.

    Parameters
    ----------
    draw_ref : Callable[[], object] | None
        A callable returning the current PIL.ImageDraw.Draw instance. If
        None, drawing helper methods become no‑ops (useful for tests).
    """

    # Default colors (can be overridden after instantiation)
    border: str = "#0e0e6b"
    background: str = "#000000"
    text: str = "#9c9ccc"
    selected_text: str = "#EEEEEE"
    select: str = "#141494"
    gamepad: str = select  # outline color
    gamepad_fill: str = selected_text  # fill color when active

    def __init__(self, draw_ref: Callable[[], object] | None = None):
        self._draw_ref = draw_ref

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _draw(self):
        return self._draw_ref() if self._draw_ref else None

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def draw_border(self) -> None:
        """Render the outer UI border onto the current draw surface."""
        d = self._draw_ref and self._draw_ref()
        if not d:
            return
        d.line([(127, 12), (127, 127)], fill=self.border, width=5)
        d.line([(127, 127), (0, 127)], fill=self.border, width=5)
        d.line([(0, 127), (0, 12)], fill=self.border, width=5)
        d.line([(0, 12), (128, 12)], fill=self.border, width=5)

    def draw_menu_background(self) -> None:
        """Fill the menu interior area using the background color."""
        d = self._draw_ref and self._draw_ref()
        if not d:
            return
        d.rectangle((3, 14, 124, 124), fill=self.background)

    # ------------------------------------------------------------------
    # Color access (index based for legacy compatibility)
    # ------------------------------------------------------------------
    def set_color(self, index: int, value: str) -> None:
        """Set a color by legacy index mapping.

        Automatically re-renders the border if index 1 (border) changes.
        """
        if index == 0:
            self.background = value
        elif index == 1:
            self.border = value
            # Re-draw immediately for visual feedback
            self.draw_border()
        elif index == 2:
            self.text = value
        elif index == 3:
            self.selected_text = value
        elif index == 4:
            self.select = value
        elif index == 5:
            self.gamepad = value
        elif index == 6:
            self.gamepad_fill = value

    def get_color(self, index: int) -> str:
        if index == 0:
            return self.background
        if index == 1:
            return self.border
        if index == 2:
            return self.text
        if index == 3:
            return self.selected_text
        if index == 4:
            return self.select
        if index == 5:
            return self.gamepad
        if index == 6:
            return self.gamepad_fill
        raise IndexError(f"Unknown color index: {index}")

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, str]:
        """Return a JSON‑serializable dict of the color scheme."""
        return {
            "BORDER": self.border,
            "BACKGROUND": self.background,
            "TEXT": self.text,
            "SELECTED_TEXT": self.selected_text,
            "SELECTED_TEXT_BACKGROUND": self.select,
            "GAMEPAD": self.gamepad,
            "GAMEPAD_FILL": self.gamepad_fill,
        }

    def load_dict(self, data: Dict[str, str]) -> None:
        """Load colors from a dict produced by `to_dict` (tolerant)."""
        try:
            self.set_color(1, data["BORDER"])  # ensure border redraw
        except KeyError:
            pass
        self.background = data.get("BACKGROUND", self.background)
        self.text = data.get("TEXT", self.text)
        self.selected_text = data.get("SELECTED_TEXT", self.selected_text)
        self.select = data.get("SELECTED_TEXT_BACKGROUND", self.select)
        self.gamepad = data.get("GAMEPAD", self.gamepad)
        self.gamepad_fill = data.get("GAMEPAD_FILL", self.gamepad_fill)

