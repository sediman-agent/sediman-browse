use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_schedule(app: &mut App, _args: &str) {
    match app.bridge.list_schedules().await {
        Ok(jobs) => {
            if jobs.is_empty() {
                app.step_log.push("  No scheduled jobs.".into());
                return;
            }
            app.step_log.push(format!(" Scheduled Jobs ({})", jobs.len()));
            for j in &jobs {
                let status = if j.enabled { "active" } else { "paused" };
                let task = &j.task;
                app.step_log.push(format!(
                    "  [{}] {} — cron: {} ({})",
                    &j.id[..j.id.len().min(8)], task, j.cron_expr, status
                ));
                if let Some(ref next) = j.next_run {
                    app.step_log.push(format!("    next: {}", next));
                }
            }
        }
        Err(e) => app.step_log.push(format!("✗ Failed to list schedules: {}", e)),
    }
}

pub async fn handle_schedule_add(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /schedule-add <cron> <task>".into());
        return;
    }
    let parts: Vec<&str> = args.splitn(2, ' ').collect();
    if parts.len() < 2 {
        app.step_log.push("Usage: /schedule-add <cron> <task>".into());
        return;
    }
    let cron_expr = parts[0];
    let task = parts[1];
    match app.bridge.add_schedule(cron_expr, task).await {
        Ok(id) => app.step_log.push(format!("✓ Scheduled job created: {}", id)),
        Err(e) => app.step_log.push(format!("✗ Failed: {}", e)),
    }
}

pub async fn handle_schedule_remove(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /schedule-remove <id>".into());
        return;
    }
    match app.bridge.remove_schedule(args).await {
        Ok(_) => app.step_log.push(format!("✓ Removed job: {}", args)),
        Err(e) => app.step_log.push(format!("✗ Failed: {}", e)),
    }
}

pub static CMD_SCHEDULE: Command = Command {
    name: "/schedule",
    aliases: &[],
    description: "List scheduled cron jobs",
    category: CommandCategory::Schedule,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_SCHEDULE_ADD: Command = Command {
    name: "/schedule-add",
    aliases: &[],
    description: "Add a scheduled task: /schedule-add <cron> <task>",
    category: CommandCategory::Schedule,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_SCHEDULE_REMOVE: Command = Command {
    name: "/schedule-remove",
    aliases: &[],
    description: "Remove a scheduled job: /schedule-remove <id>",
    category: CommandCategory::Schedule,
    handler: |_, _| Box::new(std::future::ready(())),
};
