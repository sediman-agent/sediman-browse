#![allow(dead_code)]
use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal, ModalLine};

fn is_connection_error(e: &str) -> bool {
    e.contains("Connection failed") || e.contains("No such file") || e.contains("os error 2")
}

fn show_connection_error(app: &mut App, action: &str) {
    app.active_modal = Some(AppModal::Info {
        title: "Hub Unavailable".into(),
        lines: vec![
            ModalLine::blank(),
            ModalLine::error(format!("  Cannot {} — backend not reachable.", action)),
            ModalLine::blank(),
            ModalLine::muted("  Make sure the sediman backend is running."),
            ModalLine::muted("  Run: sediman serve"),
        ],
        scroll: 0,
    });
}

fn show_hub_error(app: &mut App, title: &str, e: &str) {
    if is_connection_error(e) {
        show_connection_error(app, title.to_lowercase().as_str());
        return;
    }
    app.active_modal = Some(AppModal::Info {
        title: title.into(),
        lines: vec![
            ModalLine::blank(),
            ModalLine::error(format!("  {}", e)),
        ],
        scroll: 0,
    });
}

pub async fn handle_hub_browse(app: &mut App, args: &str) {
    let category = if args.is_empty() { None } else { Some(args) };

    // Fetch installed skills so we can show [installed] badges
    let installed = app.bridge.list_skills().await.unwrap_or_default();
    app.skill_browser_installed = installed.iter().map(|s| s.name.clone()).collect();

    match app.bridge.hub_browse(category).await {
        Ok(skills) => {
            if skills.is_empty() {
                app.active_modal = Some(AppModal::Info {
                    title: "Hub \u{2014} Browse".into(),
                    lines: vec![
                        ModalLine::blank(),
                        ModalLine::muted("  No skills found in hub."),
                    ],
                    scroll: 0,
                });
                return;
            }
            app.skill_browser_skills = skills;
            app.skill_browser_selected = 0;
            app.skill_browser_filter.clear();
            app.skill_browser_scroll = 0;
            app.active_modal = Some(AppModal::SkillBrowser);
        }
        Err(e) => show_hub_error(app, "Hub Browse", &e.to_string()),
    }
}

pub async fn handle_hub_search(app: &mut App, args: &str) {
    if args.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} Search".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub search <query>"),
            ],
            scroll: 0,
        });
        return;
    }
    match app.bridge.hub_search(args).await {
        Ok(skills) => {
            if skills.is_empty() {
                app.active_modal = Some(AppModal::Info {
                    title: format!("Hub \u{2014} Search: {}", args),
                    lines: vec![
                        ModalLine::blank(),
                        ModalLine::muted("  No matches found."),
                    ],
                    scroll: 0,
                });
                return;
            }

            let installed = app.bridge.list_skills().await.unwrap_or_default();
            app.skill_browser_installed = installed.iter().map(|s| s.name.clone()).collect();
            app.skill_browser_skills = skills;
            app.skill_browser_filter = args.to_string();
            app.skill_browser_selected = 0;
            app.skill_browser_scroll = 0;
            app.active_modal = Some(AppModal::SkillBrowser);
        }
        Err(e) => show_hub_error(app, "Hub Search", &e.to_string()),
    }
}

pub async fn handle_hub_install(app: &mut App, args: &str) {
    if args.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} Install".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub install <name> [--force]"),
            ],
            scroll: 0,
        });
        return;
    }
    let parts: Vec<&str> = args.split_whitespace().collect();
    let mut force = false;
    let mut name_parts: Vec<&str> = Vec::new();
    for part in parts {
        if part == "--force" {
            force = true;
        } else {
            name_parts.push(part);
        }
    }
    let name = name_parts.join(" ");
    if name.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} Install".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub install <name> [--force]"),
            ],
            scroll: 0,
        });
        return;
    }
    app.add_system_message(format!("Installing {} from hub...", name));
    match app.bridge.hub_install(&name, force).await {
        Ok(_) => app.add_system_message(format!("Installed {}", name)),
        Err(e) => show_hub_error(app, "Hub Install", &e.to_string()),
    }
}

pub async fn handle_hub_info(app: &mut App, args: &str) {
    if args.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} Info".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub info <name>"),
            ],
            scroll: 0,
        });
        return;
    }
    match app.bridge.hub_info_detail(args).await {
        Ok(skill) => {
            let mut lines = vec![
                ModalLine::heading(format!("  {} v{}", skill.name, skill.version)),
                ModalLine::muted(format!("    by {}", skill.author)),
                ModalLine::blank(),
                ModalLine::normal(format!("    {}", skill.description)),
                ModalLine::blank(),
                ModalLine::normal(format!("    Category: {}", skill.category)),
                ModalLine::normal(format!("    Trust: {}", skill.trust)),
            ];
            if let Some(ref license) = skill.license {
                lines.push(ModalLine::normal(format!("    License: {}", license)));
            }
            if let Some(ref schedule) = skill.schedule {
                lines.push(ModalLine::normal(format!("    Schedule: {}", schedule)));
            }
            if !skill.variables.is_empty() {
                lines.push(ModalLine::blank());
                lines.push(ModalLine::accent(format!("  Variables ({})", skill.variables.len())));
                for v in &skill.variables {
                    let default = v.default.as_deref().unwrap_or("");
                    lines.push(ModalLine::normal(format!("    {} ({}): {}", v.name, v.description, default)));
                }
            }
            if !skill.steps.is_empty() {
                lines.push(ModalLine::blank());
                lines.push(ModalLine::accent(format!("  Steps ({})", skill.steps.len())));
                for (i, step) in skill.steps.iter().enumerate() {
                    lines.push(ModalLine::normal(format!("    {}. {}", i + 1, step.description)));
                }
            }
            if !skill.warnings.is_empty() {
                lines.push(ModalLine::blank());
                lines.push(ModalLine::error("  Warnings"));
                for w in &skill.warnings {
                    lines.push(ModalLine::normal(format!("    - {}", w)));
                }
            }
            app.active_modal = Some(AppModal::Info {
                title: format!("Hub \u{2014} {}", args),
                lines,
                scroll: 0,
            });
        }
        Err(e) => show_hub_error(app, "Hub Info", &e.to_string()),
    }
}

