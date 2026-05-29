use sediman_tui_core::command::{Command, CommandCategory};
use sediman_tui_core::event::AppEvent;

use crate::app::{App, AppModal, ModalLine};

/// `/skills` — list all skills
/// `/skills <name>` — show skill details
/// Merged from /skill + /skills (they were redundant).
pub async fn handle_skills(app: &mut App, args: &str) {
    let args = args.trim();

    // If a name is given, show that skill's details
    if !args.is_empty() && args != "list" {
        handle_skill_detail(app, args).await;
        return;
    }

    // No args or "list" — show all skills
    match app.bridge.list_skills().await {
        Ok(skills) => {
            if skills.is_empty() {
                app.active_modal = Some(AppModal::Info {
                    title: "Skills".into(),
                    lines: vec![
                        ModalLine::blank(),
                        ModalLine::muted("  No skills saved yet."),
                        ModalLine::muted("  Use /record <name> to start recording."),
                    ],
                    scroll: 0,
                });
                return;
            }
            let mut lines = vec![
                ModalLine::heading(format!("  Skills ({})", skills.len())),
                ModalLine::blank(),
            ];
            for s in &skills {
                let cat = s.category.as_deref().unwrap_or("general");
                lines.push(ModalLine::primary(format!("  {} v{}", s.name, s.version)));
                lines.push(ModalLine::muted(format!("    {} [{}]", s.description, cat)));
            }
            lines.push(ModalLine::blank());
            lines.push(ModalLine::muted("  /skills <name> for details"));
            app.active_modal = Some(AppModal::Info {
                title: "Skills".into(),
                lines,
                scroll: 0,
            });
        }
        Err(e) => {
            app.active_modal = Some(AppModal::Info {
                title: "Skills".into(),
                lines: vec![
                    ModalLine::blank(),
                    ModalLine::error(format!("  Failed to load skills: {}", e)),
                ],
                scroll: 0,
            });
        }
    }
}

async fn handle_skill_detail(app: &mut App, name: &str) {
    match app.bridge.get_skill(name).await {
        Ok(skill) => {
            let mut lines = vec![
                ModalLine::heading(format!("  {} v{}", skill.name, skill.version)),
                ModalLine::muted(format!("    {}", skill.description)),
            ];
            if let Some(ref cat) = skill.category {
                lines.push(ModalLine::muted(format!("    Category: {}", cat)));
            }
            lines.push(ModalLine::blank());
            lines.push(ModalLine::accent(format!("  Steps ({})", skill.steps.len())));
            for (i, step) in skill.steps.iter().enumerate() {
                let url = step.url.as_deref().unwrap_or("");
                lines.push(ModalLine::normal(format!("    {}. {} {}", i + 1, step.description, url)));
            }
            if !skill.when_to_use.is_empty() {
                lines.push(ModalLine::blank());
                lines.push(ModalLine::accent("  When to use"));
                for w in &skill.when_to_use {
                    lines.push(ModalLine::normal(format!("    - {}", w)));
                }
            }
            if !skill.pitfalls.is_empty() {
                lines.push(ModalLine::blank());
                lines.push(ModalLine::error("  Pitfalls"));
                for p in &skill.pitfalls {
                    lines.push(ModalLine::normal(format!("    - {}", p)));
                }
            }
            app.active_modal = Some(AppModal::Info {
                title: name.into(),
                lines,
                scroll: 0,
            });
        }
        Err(e) => {
            app.active_modal = Some(AppModal::Info {
                title: name.into(),
                lines: vec![
                    ModalLine::blank(),
                    ModalLine::error(format!("  Skill not found: {}", e)),
                ],
                scroll: 0,
            });
        }
    }
}

pub async fn handle_run_skill(app: &mut App, args: &str) {
    if args.is_empty() {
        app.add_system_message("Usage: /run-skill <name>".into());
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

    app.add_system_message(format!("Executing skill: {}", args));
    app.agent_running = true;
    app.agent_start = std::time::Instant::now();
    app.interrupt.clear();
    app.start_agent_message(&format!("skill: {}", args));

    let skill_name = args.to_string();
    let socket_path = app.bridge_url().to_string();
    tokio::spawn(async move {
        let bridge = sediman_tui_bridge::ApiClient::new(&socket_path);
        let result = bridge.execute_skill(skill_name.as_str()).await;
        match result {
            Ok(agent_result) => {
                let _ = event_tx.send(AppEvent::AgentResult(
                    agent_result.success,
                    agent_result.result.clone(),
                    agent_result.elapsed_secs,
                ));
            }
            Err(e) => {
                let _ = event_tx.send(AppEvent::AgentError(format!("Skill failed: {}", e)));
            }
        }
        let _ = event_tx.send(AppEvent::AgentDone);
    });
}

pub static CMD_SKILLS: Command = Command {
    name: "/skills",
    aliases: &["/skill"],
    description: "List skills or show details: /skills [name]",
    category: CommandCategory::Skills,
};

pub static CMD_RUN_SKILL: Command = Command {
    name: "/run-skill",
    aliases: &[],
    description: "Execute a saved skill: /run-skill <name>",
    category: CommandCategory::Skills,
};
