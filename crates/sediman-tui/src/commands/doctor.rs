#![allow(dead_code)]
use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal, DoctorCheck, DoctorStatus};

pub static CMD_DOCTOR: Command = Command {
    name: "/doctor",
    aliases: &[],
    description: "Diagnose & install dependencies",
    category: CommandCategory::Utilities,
};

pub async fn handle_doctor(app: &mut App, _args: &str) {
    let checks = run_all_checks_sync(app).await;
    app.active_modal = Some(AppModal::Doctor {
        checks,
        cursor: 0,
        scroll: 0,
        installing: false,
        install_output: Vec::new(),
    });
}

pub async fn run_all_checks_sync(app: &App) -> Vec<DoctorCheck> {
    let mut checks = Vec::new();

    checks.extend(check_browser());
    checks.extend(check_ai_llm(&app.bridge, &app.provider).await);
    checks.extend(check_tools());
    checks.extend(check_python());
    checks.extend(check_system(&app.bridge).await);

    checks
}

pub async fn run_checks_for_recheck(bridge: &sediman_tui_bridge::ApiClient, provider: &str) -> Vec<DoctorCheck> {
    let mut checks = Vec::new();
    checks.extend(check_browser());
    checks.extend(check_ai_llm(bridge, provider).await);
    checks.extend(check_tools());
    checks.extend(check_python());
    checks.extend(check_system(bridge).await);
    checks
}

pub async fn run_single_check(category: &str, name: &str, _optional: bool, _install_cmd: Option<&str>, bridge: &sediman_tui_bridge::ApiClient, provider: &str) -> Vec<DoctorCheck> {
    match category {
        "Browser" => check_browser(),
        "AI & LLM" => check_ai_llm(bridge, provider).await,
        "Tools" => check_tools(),
        "Python" => check_python(),
        "System" => check_system(bridge).await,
        _ => vec![],
    }
    .into_iter()
    .filter(|c| c.name == name)
    .collect()
}

fn check_browser() -> Vec<DoctorCheck> {
    let mut result = Vec::new();

    let chrome = find_chrome();
    match chrome {
        Some(path) => result.push(DoctorCheck {
            category: "Browser",
            name: "Chrome/Chromium",
            status: DoctorStatus::Pass,
            message: format!("installed ({})", path),
            optional: false,
            install_cmd: None,
        }),
        None => result.push(DoctorCheck {
            category: "Browser",
            name: "Chrome/Chromium",
            status: DoctorStatus::Fail,
            message: "not found".into(),
            optional: false,
            install_cmd: Some(chrome_install_cmd()),
        }),
    }

    match which("playwright") {
        Some(_) => result.push(DoctorCheck {
            category: "Browser",
            name: "Playwright",
            status: DoctorStatus::Pass,
            message: "installed".into(),
            optional: false,
            install_cmd: None,
        }),
        None => result.push(DoctorCheck {
            category: "Browser",
            name: "Playwright",
            status: DoctorStatus::Warn,
            message: "not found (bundled via Python)".into(),
            optional: true,
            install_cmd: None,
        }),
    }

    let pw_drivers = std::path::Path::new(&std::env::var("HOME").unwrap_or_default())
        .join(".cache")
        .join("ms-playwright");
    if pw_drivers.exists() {
        result.push(DoctorCheck {
            category: "Browser",
            name: "Playwright drivers",
            status: DoctorStatus::Pass,
            message: "installed".into(),
            optional: false,
            install_cmd: None,
        });
    } else {
        result.push(DoctorCheck {
            category: "Browser",
            name: "Playwright drivers",
            status: DoctorStatus::Fail,
            message: "not installed".into(),
            optional: false,
            install_cmd: Some("uv run playwright install chromium".into()),
        });
    }

    result
}

