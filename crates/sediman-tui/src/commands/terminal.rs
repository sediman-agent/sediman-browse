use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_terminal(app: &mut App, args: &str) {
    let args = args.trim().to_lowercase();
    if args.is_empty() {
        app.step_log.push(format!(" Terminal access: {}", app.permission.current_label()));
        app.step_log.push(" Usage: /terminal on|off".into());
        return;
    }
    match args.as_str() {
        "on" => {
            app.step_log.push("✓ Terminal commands auto-approved.".into());
        }
        "off" => {
            app.permission.cycle();
            app.step_log.push("✓ Terminal approval required.".into());
        }
        _ => app.step_log.push("Usage: /terminal on|off".into()),
    }
}

pub static CMD_TERMINAL: Command = Command {
    name: "/terminal",
    aliases: &[],
    description: "Show or set terminal access: /terminal [on|off]",
    category: CommandCategory::Terminal,
    handler: |_, _| Box::new(std::future::ready(())),
};
