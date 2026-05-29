use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_skills(app: &mut App, _args: &str) {
    match app.bridge.list_skills().await {
        Ok(skills) => {
            if skills.is_empty() {
                app.step_log.push("  No skills saved yet.".into());
                return;
            }
            app.step_log.push(format!(" Skills ({})", skills.len()));
            for s in &skills {
                let cat = s.category.as_deref().unwrap_or("general");
                app.step_log.push(format!(
                    "  {} v{} — {} [{}]",
                    s.name, s.version, s.description, cat
                ));
            }
        }
        Err(e) => app.step_log.push(format!("✗ Failed to list skills: {}", e)),
    }
}

pub async fn handle_skill(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /skill <name>".into());
        return;
    }
    match app.bridge.get_skill(args).await {
        Ok(skill) => {
            app.step_log.push(format!(" {} v{}", skill.name, skill.version));
            app.step_log.push(format!("  {}", skill.description));
            if let Some(ref cat) = skill.category {
                app.step_log.push(format!("  Category: {}", cat));
            }
            app.step_log.push(format!("  Steps: {}", skill.steps.len()));
            for (i, step) in skill.steps.iter().enumerate() {
                let url = step.url.as_deref().unwrap_or("");
                app.step_log.push(format!("   {}. {} {}", i + 1, step.description, url));
            }
            if !skill.when_to_use.is_empty() {
                app.step_log.push("  When to use:".into());
                for w in &skill.when_to_use {
                    app.step_log.push(format!("    • {}", w));
                }
            }
            if !skill.pitfalls.is_empty() {
                app.step_log.push("  Pitfalls:".into());
                for p in &skill.pitfalls {
                    app.step_log.push(format!("    • {}", p));
                }
            }
        }
        Err(e) => app.step_log.push(format!("✗ Skill not found: {}", e)),
    }
}

pub async fn handle_run_skill(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /run-skill <name>".into());
        return;
    }
    app.step_log.push(format!("Executing skill: {}", args));
    app.agent_running = true;
    app.agent_start = std::time::Instant::now();

    match app.bridge.execute_skill(args).await {
        Ok(result) => {
            app.agent_running = false;
            app.last_result = Some(result.clone());
            let status = if result.success { "✓" } else { "✗" };
            app.step_log
                .push(format!("{} Skill done ({}s)", status, result.elapsed_secs));
        }
        Err(e) => {
            app.agent_running = false;
            app.step_log.push(format!("✗ Skill failed: {}", e));
        }
    }
}

pub static CMD_SKILLS: Command = Command {
    name: "/skills",
    aliases: &["/skill list"],
    description: "List all saved skills",
    category: CommandCategory::Skills,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_SKILL: Command = Command {
    name: "/skill",
    aliases: &[],
    description: "Show skill details: /skill <name>",
    category: CommandCategory::Skills,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_RUN_SKILL: Command = Command {
    name: "/run-skill",
    aliases: &[],
    description: "Execute a saved skill: /run-skill <name>",
    category: CommandCategory::Skills,
    handler: |_, _| Box::new(std::future::ready(())),
};
