use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal, ModalLine};

/// Check if an error is a connection failure (backend not running).
fn is_connection_error(e: &str) -> bool {
    e.contains("Connection failed") || e.contains("No such file") || e.contains("os error 2")
}

/// Show a connection-error modal instead of dumping into chat.
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

/// Show any other hub error as a modal.
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
            let mut lines = vec![
                ModalLine::heading(format!("  Hub Skills ({})", skills.len())),
                ModalLine::blank(),
            ];
            for s in &skills {
                lines.push(ModalLine::primary(format!("  {} v{}", s.name, s.version)));
                lines.push(ModalLine::muted(format!("    by {} \u{2014} {} [{}]", s.author, s.description, s.trust)));
            }
            app.active_modal = Some(AppModal::Info {
                title: "Hub \u{2014} Browse".into(),
                lines,
                scroll: 0,
            });
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
            let mut lines = vec![
                ModalLine::heading(format!("  Results for '{}'", args)),
                ModalLine::blank(),
            ];
            for s in &skills {
                lines.push(ModalLine::primary(format!("  {}", s.name)));
                lines.push(ModalLine::muted(format!("    {}", s.description)));
            }
            app.active_modal = Some(AppModal::Info {
                title: format!("Hub \u{2014} Search: {}", args),
                lines,
                scroll: 0,
            });
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
    match app.bridge.hub_info(args).await {
        Ok(skill) => {
            let lines = vec![
                ModalLine::heading(format!("  {} v{}", skill.name, skill.version)),
                ModalLine::muted(format!("    by {}", skill.author)),
                ModalLine::blank(),
                ModalLine::normal(format!("    {}", skill.description)),
                ModalLine::blank(),
                ModalLine::normal(format!("    Category: {}", skill.category)),
                ModalLine::normal(format!("    Trust: {}", skill.trust)),
            ];
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

pub async fn handle_hub_publish(app: &mut App, args: &str) {
    if args.is_empty() {
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
    app.add_system_message(format!("Publishing {}...", args));
    app.add_system_message("Publish requires a GitHub token. Use the Python CLI or SDK for full publish support.".into());
}

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
