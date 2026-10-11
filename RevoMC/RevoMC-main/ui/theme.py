"""Central color palette for the FlowwwClient interface."""


_PALETTE = {
    "BG_PRIMARY": "#0B0D10",
    "BG_SECONDARY": "#14171C",
    "BG_CONSOLE": "#090A0C",
    "BG_CARD": "#191D23",
    "BORDER_COL": "#292E36",
    "ACCENT": "#E53945",
    "ACCENT_DARK": "#C62835",
    "ACCENT_ALT": "#FF4655",
    "RED": "#FF5964",
    "MS_BLUE": "#2F7EE7",
    "MS_BLUE_DARK": "#1A5EBF",
    "TEXT_FG": "#F4F5F7",
    "TEXT_MUTED": "#A2A8B2",
    "TEXT_LABEL": "#858C97",
}


def get_theme(_name: str = "crimson") -> dict:
    """Return the single supported brand palette.

    The argument remains accepted so older configuration values continue to load.
    """
    return dict(_PALETTE)


def apply_customtkinter_palette() -> None:
    """Apply the brand palette to toolkit defaults used across windows and dialogs."""
    import customtkinter as ctk

    theme = ctk.ThemeManager.theme

    def dual(color: str) -> list[str]:
        return [color, color]

    accent = dual(_PALETTE["ACCENT"])
    accent_dark = dual(_PALETTE["ACCENT_DARK"])
    border = dual(_PALETTE["BORDER_COL"])
    text = dual(_PALETTE["TEXT_FG"])
    muted = dual(_PALETTE["TEXT_MUTED"])
    primary = dual(_PALETTE["BG_PRIMARY"])
    secondary = dual(_PALETTE["BG_SECONDARY"])
    card = dual(_PALETTE["BG_CARD"])
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
            "text_color": text,
            "text_color_disabled": muted,
            "border_color": border,
        },
        "CTkCheckBox": {
            "fg_color": accent,
            "hover_color": accent_dark,
            "border_color": border,
            "checkmark_color": primary,
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
            "button_color": accent,
            "button_hover_color": accent_dark,
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
            "selected_color": accent,
            "selected_hover_color": accent_dark,
            "unselected_color": secondary,
            "unselected_hover_color": card,
            "text_color": text,
            "text_color_disabled": muted,
        },
        "CTkSlider": {
            "fg_color": primary,
            "progress_color": accent,
            "button_color": accent,
            "button_hover_color": accent_dark,
        },
        "CTkProgressBar": {"fg_color": primary, "progress_color": accent},
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
        theme[widget].update(values)
