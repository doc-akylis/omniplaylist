from dataclasses import dataclass
from typing import Any, Optional
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UserSettings


@dataclass
class ThemeDefinition:
    """Palette and visual specification for a named theme."""

    name: str
    primary: str
    secondary: str
    accent: str
    dark: str
    card_bg: str
    text_color: str
    is_dark_mode: bool
    description: str


class ThemeManager:
    """Global styling and multi-theme orchestrator for NiceGUI."""

    PRESET_THEMES = {
        "Omni Green": ThemeDefinition(
            name="Omni Green",
            primary="#1DB954",
            secondary="#282828",
            accent="#1ED760",
            dark="#121212",
            card_bg="#181818",
            text_color="#E5E7EB",
            is_dark_mode=True,
            description="Identidade clássica original inspirada em streamings premium.",
        ),
        "Midnight Blue": ThemeDefinition(
            name="Midnight Blue",
            primary="#3B82F6",
            secondary="#1E293B",
            accent="#60A5FA",
            dark="#0A0F1D",
            card_bg="#131C31",
            text_color="#F1F5F9",
            is_dark_mode=True,
            description="Tons azuis profundos noturnos para ambientes de baixa iluminação.",
        ),
        "Purple Neon": ThemeDefinition(
            name="Purple Neon",
            primary="#A855F7",
            secondary="#2D1B4E",
            accent="#C084FC",
            dark="#0F091A",
            card_bg="#1B122C",
            text_color="#F3E8FF",
            is_dark_mode=True,
            description="Visual synthwave/cyberpunk com tons roxos vibrantes.",
        ),
        "Crimson": ThemeDefinition(
            name="Crimson",
            primary="#EF4444",
            secondary="#331A1A",
            accent="#F87171",
            dark="#140C0C",
            card_bg="#201313",
            text_color="#FEE2E2",
            is_dark_mode=True,
            description="Visual marcante com acentos vermelho carmesim.",
        ),
        "AMOLED Black": ThemeDefinition(
            name="AMOLED Black",
            primary="#00FF66",
            secondary="#111111",
            accent="#33FF88",
            dark="#000000",
            card_bg="#080808",
            text_color="#FFFFFF",
            is_dark_mode=True,
            description="Preto absoluto 100% otimizado para telas OLED e máximo contraste.",
        ),
        "Graphite": ThemeDefinition(
            name="Graphite",
            primary="#E2E8F0",
            secondary="#262626",
            accent="#94A3B8",
            dark="#171717",
            card_bg="#212121",
            text_color="#F8FAFC",
            is_dark_mode=True,
            description="Estilo industrial minimalista e neutro em escala de cinza.",
        ),
        "Light Studio": ThemeDefinition(
            name="Light Studio",
            primary="#10B981",
            secondary="#E2E8F0",
            accent="#059669",
            dark="#F8FAFC",
            card_bg="#FFFFFF",
            text_color="#0F172A",
            is_dark_mode=False,
            description="Tema claro moderno de alto contraste para trabalho diurno.",
        ),
    }

    def __init__(self):
        self.current_theme_name: str = "Omni Green"
        self.card_rounding: str = "rounded-xl"
        self.density: str = "comfortable"

    def get_current_theme(self) -> ThemeDefinition:
        """Fetch active theme definition."""
        return self.PRESET_THEMES.get(self.current_theme_name, self.PRESET_THEMES["Omni Green"])

    def load_settings(self) -> None:
        """Load user theme preferences from database if present."""
        try:
            with Session(engine) as session:
                settings = session.exec(select(UserSettings)).first()
                if settings:
                    if settings.theme_name in self.PRESET_THEMES:
                        self.current_theme_name = settings.theme_name
                    self.card_rounding = settings.card_rounding
                    self.density = settings.density
        except Exception as e:
            print(f"[ThemeManager] Settings load note: {e}")

    def save_settings(self, theme_name: str, card_rounding: str = "rounded-xl", density: str = "comfortable") -> None:
        """Persist theme selection to database."""
        if theme_name in self.PRESET_THEMES:
            self.current_theme_name = theme_name
        self.card_rounding = card_rounding
        self.density = density

        try:
            with Session(engine) as session:
                settings = session.exec(select(UserSettings)).first()
                if not settings:
                    settings = UserSettings(
                        theme_name=self.current_theme_name,
                        card_rounding=self.card_rounding,
                        density=self.density,
                    )
                else:
                    settings.theme_name = self.current_theme_name
                    settings.card_rounding = self.card_rounding
                    settings.density = self.density
                session.add(settings)
                session.commit()
        except Exception as e:
            print(f"[ThemeManager] Settings save note: {e}")

    def apply_current_theme(self) -> None:
        """Apply Tailwind & Quasar colors, body background and typography to NiceGUI page."""
        t = self.get_current_theme()

        ui.colors(
            primary=t.primary,
            secondary=t.secondary,
            accent=t.accent,
            dark=t.dark,
            positive="#10B981",
            negative="#EF4444",
            info="#3B82F6",
            warning="#F59E0B",
        )

        ui.add_head_html(f"""
        <style>
            :root {{
                --theme-primary: {t.primary};
                --theme-bg: {t.dark};
                --theme-card: {t.card_bg};
                --theme-text: {t.text_color};
            }}
            body {{
                background-color: {t.dark} !important;
                color: {t.text_color} !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                overflow: hidden;
            }}
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}
            ::-webkit-scrollbar-track {{
                background: {t.dark};
            }}
            ::-webkit-scrollbar-thumb {{
                background: {t.secondary};
                border-radius: 4px;
            }}
            ::-webkit-scrollbar-thumb:hover {{
                background: {t.primary};
            }}
        </style>
        """)

    @property
    def card_style(self) -> str:
        """Dynamic Tailwind classes for cards based on current theme."""
        t = self.get_current_theme()
        border_col = "#2A2A2A" if t.is_dark_mode else "#E2E8F0"
        return f"bg-[{t.card_bg}] transition-all duration-200 {self.card_rounding} p-4 border border-[{border_col}]"


# Singleton instance
theme_manager = ThemeManager()
