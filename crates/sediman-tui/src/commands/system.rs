use crate::app::{App, AppModal, ModalLine};

pub async fn handle_help(app: &mut App, _args: &str) {
    app.active_modal = Some(AppModal::Help);
}

pub async fn handle_clear(app: &mut App, _args: &str) {
    app.messages.clear();
    app.step_log.clear();
    app.add_system_message("Conversation cleared.".into());
}

pub async fn handle_reset(app: &mut App, _args: &str) {
    app.messages.clear();
    app.step_log.clear();
    app.task_count = 0;
    app.last_result = None;
    app.editor = sediman_tui_core::input::TextEditor::new();
    app.show_banner = true;
    app.scroll_offset = 0;
    app.add_system_message("Full reset done.".into());
}

pub async fn handle_compress(app: &mut App, _args: &str) {
    app.add_system_message("Compressing conversation...".into());
    app.step_log.drain(..app.step_log.len().saturating_sub(50));
    let keep_count = 20;
    if app.messages.len() > keep_count {
        let drain_count = app.messages.len() - keep_count;
        app.messages.drain(..drain_count);
        app.messages.insert(0, crate::app::ChatMessage::System { text: format!("(compressed {} older messages)", drain_count) });
    }
    app.add_system_message("Conversation compressed.".into());
}

pub async fn handle_exit(app: &mut App, _args: &str) {
    app.running = false;
}

pub async fn handle_status(app: &mut App, _args: &str) {
    let mut lines = Vec::new();

    match app.bridge.status().await {
        Ok(status) => {
            let uptime = if status.uptime_secs >= 60 {
                format!("{}m {}s", status.uptime_secs / 60, status.uptime_secs % 60)
            } else {
                format!("{}s", status.uptime_secs)
            };
            lines.push(ModalLine::heading("Server"));
            lines.push(ModalLine::normal(format!("  Uptime           {}", uptime)));
            lines.push(ModalLine::normal(format!("  Browser          {}", if status.browser_open { "open" } else { "closed" })));
            lines.push(ModalLine::normal(format!("  Tasks completed   {}", status.tasks_completed)));
            lines.push(ModalLine::blank());
        }
        Err(e) => {
            lines.push(ModalLine::error(format!("  Server unreachable: {}", e)));
            lines.push(ModalLine::blank());
        }
    }

    lines.push(ModalLine::heading("Session"));
    lines.push(ModalLine::normal(format!("  Model      {}/{}", app.provider, app.model.as_deref().unwrap_or("-"))));
    lines.push(ModalLine::normal(format!("  Mode       {}", app.permission.current_label())));
    lines.push(ModalLine::normal(format!("  Tasks      {}", app.task_count)));
    lines.push(ModalLine::normal(format!("  Browser    {}", if app.headless { "headless" } else { "headed + vision" })));
    lines.push(ModalLine::normal(format!("  Theme      {}", app.theme_name)));

    app.active_modal = Some(AppModal::Info {
        title: "Status".into(),
        lines,
        scroll: 0,
    });
}

use sediman_tui_core::command::{Command, CommandCategory};

pub static CMD_HELP: Command = Command {
    name: "/help",
    aliases: &["/h", "/?"],
    description: "Show categorized command list",
    category: CommandCategory::General,
};

pub static CMD_CLEAR: Command = Command {
    name: "/clear",
    aliases: &[],
    description: "Clear conversation",
    category: CommandCategory::General,
};

pub static CMD_RESET: Command = Command {
    name: "/reset",
    aliases: &[],
    description: "Full reset: agent, LLM, task count",
    category: CommandCategory::General,
};

pub static CMD_COMPRESS: Command = Command {
    name: "/compress",
    aliases: &[],
    description: "Compress conversation history",
    category: CommandCategory::Agent,
};

pub static CMD_EXIT: Command = Command {
    name: "/exit",
    aliases: &["/quit", "/q"],
    description: "Exit Sediman",
    category: CommandCategory::General,
};

pub static CMD_STATUS: Command = Command {
    name: "/status",
    aliases: &[],
    description: "Show agent, browser, model, task status",
    category: CommandCategory::General,
};
