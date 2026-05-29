use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_hub_browse(app: &mut App, args: &str) {
    let category = if args.is_empty() { None } else { Some(args) };
    match app.bridge.hub_browse(category).await {
        Ok(skills) => {
            if skills.is_empty() {
                app.step_log.push("  No skills found in hub.".into());
                return;
            }
            app.step_log.push(format!(" Hub Skills ({})", skills.len()));
            for s in &skills {
                app.step_log.push(format!(
                    "  {} v{} by {} — {} [{}]",
                    s.name, s.version, s.author, s.description, s.trust
                ));
            }
        }
        Err(e) => app.step_log.push(format!("✗ Hub browse failed: {}", e)),
    }
}

pub async fn handle_hub_search(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /hub search <query>".into());
        return;
    }
    match app.bridge.hub_search(args).await {
        Ok(skills) => {
            if skills.is_empty() {
                app.step_log.push("  No matches found.".into());
                return;
            }
            app.step_log.push(format!(" Search results for '{}'", args));
            for s in &skills {
                app.step_log.push(format!("  {} — {}", s.name, s.description));
            }
        }
        Err(e) => app.step_log.push(format!("✗ Search failed: {}", e)),
    }
}

pub async fn handle_hub_install(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /hub install <name> [--force]".into());
        return;
    }
    let force = args.contains("--force");
    let name = args.trim().trim_end_matches(" --force");
    app.step_log.push(format!("Installing {} from hub...", name));
    match app.bridge.hub_install(name, force).await {
        Ok(_) => app.step_log.push(format!("✓ Installed {}", name)),
        Err(e) => app.step_log.push(format!("✗ Install failed: {}", e)),
    }
}

pub async fn handle_hub_info(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /hub info <name>".into());
        return;
    }
    match app.bridge.hub_info(args).await {
        Ok(skill) => {
            app.step_log.push(format!(" {} v{} by {}", skill.name, skill.version, skill.author));
            app.step_log.push(format!("  {}", skill.description));
            app.step_log.push(format!("  Category: {}", skill.category));
            app.step_log.push(format!("  Trust: {}", skill.trust));
        }
        Err(e) => app.step_log.push(format!("✗ Info failed: {}", e)),
    }
}

pub async fn handle_hub_publish(app: &mut App, args: &str) {
    if args.is_empty() {
        app.step_log.push("Usage: /hub publish <name>".into());
        return;
    }
    app.step_log.push(format!("Publishing {}...", args));
    app.step_log.push("⚠ Publish requires a GitHub token. Use the Python CLI for now.".into());
}

pub static CMD_HUB_BROWSE: Command = Command {
    name: "/hub browse",
    aliases: &[],
    description: "Browse Skills Hub: /hub browse [--category <cat>]",
    category: CommandCategory::Hub,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_HUB_SEARCH: Command = Command {
    name: "/hub search",
    aliases: &[],
    description: "Search Skills Hub: /hub search <query>",
    category: CommandCategory::Hub,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_HUB_INSTALL: Command = Command {
    name: "/hub install",
    aliases: &[],
    description: "Install a hub skill: /hub install <name> [--force]",
    category: CommandCategory::Hub,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_HUB_INFO: Command = Command {
    name: "/hub info",
    aliases: &[],
    description: "Show hub skill details: /hub info <name>",
    category: CommandCategory::Hub,
    handler: |_, _| Box::new(std::future::ready(())),
};

pub static CMD_HUB_PUBLISH: Command = Command {
    name: "/hub publish",
    aliases: &[],
    description: "Publish a local skill: /hub publish <name>",
    category: CommandCategory::Hub,
    handler: |_, _| Box::new(std::future::ready(())),
};
