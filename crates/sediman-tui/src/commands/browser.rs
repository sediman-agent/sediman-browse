use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_browser(app: &mut App, args: &str) {
    let args = args.trim().to_lowercase();
    if args.is_empty() {
        let mode = if app.headless { "headless" } else { "headed" };
        app.add_system_message(format!("Browser mode: {}", mode));
        app.add_system_message("Usage: /browser headless|headed".into());
        return;
    }
    match args.as_str() {
        "headless" => {
            app.headless = true;
            app.add_system_message("Switched to headless mode (next task)".into());
        }
        "headed" => {
            app.headless = false;
            app.add_system_message("Switched to headed mode (next task)".into());
        }
        _ => {
            app.add_system_message("Usage: /browser headless|headed".into());
        }
    }
}

pub async fn handle_screenshot(app: &mut App, _args: &str) {
    match app.bridge.get_screenshot().await {
        Ok(bytes) => {
            let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
            let path = format!("{}/.sediman/last_screenshot.png", home);
            if let Err(e) = std::fs::create_dir_all(format!("{}/.sediman", home)) {
                app.add_error_message(format!("Failed to create dir: {}", e));
                return;
            }
            match std::fs::write(&path, &bytes) {
                Ok(_) => app.add_system_message(format!("Screenshot saved: {} ({} bytes)", path, bytes.len())),
                Err(e) => app.add_error_message(format!("Failed to save: {}", e)),
            }
        }
        Err(e) => app.add_error_message(format!("Screenshot failed: {}", e)),
    }
}

pub static CMD_BROWSER: Command = Command {
    name: "/browser",
    aliases: &[],
    description: "Show or switch browser mode: /browser [headless|headed]",
    category: CommandCategory::Browser,
};

pub static CMD_SCREENSHOT: Command = Command {
    name: "/screenshot",
    aliases: &[],
    description: "Take a browser screenshot and save it",
    category: CommandCategory::Browser,
};
