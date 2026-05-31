use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

const VALID_BACKENDS: &[&str] = &["internal", "claude-code", "codex", "opencode"];

/// `/coder` without args — open picker popup.
/// `/coder <backend>` — switch coder backend directly.
pub async fn handle_coder(app: &mut App, args: &str) {
    let input = args.trim().to_lowercase();

    if input.is_empty() {
        // Open picker, pre-select current backend
        app.coder_picker_selected = VALID_BACKENDS.iter()
            .position(|&b| b == app.coder_backend)
            .unwrap_or(0);
        app.active_modal = Some(crate::app::AppModal::CoderPicker);
        return;
    }

    if VALID_BACKENDS.contains(&input.as_str()) {
        let old = app.coder_backend.clone();
        app.coder_backend = input.clone();
        app.add_system_message(format!(
            "Coder backend: {} → {}",
            old, input
        ));
        // Persist
        let config = crate::config::TuiConfig::load();
        let mut config = config;
        config.coder_backend = app.coder_backend.clone();
        if let Err(e) = config.save() {
            app.add_error_message(format!("Failed to save config: {}", e));
        }
    } else {
        app.add_error_message(format!(
            "Unknown coder backend '{}'. Options: {}",
            input,
            VALID_BACKENDS.join(", ")
        ));
    }
}

pub static CMD_CODER: Command = Command {
    name: "/coder",
    aliases: &[],
    description: "Set coder backend (internal|claude-code|codex|opencode)",
    category: CommandCategory::Agent,
};
