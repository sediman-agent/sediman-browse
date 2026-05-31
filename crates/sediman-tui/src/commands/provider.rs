use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

/// `/provider` without args — opens the unified model picker.
/// `/provider <name>` — switches provider directly and syncs with backend.
pub async fn handle_provider(app: &mut App, args: &str) {
    if args.is_empty() {
        app.open_model_dialog();
        return;
    }

    let name = args.trim().to_lowercase();

    // Find the provider's default model and base_url
    let (default_model, default_url) = app
        .available_providers
        .iter()
        .find(|p| p.name == name)
        .map(|p| (p.default_model.clone(), p.default_base_url.clone()))
        .unwrap_or(("default".into(), None));

    // Sync with backend
    if let Err(e) = app.bridge.switch_model(&name, Some(&default_model), default_url.as_deref()).await {
        app.add_error_message(format!("Failed to switch provider: {}", e));
        return;
    }

    app.provider = name.clone();
    app.model = Some(default_model);
    app.add_system_message(format!("Provider: {}", name));
}

pub static CMD_PROVIDER: Command = Command {
    name: "/provider",
    aliases: &[],
    description: "Select LLM provider",
    category: CommandCategory::Agent,
};