async fn check_ai_llm(bridge: &sediman_tui_bridge::ApiClient, provider: &str) -> Vec<DoctorCheck> {
    let mut result = Vec::new();

    let has_key = check_api_key(provider);
    result.push(DoctorCheck {
        category: "AI & LLM",
        name: "API key",
        status: if has_key { DoctorStatus::Pass } else { DoctorStatus::Fail },
        message: if has_key {
            format!("configured ({})", provider)
        } else {
            "not set — use /connect".into()
        },
        optional: false,
        install_cmd: None,
    });

    match bridge.status().await {
        Ok(status) => result.push(DoctorCheck {
            category: "AI & LLM",
            name: "Backend server",
            status: DoctorStatus::Pass,
            message: format!("ok (uptime {}s)", status.uptime_secs),
            optional: false,
            install_cmd: None,
        }),
        Err(_) => result.push(DoctorCheck {
            category: "AI & LLM",
            name: "Backend server",
            status: DoctorStatus::Fail,
            message: "not reachable".into(),
            optional: false,
            install_cmd: None,
        }),
    }

    result
}

fn check_tools() -> Vec<DoctorCheck> {
    let mut result = Vec::new();

    let tools: Vec<(&str, bool, String)> = vec![
        ("git", false, git_install_cmd()),
        ("uv", false, "curl -LsSf https://astral.sh/uv/install.sh | sh".into()),
        ("rg", false, rg_install_cmd()),
        ("opencode", true, "curl -fsSL https://opencode.ai/install | sh".into()),
        ("fd", true, fd_install_cmd()),
        ("bun", true, "curl -fsSL https://bun.sh/install | bash".into()),
        ("node", true, node_install_cmd()),
        ("sediman-sandbox", true, "make install-sandbox".into()),
        ("docker", true, docker_install_cmd()),
    ];

    for (name, optional, install) in tools {
        match which(name) {
            Some(path) => result.push(DoctorCheck {
                category: "Tools",
                name,
                status: DoctorStatus::Pass,
                message: if path.len() < 50 {
                    format!("installed ({})", path)
                } else {
                    "installed".into()
                },
                optional,
                install_cmd: None,
            }),
            None => result.push(DoctorCheck {
                category: "Tools",
                name,
                status: if optional { DoctorStatus::Warn } else { DoctorStatus::Fail },
                message: if optional { "not found (optional)".into() } else { "not found".into() },
                optional,
                install_cmd: Some(install.to_string()),
            }),
        }
    }

    result
}

fn check_python() -> Vec<DoctorCheck> {
    let mut result = Vec::new();

    match get_python_version() {
        Some(ver) => {
            let ok = ver.starts_with("Python 3.1")
                || ver.starts_with("Python 3.2")
                || ver.starts_with("Python 3.3")
                || ver == "Python 3.11"
                || ver.starts_with("Python 3.12")
                || ver.starts_with("Python 3.13");
            result.push(DoctorCheck {
                category: "Python",
                name: "Python 3.11+",
                status: if ok { DoctorStatus::Pass } else { DoctorStatus::Fail },
                message: if ok { format!("installed ({})", ver) } else { format!("{} — need 3.11+", ver) },
                optional: false,
                install_cmd: if ok { None } else { Some(python_install_cmd()) },
            });
        }
        None => result.push(DoctorCheck {
            category: "Python",
            name: "Python 3.11+",
            status: DoctorStatus::Fail,
            message: "not found".into(),
            optional: false,
            install_cmd: Some(python_install_cmd()),
        }),
    }

    match std::process::Command::new("python3")
        .arg("-c")
        .arg("import sediman")
        .output()
    {
        Ok(o) if o.status.success() => result.push(DoctorCheck {
            category: "Python",
            name: "sediman package",
            status: DoctorStatus::Pass,
            message: "installed".into(),
            optional: false,
            install_cmd: None,
        }),
        _ => result.push(DoctorCheck {
            category: "Python",
            name: "sediman package",
            status: DoctorStatus::Warn,
            message: "not importable".into(),
            optional: false,
            install_cmd: Some("uv pip install -e .".into()),
        }),
    }

    result
}

