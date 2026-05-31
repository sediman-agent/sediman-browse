use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

/// `/connect` without args — opens the unified model picker.
/// `/connect <name>` — connects a provider (prompts for API key if needed).
pub async fn handle_connect(app: &mut App, args: &str) {
    if !args.is_empty() {
        let name = args.trim().to_lowercase();
        let needs_key = app
            .available_providers
            .iter()
            .find(|p| p.name == name)
            .map(|p| p.needs_api_key)
            .unwrap_or(true);

        if !needs_key {
            // Local provider — switch directly
            let default_url = app
                .available_providers
                .iter()
                .find(|p| p.name == name)
                .and_then(|p| p.default_base_url.clone());
            let default_model = app
                .available_providers
                .iter()
                .find(|p| p.name == name)
                .map(|p| p.default_model.clone())
                .unwrap_or_else(|| "default".into());

            if let Err(e) = app.bridge.switch_model(&name, Some(&default_model), default_url.as_deref()).await {
                app.add_error_message(format!("Failed to connect: {}", e));
                return;
            }
            app.provider = name.clone();
            app.model = Some(default_model);
            app.add_system_message(format!("Provider: {} (local, no key needed)", name));
            return;
        }

        // Needs API key — open the key prompt
        app.connect_target = Some(name);
        app.api_key_input.clear();
        app.active_modal = Some(crate::app::AppModal::ApiKeyPrompt);
        return;
    }

    // No args — open unified picker
    app.open_model_dialog();
}

pub static CMD_CONNECT: Command = Command {
    name: "/connect",
    aliases: &[],
    description: "Connect an LLM provider (save API key)",
    category: CommandCategory::Agent,
};