pub async fn handle_hub_install_github(app: &mut App, args: &str) {
    if args.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} GitHub Install".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub install-github <owner/repo>[@skill] [--force]"),
                ModalLine::muted("  Examples:"),
                ModalLine::muted("    /hub install-github mattpocock/skills"),
                ModalLine::muted("    /hub install-github mattpocock/skills@web-scraper"),
            ],
            scroll: 0,
        });
        return;
    }
    let parts: Vec<&str> = args.split_whitespace().collect();
    let mut force = false;
    let mut ref_parts: Vec<&str> = Vec::new();
    for part in parts {
        if part == "--force" {
            force = true;
        } else {
            ref_parts.push(part);
        }
    }
    let ref_ = ref_parts.join(" ");
    if ref_.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} GitHub Install".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub install-github <owner/repo>[@skill] [--force]"),
            ],
            scroll: 0,
        });
        return;
    }
    app.add_system_message(format!("Installing {} from GitHub...", ref_));
    match app.bridge.hub_install_github(&ref_, force).await {
        Ok(_) => app.add_system_message(format!("Installed {}", ref_)),
        Err(e) => show_hub_error(app, "GitHub Install", &e.to_string()),
    }
}

pub async fn handle_hub_update(app: &mut App, args: &str) {
    let name = args.trim();
    if name.is_empty() {
        app.add_system_message("Usage: /hub update <name>".into());
        return;
    }
    app.add_system_message(format!("Updating {}...", name));
    match app.bridge.hub_update(name).await {
        Ok(msg) => app.add_system_message(format!("Updated {}: {}", name, msg)),
        Err(e) => show_hub_error(app, "Hub Update", &e.to_string()),
    }
}

pub async fn handle_hub_remove(app: &mut App, args: &str) {
    let name = args.trim();
    if name.is_empty() {
        app.add_system_message("Usage: /hub remove <name>".into());
        return;
    }
    match app.bridge.hub_remove(name).await {
        Ok(()) => app.add_system_message(format!("Removed {}", name)),
        Err(e) => show_hub_error(app, "Hub Remove", &e.to_string()),
    }
}

pub async fn handle_hub_check_update(app: &mut App, args: &str) {
    let name = args.trim();
    if name.is_empty() {
        app.add_system_message("Usage: /hub check-update <name>".into());
        return;
    }
    match app.bridge.hub_check_update(name).await {
        Ok((has_update, msg)) => {
            if has_update {
                app.add_system_message(format!("Update available for {}: {}", name, msg));
            } else {
                app.add_system_message(format!("{} is up to date. {}", name, msg));
            }
        }
        Err(e) => show_hub_error(app, "Hub Check Update", &e.to_string()),
    }
}

pub async fn handle_hub_publish(app: &mut App, args: &str) {
    let name = args.trim();
    if name.is_empty() {
        app.active_modal = Some(AppModal::Info {
            title: "Hub \u{2014} Publish".into(),
            lines: vec![
                ModalLine::blank(),
                ModalLine::muted("  Usage: /hub publish <name>"),
            ],
            scroll: 0,
        });
        return;
    }
    app.add_system_message(format!("Publishing {}...", name));
    match app.bridge.hub_publish(name).await {
        Ok(msg) => app.add_system_message(format!("Published {}: {}", name, msg)),
        Err(e) => show_hub_error(app, "Hub Publish", &e.to_string()),
    }
}

pub static CMD_HUB: Command = Command {
    name: "/hub",
    aliases: &[],
    description: "Browse, install & manage hub skills",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_BROWSE: Command = Command {
    name: "/hub browse",
    aliases: &[],
    description: "Browse Skills Hub: /hub browse [--category <cat>]",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_SEARCH: Command = Command {
    name: "/hub search",
    aliases: &[],
    description: "Search Skills Hub: /hub search <query>",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_INSTALL: Command = Command {
    name: "/hub install",
    aliases: &[],
    description: "Install a hub skill: /hub install <name> [--force]",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_INFO: Command = Command {
    name: "/hub info",
    aliases: &[],
    description: "Show hub skill details: /hub info <name>",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_INSTALL_GITHUB: Command = Command {
    name: "/hub install-github",
    aliases: &[],
    description: "Install from GitHub: /hub install-github <owner/repo>[@skill] [--force]",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_PUBLISH: Command = Command {
    name: "/hub publish",
    aliases: &[],
    description: "Publish a local skill: /hub publish <name>",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_UPDATE: Command = Command {
    name: "/hub update",
    aliases: &[],
    description: "Update an installed skill: /hub update <name>",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_REMOVE: Command = Command {
    name: "/hub remove",
    aliases: &[],
    description: "Remove an installed skill: /hub remove <name>",
    category: CommandCategory::Hub,
};

pub static CMD_HUB_CHECK_UPDATE: Command = Command {
    name: "/hub check-update",
    aliases: &[],
    description: "Check for skill updates: /hub check-update <name>",
    category: CommandCategory::Hub,
};
