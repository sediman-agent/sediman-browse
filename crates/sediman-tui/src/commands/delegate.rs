use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;
use crate::update::handle_task;

pub async fn handle_delegate(app: &mut App, args: &str) {
    if args.is_empty() {
        app.add_system_message("Usage: /delegate <task>".into());
        return;
    }
    if app.agent_running {
        app.add_system_message("Agent is busy. Wait for it to finish.".into());
        return;
    }
    let Some(event_tx) = app.event_tx.clone() else {
        app.add_error_message("No event channel available.".into());
        return;
    };
    app.add_system_message(format!("Delegating: {}", args));
    handle_task(app, args, &event_tx).await;
}

pub async fn handle_parallel(app: &mut App, args: &str) {
    if args.is_empty() {
        app.add_system_message("Usage: /parallel <task1> | <task2> | ...".into());
        return;
    }
    if app.agent_running {
        app.add_system_message("Agent is busy. Wait for it to finish.".into());
        return;
    }
    let tasks: Vec<&str> = args.split('|').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    if tasks.is_empty() {
        app.add_system_message("No tasks specified.".into());
        return;
    }
    if tasks.len() > 5 {
        app.add_system_message("Max 5 parallel tasks.".into());
        return;
    }
    let Some(event_tx) = app.event_tx.clone() else {
        app.add_error_message("No event channel available.".into());
        return;
    };
    app.add_system_message(format!("Running {} tasks in parallel...", tasks.len()));
    for (i, task) in tasks.iter().enumerate() {
        app.add_system_message(format!("  {}. {}", i + 1, task));
    }
    let combined = tasks.join("; then also: ");
    handle_task(app, &combined, &event_tx).await;
}

pub static CMD_DELEGATE: Command = Command {
    name: "/delegate",
    aliases: &[],
    description: "Run task as isolated subagent: /delegate <task>",
    category: CommandCategory::Tasks,
};

pub static CMD_PARALLEL: Command = Command {
    name: "/parallel",
    aliases: &[],
    description: "Run tasks in parallel: /parallel <t1> | <t2> | ...",
    category: CommandCategory::Tasks,
};
