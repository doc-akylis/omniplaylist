from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UserHistory, UserSettings
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager


def render_settings_page():
    """Render the Settings and Global Theme Customization center."""
    with main_layout(current_page="settings"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Configurações & Personalização Visual").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Altere o tema global da aplicação, bordas, densidade e controle o histórico de recomendações."
                ).classes("text-sm text-gray-400")

        # Themes Grid Section
        with ui.column().classes(f"w-full {card_cls} mb-6 gap-4"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("palette", color="primary")
                ui.label("Temas Globais da Interface").classes("text-lg font-bold text-white")

            ui.label("Clique em um tema para aplicar instantaneamente a toda a aplicação:").classes("text-xs text-gray-400")

            with ui.row().classes("w-full gap-4 flex-wrap"):
                for t_name, t_def in theme_manager.PRESET_THEMES.items():
                    is_active = (t_name == theme_manager.current_theme_name)
                    with ui.column().classes(
                        f"w-56 p-4 rounded-xl border cursor-pointer transition-all hover:scale-105 "
                        f"{'border-primary bg-[#252525]' if is_active else 'border-[#333] bg-[#1E1E1E]'}"
                    ).on("click", lambda _, name=t_name: select_theme(name)):
                        with ui.row().classes("items-center justify-between w-full mb-2"):
                            ui.label(t_name).classes(f"text-sm font-bold {'text-primary' if is_active else 'text-white'}")
                            if is_active:
                                ui.badge("Ativo", color="primary").props("dense")

                        # Palette previews dots
                        with ui.row().classes("gap-2 items-center mb-2"):
                            ui.html(f'<div style="width:16px;height:16px;border-radius:50%;background:{t_def.primary};"></div>')
                            ui.html(f'<div style="width:16px;height:16px;border-radius:50%;background:{t_def.secondary};"></div>')
                            ui.html(f'<div style="width:16px;height:16px;border-radius:50%;background:{t_def.dark};border:1px solid #444;"></div>')

                        ui.label(t_def.description).classes("text-[11px] text-gray-400 leading-tight")

        # Density and Rounding Row
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            with ui.column().classes(f"flex-1 {card_cls} gap-3"):
                ui.label("Arredondamento dos Cartões").classes("text-sm font-bold text-white")
                rounding_select = ui.select(
                    {
                        "rounded-none": "Sem Arredondamento (Reto)",
                        "rounded-lg": "Suave (rounded-lg)",
                        "rounded-xl": "Padrão Moderno (rounded-xl)",
                        "rounded-3xl": "Curvo Acentuado (rounded-3xl)",
                    },
                    value=theme_manager.card_rounding,
                ).props("dark outlined dense")

                rounding_select.on("update:model-value", lambda e: update_style(e.value, theme_manager.density))

            with ui.column().classes(f"flex-1 {card_cls} gap-3"):
                ui.label("Densidade Visual").classes("text-sm font-bold text-white")
                density_select = ui.select(
                    {"comfortable": "Confortável (Padrão)", "compact": "Compacta (Mais elementos na tela)"},
                    value=theme_manager.density,
                ).props("dark outlined dense")

                density_select.on("update:model-value", lambda e: update_style(theme_manager.card_rounding, e.value))

        # Privacy & History Control Card
        with ui.column().classes(f"w-full {card_cls} gap-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("security", color="info")
                ui.label("Privacidade & Histórico de Recomendações").classes("text-lg font-bold text-white")

            history_cb = ui.checkbox(
                "Registrar histórico de reproduções para aprimorar o Music Discovery e Smart DJ",
                value=True,
            ).props("dark color=primary")

            with ui.row().classes("items-center justify-between w-full pt-2"):
                ui.label("Limpar dados de histórico registrados até o momento:").classes("text-xs text-gray-400")
                ui.button("Limpar Histórico", icon="delete_sweep", on_click=lambda: clear_user_history()).props(
                    "flat color=negative dense no-caps"
                )

        def select_theme(name: str):
            theme_manager.save_settings(name, theme_manager.card_rounding, theme_manager.density)
            theme_manager.apply_current_theme()
            ui.notify(f"Tema alterado para: {name}", type="positive")
            ui.navigate.to("/settings")

        def update_style(rounding: str, density: str):
            theme_manager.save_settings(theme_manager.current_theme_name, rounding, density)
            ui.notify("Estilo visual atualizado!", type="positive")
            ui.navigate.to("/settings")

        def clear_user_history():
            with Session(engine) as session:
                records = session.exec(select(UserHistory)).all()
                for r in records:
                    session.delete(r)
                session.commit()
            ui.notify(f"{len(records)} eventos de histórico foram excluídos.", type="info")
