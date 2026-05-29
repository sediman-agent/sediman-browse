use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_usage(app: &mut App, _args: &str) {
    let conv_chars: usize = app.step_log.iter().map(|s| s.len()).sum();
    let est_tokens = conv_chars / 4;
    app.step_log.push(" Session Usage".into());
    app.step_log.push(format!("  Tasks run:  {}", app.task_count));
    app.step_log.push(format!("  Est. tokens: ~{}", est_tokens));
    app.step_log.push(format!("  Step log entries: {}", app.step_log.len()));
    app.step_log.push(format!(
        "  Model: {}/{}",
        app.provider,
        app.model.as_deref().unwrap_or("default")
    ));
    app.step_log.push(format!("  Agent running: {}", app.agent_running));
}

pub async fn handle_doctor(app: &mut App, _args: &str) {
    app.step_log.push(" Sediman Diagnostics".into());
    match app.bridge.status().await {
        Ok(status) => {
            app.step_log.push(format!("  API server: ✓ (uptime: {}s)", status.uptime_secs));
            app.step_log.push(format!("  Browser: {}", if status.browser_open { "✓ open" } else { "✗ closed" }));
        }
        Err(_) => {
            app.step_log.push("  API server: ✗ not reachable".into());
        }
    }
    app.step_log.push("  Config dir: ~/.sediman/".into());
    app.step_log.push(format!("  Mode: {}", app.permission.current_label()));
}

pub async fn handle_export(app: &mut App, _args: &str) {
    let lines: Vec<String> = app.step_log.iter().map(|s| format!("> {}", s)).collect();
    let content = lines.join("\n");
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs();
    // In a real impl, write to ~/.sediman/export_{timestamp}.md
    app.step_log.push(format!("✓ Export ready ({} chars)", content.len()));
    app.step_log.push(format!("  Would write: export_{}.md", timestamp));
}

pub async fn handle_btw(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /btw <question>".into());
        return;
    }
    app.step_log.push(format!("Side question: {}", args));
    app.step_log.push("  (ephemeral — does not affect conversation context)".into());
}

pub async fn handle_color(app: &mut App, _args: &str) {
    let colors = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"];
    let current = app.session_color.as_deref().unwrap_or("default");
    app.step_log.push(format!(" Session color: {}", current));
    app.step_log.push(format!(" Usage: /color {}", colors.join("|")));
    app.step_log.push("     or: /color random".into());
}

pub async fn handle_rename(app: &mut App, args: &str) {
    let args = args.trim();
    if args.is_empty() {
        let current = app.session_name.as_deref().unwrap_or("(unnamed)");
        app.step_log.push(format!(" Session name: {}", current));
        app.step_log.push(" Usage: /rename <name>".into());
        return;
    }
    let name: String = args.chars().take(30).collect();
    app.session_name = Some(name.clone());
    app.step_log.push(format!("✓ Session renamed to: {}", name));
}

pub static CMD_USAGE: Command = Command {
    name: "/usage",
    aliases: &[],
    description: "Show session usage stats",
    category: CommandCategory::Utilities,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_DOCTOR: Command = Command {
    name: "/doctor",
    aliases: &[],
    description: "Diagnose installation and settings",
    category: CommandCategory::Utilities,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_EXPORT: Command = Command {
    name: "/export",
    aliases: &[],
    description: "Export conversation to Markdown file",
    category: CommandCategory::Utilities,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_BTW: Command = Command {
    name: "/btw",
    aliases: &[],
    description: "Ephemeral side question: /btw <question>",
    category: CommandCategory::Utilities,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_COLOR: Command = Command {
    name: "/color",
    aliases: &[],
    description: "Set prompt bar color",
    category: CommandCategory::Terminal,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_RENAME: Command = Command {
    name: "/rename",
    aliases: &[],
    description: "Name this session: /rename <name>",
    category: CommandCategory::Terminal,
    handler: |_, _| Box::new(std::future::ready(())),
};
