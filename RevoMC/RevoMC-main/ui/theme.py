"""Colour palettes for the FlowwwClient interface (light and dark, violet accent).

Every colour value inside one palette is unique so a live theme switch can swap
colours by value (see :func:`retheme_widget_tree`).  Brand accent colours are
identical in both palettes, so they never change when the theme changes.
"""

DEFAULT_THEME = "dark"
THEME_NAMES = ("light", "dark")

_LIGHT = {
    "BG_PRIMARY": "#FDFCFF",
    "BG_SECONDARY": "#F3F1FB",
    "BG_CONSOLE": "#E9E6F7",
    "BG_CARD": "#FAF9FE",
    "BORDER_COL": "#D9D5F0",
    "ACCENT": "#6C5CE7",
    "ACCENT_DARK": "#5646D6",
    "ACCENT_ALT": "#3B82F6",
    "ACCENT_TEXT": "#FFFFFF",
    "RED": "#D64550",
    "ENABLED": "#17935A",
    "WARNING": "#C97A12",
    "MS_BLUE": "#2F7EE7",
    "MS_BLUE_DARK": "#1A5EBF",
    "TEXT_FG": "#1B1830",
    "TEXT_MUTED": "#5E5A7C",
    "TEXT_LABEL": "#6A6689",
    "NEUTRAL": "#8B88A6",
    "STAGE_TOP": "#EFEBFF",
    "STAGE_BOTTOM": "#DCD6F7",
    "NAMETAG_BG": "#221E3D",
}

_DARK = {
    "BG_PRIMARY": "#0B0A1A",
    "BG_SECONDARY": "#14112A",
    "BG_CONSOLE": "#0E0C20",
    "BG_CARD": "#1B1738",
    "BORDER_COL": "#2E2A52",
    "ACCENT": "#6C5CE7",
    "ACCENT_DARK": "#5646D6",
    "ACCENT_ALT": "#4DA3FF",
    "ACCENT_TEXT": "#FFFFFF",
    "RED": "#E0525F",
    "ENABLED": "#1FA86A",
    "WARNING": "#F0A030",
    "MS_BLUE": "#2F7EE7",
    "MS_BLUE_DARK": "#1A5EBF",
    "TEXT_FG": "#F4F3FA",
    "TEXT_MUTED": "#A9A6C6",
    "TEXT_LABEL": "#9A97B5",
    "NEUTRAL": "#6F6C8F",
    "STAGE_TOP": "#1F1A45",
    "STAGE_BOTTOM": "#0F0C26",
    "NAMETAG_BG": "#05040F",
}

_PALETTES = {"light": _LIGHT, "dark": _DARK}

# Widget options that can hold a palette colour.
_COLOR_OPTIONS = (
    "fg_color", "bg_color", "border_color", "hover_color", "text_color",
    "text_color_disabled", "button_color", "button_hover_color",
    "progress_color", "selected_color", "selected_hover_color",
    "unselected_color", "unselected_hover_color", "checkmark_color",
    "placeholder_text_color", "scrollbar_fg_color", "scrollbar_button_color",
    "scrollbar_button_hover_color", "label_fg_color", "dropdown_fg_color",
    "dropdown_hover_color", "dropdown_text_color", "top_fg_color",
)


def normalize_theme_name(name) -> str:
    """Map any stored theme value (including legacy ones) to a known theme."""
    if isinstance(name, str) and name.lower() in _PALETTES:
        return name.lower()
    return DEFAULT_THEME


def get_theme(name: str = DEFAULT_THEME) -> dict:
    """Return a copy of the requested palette (unknown names give the default)."""
    return dict(_PALETTES[normalize_theme_name(name)])


def is_light(name: str) -> bool:
    return normalize_theme_name(name) == "light"


