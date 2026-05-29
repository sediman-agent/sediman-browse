use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_help(app: &mut App, _args: &str) {
    app.step_log.push(" Commands".into());
    app.step_log.push("".into());
    app.step_log.push("[General]".into());
    app.step_log.push("  /help       — Show this help".into());
    app.step_log.push("  /exit       — Exit Sediman".into());
    app.step_log.push("  /status     — Show status".into());
    app.step_log.push("  /clear      — Clear conversation".into());
    app.step_log.push("  /reset      — Full reset".into());
    app.step_log.push("".into());
    app.step_log.push("[Agent]".into());
    app.step_log.push("  /model      — Show/switch model".into());
    app.step_log.push("  /models     — List providers".into());
    app.step_log.push("  /compress   — Compress history".into());
    app.step_log.push("  /soul       — Show/set personality".into());
    app.step_log.push("  /plan       — Toggle plan mode".into());
    app.step_log.push("".into());
    app.step_log.push("[Skills]".into());
    app.step_log.push("  /skills     — List skills".into());
    app.step_log.push("  /skill      — Show skill detail".into());
    app.step_log.push("  /run-skill  — Execute a skill".into());
    app.step_log.push("  /record     — Start recording".into());
    app.step_log.push("  /stop       — Stop recording".into());
    app.step_log.push("".into());
    app.step_log.push("[Hub]".into());
    app.step_log.push("  /hub browse  — Browse Skills Hub".into());
    app.step_log.push("  /hub search  — Search hub".into());
    app.step_log.push("  /hub install — Install from hub".into());
    app.step_log.push("  /hub info    — Hub skill details".into());
    app.step_log.push("  /hub publish — Publish to hub".into());
    app.step_log.push("".into());
    app.step_log.push("[Browser]".into());
    app.step_log.push("  /browser    — Headless/headed toggle".into());
    app.step_log.push("  /screenshot — Take screenshot".into());
    app.step_log.push("".into());
    app.step_log.push("[Sessions & Memory]".into());
    app.step_log.push("  /sessions   — Recent sessions".into());
    app.step_log.push("  /resume     — Resume session".into());
    app.step_log.push("  /memory     — Show memory".into());
    app.step_log.push("  /remember   — Save to memory".into());
    app.step_log.push("".into());
    app.step_log.push("[Schedule]".into());
    app.step_log.push("  /schedule       — List cron jobs".into());
    app.step_log.push("  /schedule-add   — Add cron job".into());
    app.step_log.push("  /schedule-remove— Remove cron job".into());
    app.step_log.push("".into());
    app.step_log.push("[Other]".into());
    app.step_log.push("  /terminal   — Terminal access on/off".into());
    app.step_log.push("  /color      — Set prompt color".into());
    app.step_log.push("  /rename     — Name session".into());
    app.step_log.push("  /delegate   — Subagent task".into());
    app.step_log.push("  /parallel   — Parallel tasks".into());
    app.step_log.push("  /usage      — Usage stats".into());
    app.step_log.push("  /doctor     — Diagnostics".into());
    app.step_log.push("  /export     — Export conversation".into());
    app.step_log.push("  /btw        — Side question".into());
}

pub async fn handle_clear(app: &mut App, _args: &str) {
    app.step_log.clear();
    app.output_text.clear();
    app.step_log.push("✓ Conversation cleared.".into());
}

pub async fn handle_reset(app: &mut App, _args: &str) {
    app.step_log.clear();
    app.output_text.clear();
    app.task_count = 0;
    app.last_result = None;
    app.editor = sediman_tui_core::input::TextEditor::new();
    app.show_banner = true;
    app.step_log.push("✓ Full reset done.".into());
}

pub async fn handle_compress(app: &mut App, _args: &str) {
    app.step_log.push("Compressing conversation...".into());
    app.step_log.truncate(50);
    app.step_log.push("✓ Conversation compressed.".into());
}

pub async fn handle_exit(app: &mut App, _args: &str) {
    app.running = false;
    app.step_log.push("Exiting...".into());
}

pub async fn handle_status(app: &mut App, _args: &str) {
    match app.bridge.status().await {
        Ok(status) => {
            app.step_log.push(" Status".into());
            let uptime = if status.uptime_secs >= 60 {
                format!("{}m {}s", status.uptime_secs / 60, status.uptime_secs % 60)
            } else {
                format!("{}s", status.uptime_secs)
            };
            app.step_log.push(format!("  Server uptime: {}", uptime));
            app.step_log.push(format!("  Browser open: {}", status.browser_open));
            app.step_log.push(format!("  Tasks completed: {}", status.tasks_completed));
            app.step_log.push(format!("  Model: {}/{}", app.provider, app.model.as_deref().unwrap_or("-")));
            app.step_log.push(format!("  Tasks this session: {}", app.task_count));
            app.step_log.push(format!("  Mode: {}", app.permission.current_label()));
        }
        Err(e) => app.step_log.push(format!("✗ Status check failed: {}", e)),
    }
}

pub static CMD_HELP: Command = Command {
    name: "/help",
    aliases: &["/h", "/?"],
    description: "Show categorized command list",
    category: CommandCategory::General,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_CLEAR: Command = Command {
    name: "/clear",
    aliases: &[],
    description: "Clear conversation",
    category: CommandCategory::General,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_RESET: Command = Command {
    name: "/reset",
    aliases: &[],
    description: "Full reset: agent, LLM, task count",
    category: CommandCategory::General,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_COMPRESS: Command = Command {
    name: "/compress",
    aliases: &[],
    description: "Compress conversation history",
    category: CommandCategory::Agent,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_EXIT: Command = Command {
    name: "/exit",
    aliases: &["/quit", "/q"],
    description: "Exit Sediman",
    category: CommandCategory::General,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_STATUS: Command = Command {
    name: "/status",
    aliases: &[],
    description: "Show agent, browser, model, task status",
    category: CommandCategory::General,
    handler: |_, _| Box::new(std::future::ready(())),
};
