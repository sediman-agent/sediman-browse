use sediman_tui_core::command::{Command, CommandCategory};
use sediman_tui_core::styling::themes;

use crate::app::{App, AppModal, ModalLine};

pub static CMD_THEMES: Command = Command {
    name: "/themes",
    aliases: &["/theme"],
    description: "List and switch color themes",
    category: CommandCategory::General,
};

pub async fn handle_themes(app: &mut App, args: &str) {
    let name = args.trim();
    if name.is_empty() {
        let names = themes::list_theme_names();
        let mut lines = vec![
            ModalLine::heading("  Available Themes"),
            ModalLine::blank(),
        ];
        for n in &names {
            if *n == app.theme_name {
                lines.push(ModalLine::primary(format!("  {} \u{25c6} (current)", n)));
            } else {
                lines.push(ModalLine::normal(format!("  {}", n)));
            }
        }
        lines.push(ModalLine::blank());
        lines.push(ModalLine::muted("  /themes <name> to switch"));
        app.active_modal = Some(AppModal::Info {
            title: "Themes".into(),
            lines,
            scroll: 0,
        });
        return;
    }
    if let Some(theme) = themes::load_theme(name) {
        app.theme = theme;
        app.theme_name = name.to_string();
        app.add_system_message(format!("Theme switched to: {}", name));
    } else {
        app.add_system_message(format!("Unknown theme: {}. Available: {}", name, themes::list_theme_names().join(", ")));
    }
}