async fn check_system(bridge: &sediman_tui_bridge::ApiClient) -> Vec<DoctorCheck> {
    let mut result = Vec::new();

    let home = std::env::var("HOME").unwrap_or_default();
    let config_dir = std::path::Path::new(&home).join(".sediman");
    if config_dir.exists() {
        result.push(DoctorCheck {
            category: "System",
            name: "Config directory",
            status: DoctorStatus::Pass,
            message: "~/.sediman/".to_string(),
            optional: false,
            install_cmd: None,
        });
    } else {
        result.push(DoctorCheck {
            category: "System",
            name: "Config directory",
            status: DoctorStatus::Warn,
            message: "~/.sediman/ not found".into(),
            optional: false,
            install_cmd: Some("mkdir -p ~/.sediman".into()),
        });
    }

    let connected = bridge.is_connected().await;
    result.push(DoctorCheck {
        category: "System",
        name: "Unix socket",
        status: if connected { DoctorStatus::Pass } else { DoctorStatus::Fail },
        message: if connected { "connected".into() } else { "not connected".into() },
        optional: false,
        install_cmd: None,
    });

    match get_disk_space() {
        Some(space) => {
            let gb = space as f64 / 1_000_000_000.0;
            result.push(DoctorCheck {
                category: "System",
                name: "Disk space",
                status: if gb > 1.0 { DoctorStatus::Pass } else { DoctorStatus::Warn },
                message: format!("{:.1} GB available", gb),
                optional: false,
                install_cmd: None,
            });
        }
        None => result.push(DoctorCheck {
            category: "System",
            name: "Disk space",
            status: DoctorStatus::Pass,
            message: "unknown".into(),
            optional: true,
            install_cmd: None,
        }),
    }

    result
}

fn find_chrome() -> Option<String> {
    if cfg!(target_os = "macos") {
        let paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ];
        for p in &paths {
            if std::path::Path::new(p).exists() {
                return Some(p.to_string());
            }
        }
    }
    for name in &["google-chrome-stable", "google-chrome", "chromium-browser", "chromium"] {
        if let Some(p) = which(name) {
            return Some(p);
        }
    }
    None
}

fn which(name: &str) -> Option<String> {
    std::process::Command::new("which")
        .arg(name)
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .filter(|s| !s.is_empty())
}

fn get_python_version() -> Option<String> {
    std::process::Command::new("python3")
        .arg("--version")
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
}

fn get_disk_space() -> Option<u64> {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/".into());
    let output = std::process::Command::new("df")
        .arg("-k")
        .arg(&home)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let line = text.lines().nth(1)?;
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() >= 4 {
        parts[3].parse::<u64>().ok().map(|kb| kb * 1024)
    } else {
        None
    }
}

fn check_api_key(provider: &str) -> bool {
    if !provider.is_empty() {
        let home = std::env::var("HOME").unwrap_or_default();
        let auth_file = std::path::Path::new(&home)
            .join(".sediman")
            .join("auth.json");
        if let Ok(data) = std::fs::read_to_string(&auth_file) {
            if let Ok(map) = serde_json::from_str::<serde_json::Value>(&data) {
                if let Some(obj) = map.as_object() {
                    for (_k, v) in obj {
                        if let Some(s) = v.as_str() {
                            if !s.is_empty() {
                                return true;
                            }
                        }
                    }
                }
            }
        }
        let env_key = format!("{}_API_KEY", provider.to_uppercase().replace('-', "_"));
        if std::env::var(&env_key).is_ok() {
            return true;
        }
        if std::env::var("OPENAI_API_KEY").is_ok() {
            return true;
        }
    }
    false
}

fn chrome_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "brew install --cask google-chrome".into()
    } else if which("apt").is_some() {
        "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && apt install -y google-chrome-stable".into()
    } else if which("dnf").is_some() {
        "dnf install -y google-chrome-stable".into()
    } else {
        "curl -LsSf https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/chrome.deb && sudo dpkg -i /tmp/chrome.deb".into()
    }
}

fn git_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "xcode-select --install".into()
    } else {
        "sudo apt install -y git".into()
    }
}

fn rg_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "brew install ripgrep".into()
    } else if which("apt").is_some() {
        "sudo apt install -y ripgrep".into()
    } else {
        "curl -LO https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz && tar xzf ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz && sudo cp ripgrep-14.1.1-x86_64-unknown-linux-musl/rg /usr/local/bin/".into()
    }
}

fn fd_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "brew install fd".into()
    } else {
        "sudo apt install -y fd-find".into()
    }
}

fn node_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "brew install node".into()
    } else {
        "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs".into()
    }
}

fn docker_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "brew install --cask docker".into()
    } else {
        "curl -fsSL https://get.docker.com | sh".into()
    }
}

fn python_install_cmd() -> String {
    if cfg!(target_os = "macos") {
        "brew install python@3.12".into()
    } else {
        "sudo apt install -y python3.12 python3.12-venv".into()
    }
}
