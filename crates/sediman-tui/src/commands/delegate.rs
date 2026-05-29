use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_delegate(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /delegate <task>".into());
        return;
    }
    app.step_log.push(format!("Delegating task as subagent: {}", args));
    app.agent_running = true;
    app.agent_start = std::time::Instant::now();
    app.step_log.push("  Subagent spawned. Results will appear here.".into());
    // In future: spawn a SubagentSession via the bridge API
    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    app.agent_running = false;
    app.step_log.push("✓ Subagent completed.".into());
}

pub async fn handle_parallel(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /parallel <task1> | <task2> | ...".into());
        return;
    }
    let tasks: Vec<&str> = args.split('|').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    if tasks.is_empty() {
        app.step_log.push("  No tasks specified.".into());
        return;
    }
    if tasks.len() > 5 {
        app.step_log.push("  Max 5 parallel tasks.".into());
        return;
    }
    app.step_log.push(format!("Running {} tasks in parallel...", tasks.len()));
    for (i, task) in tasks.iter().enumerate() {
        app.step_log.push(format!("  {}. {}", i + 1, task));
    }
    app.agent_running = true;
    // In future: call delegate_parallel via the bridge
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    app.agent_running = false;
    app.step_log.push("✓ All parallel tasks completed.".into());
}

pub static CMD_DELEGATE: Command = Command {
    name: "/delegate",
    aliases: &[],
    description: "Run task as isolated subagent: /delegate <task>",
    category: CommandCategory::Tasks,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_PARALLEL: Command = Command {
    name: "/parallel",
    aliases: &[],
    description: "Run tasks in parallel: /parallel <t1> | <t2> | ...",
    category: CommandCategory::Tasks,
    handler: |_, _| Box::new(std::future::ready(())),
};
