#![allow(dead_code)]
use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal};

pub async fn handle_schedule(app: &mut App, _args: &str) {
    match app.bridge.list_schedules().await {
        Ok(jobs) => {
            app.schedule_jobs = jobs;
            app.schedule_selected = 0;
            app.schedule_scroll = 0;
            app.schedule_input.clear();
            app.active_modal = Some(AppModal::ScheduleBrowser);
        }
        Err(e) => {
            app.add_error_message(format!("Failed to load schedules: {}", e));
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
    description: "Manage scheduled jobs interactively",
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