def apply_customtkinter_palette(theme: dict | None = None) -> None:
    """Apply a palette to the toolkit defaults used by new widgets and dialogs."""
    import customtkinter as ctk

    palette = theme or get_theme()
    toolkit = ctk.ThemeManager.theme

    def dual(color: str) -> list[str]:
        return [color, color]

    accent = dual(palette["ACCENT"])
    accent_dark = dual(palette["ACCENT_DARK"])
    accent_text = dual(palette["ACCENT_TEXT"])
    border = dual(palette["BORDER_COL"])
    text = dual(palette["TEXT_FG"])
    muted = dual(palette["TEXT_MUTED"])
    primary = dual(palette["BG_PRIMARY"])
    secondary = dual(palette["BG_SECONDARY"])
    card = dual(palette["BG_CARD"])
    overrides = {
        "CTk": {"fg_color": primary},
        "CTkToplevel": {"fg_color": primary},
        "CTkFrame": {
            "fg_color": secondary,
            "top_fg_color": card,
            "border_color": border,
        },
        "CTkLabel": {"text_color": text},
        "CTkButton": {
            "fg_color": accent,
            "hover_color": accent_dark,
            "text_color": accent_text,
            "text_color_disabled": muted,
            "border_color": border,
        },
        "CTkCheckBox": {
            "fg_color": accent,
            "hover_color": accent_dark,
            "border_color": border,
            "checkmark_color": accent_text,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkRadioButton": {
            "fg_color": accent,
            "hover_color": accent_dark,
            "border_color": border,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkSwitch": {
            "fg_color": border,
            "progress_color": accent,
            "button_color": accent_text,
            "button_hover_color": accent_text,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkEntry": {
            "fg_color": primary,
            "border_color": border,
            "text_color": text,
            "placeholder_text_color": muted,
        },
        "CTkComboBox": {
            "fg_color": primary,
            "border_color": border,
            "button_color": accent_dark,
            "button_hover_color": accent,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkOptionMenu": {
            "fg_color": secondary,
            "button_color": accent,
            "button_hover_color": accent_dark,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkSegmentedButton": {
            "fg_color": primary,
            "selected_color": border,
            "selected_hover_color": border,
            "unselected_color": secondary,
            "unselected_hover_color": card,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkSlider": {
            "fg_color": border,
            "progress_color": accent,
            "button_color": accent,
            "button_hover_color": accent_dark,
        },
        "CTkProgressBar": {"fg_color": border, "progress_color": accent},
        "CTkScrollbar": {
            "fg_color": secondary,
            "button_color": border,
            "button_hover_color": accent,
        },
        "CTkTextbox": {
            "fg_color": primary,
            "border_color": border,
            "text_color": text,
            "scrollbar_button_color": border,
            "scrollbar_button_hover_color": accent,
        },
        "CTkScrollableFrame": {"label_fg_color": secondary},
    }
    for widget, values in overrides.items():
        toolkit[widget].update(values)


def color_map(old: dict, new: dict) -> dict:
    """Map every colour value of ``old`` to the matching value of ``new``."""
    mapping = {}
    for key, value in old.items():
        target = new.get(key)
        if isinstance(value, str) and isinstance(target, str) and value.lower() != target.lower():
            mapping[value.lower()] = target
    return mapping


def _map_value(value, mapping: dict):
    if isinstance(value, str):
        return mapping.get(value.lower(), value)
    if isinstance(value, (list, tuple)):
        mapped = [_map_value(item, mapping) for item in value]
        return type(value)(mapped) if isinstance(value, tuple) else mapped
    return value


def retheme_widget_tree(root, mapping: dict) -> int:
    """Recolour ``root`` and every descendant by swapping palette colours.

    Returns the number of options that were changed.  Widgets that do not know an
    option, or that were destroyed while walking, are skipped.
    """
    changed = 0
    stack = [root]
    while stack:
        widget = stack.pop()
        try:
            children = widget.winfo_children()
        except Exception:  # destroyed or foreign widget
            continue
        stack.extend(children)
        cget = getattr(widget, "cget", None)
        configure = getattr(widget, "configure", None)
        if cget is None or configure is None:
            continue
        updates = {}
        for option in _COLOR_OPTIONS:
            try:
                value = cget(option)
            except Exception:
                continue
            mapped = _map_value(value, mapping)
            if mapped != value:
                updates[option] = mapped
        if updates:
            try:
                configure(**updates)
                changed += len(updates)
            except Exception:
                for option, value in updates.items():
                    try:
                        configure(**{option: value})
                        changed += 1
                    except Exception:
                        continue
    return changed
