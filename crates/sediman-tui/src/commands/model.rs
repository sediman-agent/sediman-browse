use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

/// `/model` without args — opens the unified model picker (OpenCode-style).
/// `/model <provider/model>` — switches directly and syncs with backend.
/// `/model <model>` — switches model on current provider and syncs.
pub async fn handle_model(app: &mut App, args: &str) {
    if args.is_empty() {
        app.open_model_dialog();
        return;
    }

    // Parse: /model <provider/model> or /model <model>
    let (new_provider, new_model) = if let Some(idx) = args.find('/') {
        (args[..idx].to_string(), Some(args[idx + 1..].to_string()))
    } else {
        (app.provider.clone(), Some(args.to_string()))
    };

    // Find the provider's default base_url
    let base_url = app
        .available_providers
        .iter()
        .find(|p| p.name == new_provider)
        .and_then(|p| p.default_base_url.clone());

    // Sync with backend
    let model_str = new_model.as_deref().unwrap_or("default");
    if let Err(e) = app.bridge.switch_model(&new_provider, Some(model_str), base_url.as_deref()).await {
        app.add_error_message(format!("Failed to switch model: {}", e));
        return;
    }

    app.provider = new_provider;
    app.model = new_model;
    app.add_system_message(format!("Switched to {}", app.display_model_id()));
}

pub static CMD_MODEL: Command = Command {
    name: "/model",
    aliases: &["/models"],
    description: "Select, switch, or manage models",
    category: CommandCategory::Agent,
};
