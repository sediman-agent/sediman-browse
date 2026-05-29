use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;
use crate::app::AppModal;

const DEFAULT_SOUL: &str = "You are Sediman, a self-improving browser automation agent.

You are pragmatic, concise, and efficient. You complete browser tasks with minimal steps.

Communication style:
- Be brief but thorough
- When reporting results, lead with the answer
- If something fails, explain what went wrong and what you tried
- Proactively suggest improvements when you notice patterns";

/// `/soul` — opens interactive soul editor (loads current personality).
/// `/soul <text>` — directly sets personality.
/// `/soul reset` — resets to default.
pub async fn handle_soul(app: &mut App, args: &str) {
    let args = args.trim();
    if args.is_empty() {
        // Load current personality from file, or use default
        let soul_text = load_current_soul();
        app.soul_editor_input = soul_text;
        app.active_modal = Some(AppModal::SoulEditor);
        return;
    }
    if args == "reset" {
        match app.bridge.reset_soul().await {
            Ok(()) => app.add_system_message("Personality reset to default.".into()),
            Err(e) => app.add_error_message(format!("Failed to reset personality: {}", e)),
        }
    } else {
        match app.bridge.set_soul(args).await {
            Ok(()) => app.add_system_message("Personality set.".into()),
            Err(e) => app.add_error_message(format!("Failed to set personality: {}", e)),
        }
    }
}

/// Read the current soul from ~/.sediman/SOUL.md, falling back to default.
fn load_current_soul() -> String {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let soul_path = std::path::Path::new(&home).join(".sediman/SOUL.md");
    if soul_path.exists() {
        std::fs::read_to_string(&soul_path).unwrap_or_else(|_| DEFAULT_SOUL.to_string())
    } else {
        DEFAULT_SOUL.to_string()
    }
}

pub static CMD_SOUL: Command = Command {
    name: "/soul",
    aliases: &[],
    description: "View or edit agent personality",
    category: CommandCategory::Agent,
};
