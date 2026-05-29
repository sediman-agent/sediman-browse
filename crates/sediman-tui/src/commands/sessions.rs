use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_sessions(app: &mut App, _args: &str) {
    match app.bridge.get_sessions().await {
        Ok(sessions) => {
            if sessions.is_empty() {
                app.step_log.push("  No sessions yet.".into());
                return;
            }
            app.step_log.push(format!(" Recent Sessions ({})", sessions.len()));
            for s in &sessions {
                let task = if s.task.len() > 50 {
                    format!("{}...", &s.task[..47])
                } else {
                    s.task.clone()
                };
                app.step_log.push(format!(
                    "  [{}] {} — {}",
                    s.id,
                    task,
                    s.created_at
                ));
            }
        }
        Err(e) => app.step_log.push(format!("✗ Failed: {}", e)),
    }
}

pub async fn handle_resume(app: &mut App, _args: &str) {
    match app.bridge.get_sessions().await {
        Ok(sessions) => {
            if sessions.is_empty() {
                app.step_log.push("  No sessions to resume.".into());
                return;
            }
            app.step_log.push(" Recent sessions — use /sessions for details:".into());
            for (i, s) in sessions.iter().take(10).enumerate() {
                let task = if s.task.len() > 55 {
                    format!("{}...", &s.task[..52])
                } else {
                    s.task.clone()
                };
                app.step_log.push(format!("  {}. [{}] {}", i + 1, s.id, task));
            }
        }
        Err(e) => app.step_log.push(format!("✗ Failed: {}", e)),
    }
}

pub static CMD_SESSIONS: Command = Command {
    name: "/sessions",
    aliases: &[],
    description: "Show recent sessions",
    category: CommandCategory::Sessions,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_RESUME: Command = Command {
    name: "/resume",
    aliases: &[],
    description: "Show sessions available for resuming",
    category: CommandCategory::Sessions,
    handler: |_, _| Box::new(std::future::ready(())),
};
