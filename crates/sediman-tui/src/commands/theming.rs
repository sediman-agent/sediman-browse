use sediman_tui_core::command::{Command, CommandCategory};
use sediman_tui_core::styling;

use crate::app::{App, AppModal};

pub static CMD_THEMES: Command = Command {
    name: "/themes",
    aliases: &[],
    description: "List and switch color themes",
    category: CommandCategory::General,
};

pub async fn handle_themes(app: &mut App, args: &str) {
    let name = args.trim();
    if name.is_empty() {
        let names = styling::list_theme_names();
        let current_idx = names.iter().position(|n| n == &app.theme_name).unwrap_or(0);
        app.theme_picker_saved_theme = app.theme.clone();
        app.theme_picker_saved_name = app.theme_name.clone();
        app.theme_picker_names = names;
        app.theme_picker_selected = current_idx;
        app.active_modal = Some(AppModal::ThemePicker);
        return;
    }
    switch_theme(app, name);
}

fn switch_theme(app: &mut App, name: &str) {
    if let Some(theme) = styling::load_theme(name) {
        app.theme = theme;
        app.theme_name = name.to_string();
        app.add_system_message(format!("Theme switched to: {}", name));
        save_config_now(app);
    } else {
        app.add_error_message(format!(
            "Unknown theme: {}. Available: {}",
            name,
            styling::list_theme_names().join(", ")
        ));
    }
}

pub fn save_config_now(app: &App) {
    let config = crate::config::TuiConfig {
        theme: app.theme_name.clone(),
        permission_mode: app.permission.current_label().to_string(),
        side_panel_open: app.show_side_panel,
        side_panel_tab: match app.side_panel_tab {
            crate::app::SideTab::Skills => "Skills".into(),
            crate::app::SideTab::Memory => "Memory".into(),
            crate::app::SideTab::Schedule => "Schedule".into(),
            crate::app::SideTab::Status => "Status".into(),
        },
        headless: app.headless,
        coder_backend: app.coder_backend.clone(),
    };
    if let Err(e) = config.save() {
        eprintln!("Warning: {}", e);
    }
}
