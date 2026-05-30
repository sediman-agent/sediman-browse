use std::panic;
use std::time::Duration;

use clap::Parser;

mod app;
mod update;
mod view;
mod commands;
mod shell;
mod permission;
mod interrupt;
mod logging;
mod gpu_app;
mod config;

#[derive(Parser, Debug)]
#[command(name = "sediman-tui", about = "Sediman TUI — browser agent terminal frontend", version = "0.1.1")]
struct Args {
    #[arg(long, default_value = "openai")]
    provider: String,

    #[arg(long)]
    model: Option<String>,

    /// Base URL for the LLM provider API (e.g. https://api.minimax.chat/v1)
    #[arg(long)]
    base_url: Option<String>,

    #[arg(long)]
    headless: bool,

    /// Unix socket path for the Python backend.
    /// Default: /tmp/sediman-python.sock (connects directly to Python RPC server)
    #[arg(long, default_value = "/tmp/sediman-python.sock")]
    socket: String,

    /// Skip auto-starting the Python backend (expect it to already be running)
    #[arg(long)]
    no_spawn: bool,

    #[arg(long)]
    gpu: bool,
}

/// Auto-start the Python RPC backend if the socket doesn't exist yet.
/// Returns the child process handle if we spawned it (so we can kill on exit),
/// or None if the backend was already running.
async fn ensure_backend(
    socket_path: &str,
    no_spawn: bool,
    provider: &str,
    model: Option<&str>,
    base_url: Option<&str>,
) -> Option<tokio::process::Child> {
    // If socket exists, verify the backend is actually responsive
    if tokio::fs::metadata(socket_path).await.is_ok() {
        let bridge = sediman_tui_bridge::ApiClient::new(socket_path);
        match tokio::time::timeout(Duration::from_secs(2), bridge.status()).await {
            Ok(Ok(_)) => return None, // backend is alive
            _ => {
                eprintln!("Stale socket detected at {}, removing...", socket_path);
                let _ = tokio::fs::remove_file(socket_path).await;
            }
        }
    }

    if no_spawn {
        eprintln!("Warning: Backend not running at {} and --no-spawn set.", socket_path);
        eprintln!("  Start it manually: uv run python -m sediman.rpc_server");
        return None;
    }

    // Try to find uv or python
    let (cmd, args) = if which_exists("uv").await {
        ("uv", vec!["run", "python", "-m", "sediman.rpc_server"])
    } else if which_exists("python3").await {
        ("python3", vec!["-m", "sediman.rpc_server"])
    } else if which_exists("python").await {
        ("python", vec!["-m", "sediman.rpc_server"])
    } else {
        eprintln!("Error: Cannot find Python or uv to start the backend.");
        eprintln!("  Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh");
        return None;
    };

    eprintln!("Starting backend: {} {}", cmd, args.join(" "));

    let mut child_cmd = tokio::process::Command::new(cmd);
    child_cmd
        .args(&args)
        .env("SEDIMAN_PYTHON_SOCKET", socket_path)
        .env("SEDIMAN_PROVIDER", provider)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());

    if let Some(m) = model {
        child_cmd.env("SEDIMAN_MODEL", m);
    }
    if let Some(url) = base_url {
        child_cmd.env("SEDIMAN_BASE_URL", url);
    }

    let child = child_cmd.spawn();

    let mut child = match child {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Error: Failed to start backend: {}", e);
            return None;
        }
    };

    // Wait for the socket to appear (up to 15 seconds)
    for i in 0..30 {
        tokio::time::sleep(Duration::from_millis(500)).await;
        if tokio::fs::metadata(socket_path).await.is_ok() {
            eprintln!("  Backend ready ({})", socket_path);
            return Some(child);
        }
        // Check if process died
        match child.try_wait() {
            Ok(Some(status)) => {
                eprintln!("Error: Backend process exited: {}", status);
                return None;
            }
            Ok(None) => {} // still running
            Err(_) => {}
        }
        if i == 4 {
            eprintln!("  Waiting for backend...");
        }
    }

    eprintln!("Error: Backend did not start within 15 seconds.");
    let _ = child.kill().await;
    None
}

async fn which_exists(cmd: &str) -> bool {
    tokio::process::Command::new("which")
        .arg(cmd)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .await
        .map(|s| s.success())
        .unwrap_or(false)
}

