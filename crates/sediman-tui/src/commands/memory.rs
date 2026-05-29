use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_memory(app: &mut App, _args: &str) {
    match app.bridge.get_memory().await {
        Ok(mem) => {
            app.step_log.push(" Memory".into());
            if mem.memory.is_empty() {
                app.step_log.push("  (empty)".into());
            } else {
                app.step_log.push(format!("  {} ({} entries)", mem.memory, mem.memory_entries));
            }
            app.step_log.push(" User".into());
            if mem.user.is_empty() {
                app.step_log.push("  (empty)".into());
            } else {
                app.step_log.push(format!("  {} ({} entries)", mem.user, mem.user_entries));
            }
        }
        Err(e) => app.step_log.push(format!("✗ Failed to load memory: {}", e)),
    }
}

pub async fn handle_remember(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /remember <text>".into());
        return;
    }
    match app.bridge.remember(args).await {
        Ok(_) => app.step_log.push(format!("✓ Remembered: {}", &args[..args.len().min(60)])),
        Err(e) => app.step_log.push(format!("✗ Failed to save: {}", e)),
    }
}

pub static CMD_MEMORY: Command = Command {
    name: "/memory",
    aliases: &[],
    description: "Show stored persistent memory",
    category: CommandCategory::Sessions,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_REMEMBER: Command = Command {
    name: "/remember",
    aliases: &[],
    description: "Save to memory: /remember <text>",
    category: CommandCategory::Sessions,
    handler: |_, _| Box::new(std::future::ready(())),
};
