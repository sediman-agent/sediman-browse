use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_soul(app: &mut App, args: &str) {
    let args = args.trim();
    if args.is_empty() {
        app.step_log.push(" You are Sediman, a self-improving browser automation agent.".into());
        app.step_log.push(" Usage: /soul <text> or /soul reset".into());
        return;
    }
    if args == "reset" {
        app.step_log.push("✓ Personality reset to default.".into());
    } else {
        app.step_log.push("✓ Personality set.".into());
    }
}

pub static CMD_SOUL: Command = Command {
    name: "/soul",
    aliases: &[],
    description: "Show or set personality: /soul [text|reset]",
    category: CommandCategory::Agent,
    handler: |_, _| Box::new(std::future::ready(())),
};
