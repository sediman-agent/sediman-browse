use std::panic;

use clap::Parser;

mod app;
mod update;
mod view;
mod commands;
mod shell;
mod permission;
mod interrupt;
mod logging;

#[derive(Parser, Debug)]
#[command(name = "sediman-tui", about = "Sediman TUI — browser agent terminal frontend", version = "0.1.1")]
struct Args {
    #[arg(long, default_value = "openai")]
    provider: String,

    #[arg(long)]
    model: Option<String>,

    #[arg(long)]
    base_url: Option<String>,

    #[arg(long)]
    headless: bool,

    #[arg(long, default_value = "http://localhost:8080")]
    api_url: String,
}

#[tokio::main]
async fn main() {
    logging::setup();

    // Ensure terminal is always restored, even on panic
    let original_hook = panic::take_hook();
    panic::set_hook(Box::new(move |info| {
        ratatui::restore();
        original_hook(info);
    }));

    let args = Args::parse();

    let bridge = match sediman_tui_bridge::ApiClient::new(&args.api_url) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to connect to API at {}: {}", args.api_url, e);
            eprintln!("Start the API server with: sediman serve");
            std::process::exit(1);
        }
    };

    let app_state = app::App::new(args.provider, args.model, args.headless, bridge);

    let mut terminal = ratatui::init();
    let _ = terminal.clear();

    let result = app::run(app_state, &mut terminal).await;

    ratatui::restore();

    if let Err(e) = result {
        eprintln!("Error: {}", e);
        std::process::exit(1);
    }
}
