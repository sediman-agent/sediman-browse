use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal, ModalLine};

pub(crate) fn truncate_str(s: &str, max_chars: usize) -> String {
    s.chars().take(max_chars).collect()
}

pub async fn handle_sessions(app: &mut App, _args: &str) {
    match app.bridge.get_sessions().await {
        Ok(sessions) => {
            if sessions.is_empty() {
                app.active_modal = Some(AppModal::Info {
                    title: "Sessions".into(),
                    lines: vec![
                        ModalLine::blank(),
                        ModalLine::muted("  No sessions yet."),
                    ],
                    scroll: 0,
                });
                return;
            }
            let mut lines = vec![
                ModalLine::heading(format!("  Recent Sessions ({})", sessions.len())),
                ModalLine::blank(),
            ];
            for s in &sessions {
                let task = truncate_str(&s.task, 40);
                let suffix = if s.task.len() > 40 { "..." } else { "" };
                lines.push(ModalLine::primary(format!("  [{}]", s.id)));
                lines.push(ModalLine::normal(format!("    {}{} \u{2014} {}", task, suffix, s.created_at)));
            }
            app.active_modal = Some(AppModal::Info {
                title: "Sessions".into(),
                lines,
                scroll: 0,
            });
        }
        Err(e) => {
            app.active_modal = Some(AppModal::Info {
                title: "Sessions".into(),
                lines: vec![
                    ModalLine::blank(),
                    ModalLine::error(format!("  Failed to load sessions: {}", e)),
                ],
                scroll: 0,
            });
        }
    }
}

pub async fn handle_resume(app: &mut App, _args: &str) {
    match app.bridge.get_sessions().await {
        Ok(sessions) => {
            if sessions.is_empty() {
                app.active_modal = Some(AppModal::Info {
                    title: "Resume".into(),
                    lines: vec![
                        ModalLine::blank(),
                        ModalLine::muted("  No sessions to resume."),
                    ],
                    scroll: 0,
                });
                return;
            }
            let mut lines = vec![
                ModalLine::heading("  Resume Session"),
                ModalLine::muted("  Select a session to resume:"),
                ModalLine::blank(),
            ];
            for (i, s) in sessions.iter().take(10).enumerate() {
                let task = truncate_str(&s.task, 45);
                let suffix = if s.task.len() > 45 { "..." } else { "" };
                lines.push(ModalLine::normal(format!("  {}. [{}] {}{}", i + 1, s.id, task, suffix)));
            }
            app.active_modal = Some(AppModal::Info {
                title: "Resume".into(),
                lines,
                scroll: 0,
            });
        }
        Err(e) => {
            app.active_modal = Some(AppModal::Info {
                title: "Resume".into(),
                lines: vec![
                    ModalLine::blank(),
                    ModalLine::error(format!("  Failed to load sessions: {}", e)),
                ],
                scroll: 0,
            });
        }
    }
}

pub static CMD_SESSIONS: Command = Command {
    name: "/sessions",
    aliases: &[],
    description: "Show recent sessions",
    category: CommandCategory::Sessions,
};

pub static CMD_RESUME: Command = Command {
    name: "/resume",
    aliases: &[],
    description: "Show sessions available for resuming",
    category: CommandCategory::Sessions,
};
