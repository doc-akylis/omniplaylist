from nicegui import ui
from app.ui.theme_manager import theme_manager


def apply_theme():
    """Apply active theme configuration dynamically across pages."""
    theme_manager.load_settings()
    theme_manager.apply_current_theme()


# Theme helper classes
CARD_STYLE = "bg-[#181818] hover:bg-[#222222] transition-colors duration-200 rounded-xl p-4 border border-[#2A2A2A]"
SIDEBAR_ITEM = "flex items-center gap-3 px-4 py-2.5 rounded-lg text-gray-300 hover:text-white hover:bg-[#282828] cursor-pointer transition-all font-medium text-sm w-full"
ACTIVE_SIDEBAR_ITEM = "flex items-center gap-3 px-4 py-2.5 rounded-lg text-white bg-[#282828] font-semibold text-sm w-full border-l-4 border-[#1DB954]"
