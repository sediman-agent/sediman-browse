use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal};

/// `/provider` without args — opens provider picker modal.
/// `/provider <name>` — switches provider directly.
pub async fn handle_provider(app: &mut App, args: &str) {
    if args.is_empty() {
        // Pre-select current provider
        let providers = ["openai", "ollama"];
        app.provider_picker_index = providers.iter()
            .position(|&p| p == app.provider)
            .unwrap_or(0);
        app.provider_picker_input.clear();
        app.active_modal = Some(AppModal::ProviderPicker);
        return;
    }

    // Direct switch: /provider openai or /provider <url>
    let name = args.trim().to_lowercase();
    app.provider = name.clone();
    app.add_system_message(format!("Provider: {}", name));
}

pub static CMD_PROVIDER: Command = Command {
    name: "/provider",
    aliases: &[],
    description: "Select LLM provider",
    category: CommandCategory::Agent,
};
