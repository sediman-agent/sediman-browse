use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal};

/// `/model` without args — opens the model picker modal.
/// `/model <name>` — switches directly and saves to the list.
/// `/model remove <name>` — removes a saved model from the list.
pub async fn handle_model(app: &mut App, args: &str) {
    if args.is_empty() {
        // Open the model picker modal with saved models
        if app.model_picker_list.is_empty() {
            let config = crate::config::TuiConfig::load();
            app.model_picker_list = config.saved_models;
        }
        app.model_picker_index = 0;
        app.model_picker_input.clear();
        app.active_modal = Some(AppModal::ModelPicker);
        return;
    }

    // `/model remove <name>` — remove a saved model
    if let Some(name) = args.strip_prefix("remove ") {
        let name = name.trim();
        app.model_picker_list.retain(|m| m != name);
        save_model_list(&app.model_picker_list);
        app.add_system_message(format!("Removed model: {}", name));
        return;
    }

    // `/model <provider:model>` or `/model <model>` — switch and save
    let (new_provider, new_model) = if let Some(idx) = args.find(':') {
        (args[..idx].to_string(), Some(args[idx + 1..].to_string()))
    } else {
        (app.provider.clone(), Some(args.to_string()))
    };

    let full_id = format!("{}/{}", new_provider, new_model.as_deref().unwrap_or("default"));

    app.provider = new_provider;
    app.model = new_model;

    // Auto-save to user's model list if not already there
    if !app.model_picker_list.contains(&full_id) {
        app.model_picker_list.push(full_id);
        save_model_list(&app.model_picker_list);
    }

    app.add_system_message(format!(
        "Switched to {}/{}",
        app.provider,
        app.model.as_deref().unwrap_or("default")
    ));
}

pub fn save_model_list(models: &[String]) {
    let mut config = crate::config::TuiConfig::load();
    config.saved_models = models.to_vec();
    if let Err(e) = config.save() {
        eprintln!("Warning: {}", e);
    }
}

pub static CMD_MODEL: Command = Command {
    name: "/model",
    aliases: &["/models"],
    description: "Select, switch, or manage models",
    category: CommandCategory::Agent,
};
