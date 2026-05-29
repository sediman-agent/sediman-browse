use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal, ModalLine};
use super::sessions::truncate_str;

pub async fn handle_schedule(app: &mut App, _args: &str) {
    match app.bridge.list_schedules().await {
        Ok(jobs) => {
            if jobs.is_empty() {
                app.active_modal = Some(AppModal::Info {
                    title: "Scheduled Jobs".into(),
                    lines: vec![
                        ModalLine::blank(),
                        ModalLine::muted("  No scheduled jobs."),
                        ModalLine::muted("  Use /schedule-add <cron> <task> to create one."),
                    ],
                    scroll: 0,
                });
                return;
            }
            let mut lines = vec![
                ModalLine::heading(format!("  Scheduled Jobs ({})", jobs.len())),
                ModalLine::blank(),
            ];
            for j in &jobs {
                let status = if j.enabled { "active" } else { "paused" };
                lines.push(ModalLine::primary(format!("  [{}]", truncate_str(&j.id, 8))));
                lines.push(ModalLine::normal(format!("    {} \u{2014} cron: {} ({})", j.task, j.cron_expr, status)));
                if let Some(ref next) = j.next_run {
                    lines.push(ModalLine::muted(format!("    next: {}", next)));
                }
            }
            app.active_modal = Some(AppModal::Info {
                title: "Scheduled Jobs".into(),
                lines,
                scroll: 0,
            });
        }
        Err(e) => {
            app.active_modal = Some(AppModal::Info {
                title: "Scheduled Jobs".into(),
                lines: vec![
                    ModalLine::blank(),
                    ModalLine::error(format!("  Failed to load schedules: {}", e)),
                ],
                scroll: 0,
            });
        }
    }
}

pub async fn handle_schedule_add(app: &mut App, args: &str) {
    if args.is_empty() {
        app.add_system_message("Usage: /schedule-add <cron> <task>".into());
        return;
    }
    let parts: Vec<&str> = args.splitn(2, ' ').collect();
    if parts.len() < 2 {
        app.add_system_message("Usage: /schedule-add <cron> <task>".into());
        return;
    }
    match app.bridge.add_schedule(parts[0], parts[1]).await {
        Ok(id) => app.add_system_message(format!("Scheduled job created: {}", id)),
        Err(e) => app.add_error_message(format!("Failed: {}", e)),
    }
}

pub async fn handle_schedule_remove(app: &mut App, args: &str) {
    if args.is_empty() {
        app.add_system_message("Usage: /schedule-remove <id>".into());
        return;
    }
    match app.bridge.remove_schedule(args).await {
        Ok(_) => app.add_system_message(format!("Removed job: {}", args)),
        Err(e) => app.add_error_message(format!("Failed: {}", e)),
    }
}

pub static CMD_SCHEDULE: Command = Command {
    name: "/schedule",
    aliases: &[],
    description: "List scheduled cron jobs",
    category: CommandCategory::Schedule,
};

pub static CMD_SCHEDULE_ADD: Command = Command {
    name: "/schedule-add",
    aliases: &[],
    description: "Add a scheduled task: /schedule-add <cron> <task>",
    category: CommandCategory::Schedule,
};

pub static CMD_SCHEDULE_REMOVE: Command = Command {
    name: "/schedule-remove",
    aliases: &[],
    description: "Remove a scheduled job: /schedule-remove <id>",
    category: CommandCategory::Schedule,
};