#[tokio::main]
async fn main() {
    logging::setup();

    let original_hook = panic::take_hook();
    panic::set_hook(Box::new(move |info| {
        crossterm::terminal::disable_raw_mode().ok();
        use std::io::Write;
        let mut stdout = std::io::stdout();
        let _ = stdout.write_all(b"\x1b[?1000l");
        let _ = stdout.write_all(b"\x1b[?2004l");
        let _ = stdout.write_all(b"\x1b[?25h");
        let _ = stdout.write_all(b"\x1b[?1049l");
        let _ = stdout.flush();
        original_hook(info);
    }));

    let args = Args::parse();

    // Auto-start Python backend if needed
    let backend_child = ensure_backend(
        &args.socket,
        args.no_spawn,
        &args.provider,
        args.model.as_deref(),
        args.base_url.as_deref(),
    ).await;

    let bridge = sediman_tui_bridge::ApiClient::new(&args.socket);

    // Sync provider/model/base-url with the backend (in case it was already running).
    // Retry a few times because the backend may have just started.
    let mut synced = false;
    for attempt in 0..5 {
        match bridge.switch_model(
            &args.provider,
            args.model.as_deref(),
            args.base_url.as_deref(),
        ).await {
            Ok(()) => { synced = true; break; }
            Err(e) if attempt < 4 => {
                eprintln!("switch_model attempt {} failed: {}, retrying...", attempt + 1, e);
                tokio::time::sleep(Duration::from_millis(200 * (attempt + 1) as u64)).await;
            }
            Err(e) => {
                eprintln!("Warning: Could not switch model ({})", e);
            }
        }
    }
    if synced {
        eprintln!("Model synced: {} / {:?}", args.provider, args.model);
    }

    // Load persisted config
    let saved_config = crate::config::TuiConfig::load();
    let headless = if args.headless { true } else { saved_config.headless };

    let mut app_state = app::App::new(args.provider, args.model, args.base_url, headless, bridge);

    // Apply saved theme
    if !saved_config.theme.is_empty() {
        if let Some(theme) = sediman_tui_core::styling::load_theme(&saved_config.theme) {
            app_state.theme = theme;
            app_state.theme_name = saved_config.theme.clone();
        }
    }

    // Apply saved config to app state
    if saved_config.side_panel_open {
        app_state.show_side_panel = true;
    }
    app_state.side_panel_tab = match saved_config.side_panel_tab.as_str() {
        "Skills" => app::SideTab::Skills,
        "Memory" => app::SideTab::Memory,
        "Schedule" => app::SideTab::Schedule,
        _ => app::SideTab::Status,
    };

    // Apply saved models
    if !saved_config.saved_models.is_empty() {
        app_state.model_picker_list = saved_config.saved_models;
    }

    if args.gpu {
        #[cfg(feature = "gpu")]
        {
            let result = gpu_app::run_gpu(app_state).await;
            if let Err(e) = result {
                eprintln!("GPU error: {}", e);
                std::process::exit(1);
            }
            return;
        }
        #[cfg(not(feature = "gpu"))]
        {
            eprintln!("GPU support not compiled in. Rebuild with: cargo build --features gpu");
            std::process::exit(1);
        }
    }

    crossterm::terminal::enable_raw_mode().expect("Failed to enable raw mode");
    let mut stdout = std::io::stdout();
    use std::io::Write;
    let _ = stdout.write_all(b"\x1b[?1049h");
    let _ = stdout.write_all(b"\x1b[?25l");
    let _ = stdout.write_all(b"\x1b[?2004h");
    let _ = stdout.write_all(b"\x1b[?1000h");
    let _ = stdout.flush();

    let result = app::run(app_state).await;

    crossterm::terminal::disable_raw_mode().ok();
    let _ = std::io::Write::write_all(&mut stdout, b"\x1b[?1000l");
    let _ = std::io::Write::write_all(&mut stdout, b"\x1b[?2004l");
    let _ = std::io::Write::write_all(&mut stdout, b"\x1b[?25h");
    let _ = std::io::Write::write_all(&mut stdout, b"\x1b[?1049l");
    let _ = std::io::Write::flush(&mut stdout);

    // Clean up backend if we spawned it
    if let Some(mut child) = backend_child {
        let _ = child.kill().await;
    }

    if let Err(e) = result {
        eprintln!("Error: {}", e);
        std::process::exit(1);
    }
}
