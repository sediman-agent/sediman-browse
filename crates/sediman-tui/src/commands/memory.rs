use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal, ModalLine};

/// `/memory` — opens interactive memory editor (view, add, delete entries).
pub async fn handle_memory(app: &mut App, _args: &str) {
    match app.bridge.get_memory().await {
        Ok(mem) => {
            // Parse entries from the joined strings
            let mut entries = Vec::new();

            if !mem.memory.is_empty() {
                for line in mem.memory.lines() {
                    let line = line.trim().to_string();
                    if !line.is_empty() {
                        entries.push(("memory".to_string(), line));
                    }
                }
            }
            if !mem.user.is_empty() {
                for line in mem.user.lines() {
                    let line = line.trim().to_string();
                    if !line.is_empty() {
                        entries.push(("user".to_string(), line));
                    }
                }
            }

            app.memory_entries = entries;
            app.memory_editor_input.clear();
            app.memory_editor_index = 0;
            app.active_modal = Some(AppModal::MemoryEditor);
        }
        Err(e) => {
            // Fallback to simple info modal if backend unreachable
            app.active_modal = Some(AppModal::Info {
                title: "Memory".into(),
                lines: vec![
                    ModalLine::blank(),
                    ModalLine::error(format!("  Failed to load memory: {}", e)),
                ],
                scroll: 0,
            });
        }
    }
}

/// `/remember <text>` — quick-add to memory.
pub async fn handle_remember(app: &mut App, args: &str) {
    if args.is_empty() {
        app.add_system_message("Usage: /remember <text>".into());
        return;
    }
    match app.bridge.remember(args).await {
        Ok(_) => {
            let preview: String = args.chars().take(60).collect();
            app.add_system_message(format!("Remembered: {}", preview))
        }
        Err(e) => app.add_error_message(format!("Failed to save: {}", e)),
    }
}

pub static CMD_MEMORY: Command = Command {
    name: "/memory",
    aliases: &[],
    description: "View and edit memory entries",
    category: CommandCategory::Sessions,
};

pub static CMD_REMEMBER: Command = Command {
    name: "/remember",
    aliases: &[],
    description: "Save to memory: /remember <text>",
    category: CommandCategory::Sessions,
};
