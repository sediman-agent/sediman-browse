use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_terminal(app: &mut App, args: &str) {
    let args = args.trim().to_lowercase();
    if args.is_empty() {
        app.add_system_message(format!("Terminal access: {}", app.permission.current_label()));
        app.add_system_message("Usage: /terminal on|off".into());
        return;
    }
    match args.as_str() {
        "on" => {
            while !app.permission.is_allowed("") {
                app.permission.cycle();
            }
            app.add_system_message("Terminal commands auto-approved.".into());
        }
        "off" => {
            app.permission.set_plan_mode(false);
            for _ in 0..4 {
                app.permission.cycle();
                if app.permission.current_label() == "ask" {
                    break;
                }
            }
            app.add_system_message("Terminal approval required.".into());
        }
        _ => app.add_system_message("Usage: /terminal on|off".into()),
    }
}

pub static CMD_TERMINAL: Command = Command {
    name: "/terminal",
    aliases: &[],
    description: "Show or set terminal access: /terminal [on|off]",
    category: CommandCategory::Terminal,
};
