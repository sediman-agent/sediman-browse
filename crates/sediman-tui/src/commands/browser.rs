use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_browser(app: &mut App, args: &str) {
    let args = args.trim().to_lowercase();
    if args.is_empty() {
        let mode = if app.headless { "headless" } else { "headed" };
        app.step_log.push(format!(" Browser mode: {}", mode));
        app.step_log.push(" Usage: /browser headless|headed".into());
        return;
    }
    match args.as_str() {
        "headless" => {
            app.headless = true;
            app.step_log.push("✓ Switched to headless mode (next task)".into());
        }
        "headed" => {
            app.headless = false;
            app.step_log.push("✓ Switched to headed mode (next task)".into());
        }
        _ => {
            app.step_log.push("Usage: /browser headless|headed".into());
        }
    }
}

pub async fn handle_screenshot(app: &mut App, _args: &str) {
    match app.bridge.get_screenshot().await {
        Ok(bytes) => {
            app.step_log.push(format!("✓ Screenshot captured: {} bytes", bytes.len()));
            // In a real impl, save to ~/.sediman/last_screenshot.png
        }
        Err(e) => app.step_log.push(format!("✗ Screenshot failed: {}", e)),
    }
}

pub static CMD_BROWSER: Command = Command {
    name: "/browser",
    aliases: &[],
    description: "Show or switch browser mode: /browser [headless|headed]",
    category: CommandCategory::Browser,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_SCREENSHOT: Command = Command {
    name: "/screenshot",
    aliases: &[],
    description: "Take a browser screenshot and save it",
    category: CommandCategory::Browser,
    handler: |_, _| Box::new(std::future::ready(())),
};
