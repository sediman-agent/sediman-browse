use std::time::{Duration, Instant};

use ratatui::Terminal;
use ratatui::backend::CrosstermBackend;

use sediman_tui_bridge::{ApiClient, AgentResult, WsMessage};
use sediman_tui_core::{
    event::{AppEvent, EventLoop},
    input::TextEditor,
    command::CommandRegistry,
    layout::LayoutManager,
    styling::Theme,
};

use crate::commands::register_commands;
use crate::permission::PermissionManager;
use crate::interrupt::InterruptManager;
use crate::update::handle_message;

pub struct App {
    pub provider: String,
    pub model: Option<String>,
    pub headless: bool,
    pub bridge: ApiClient,
    #[allow(dead_code)]
    pub theme: Theme,
    #[allow(dead_code)]
    pub layout: LayoutManager,
    pub command_registry: CommandRegistry,
    pub editor: TextEditor,
    pub permission: PermissionManager,
    pub interrupt: InterruptManager,

    pub running: bool,
    pub task_count: usize,
    #[allow(dead_code)]
    pub session_start: Instant,
    pub session_name: Option<String>,
    pub session_color: Option<String>,
    pub agent_running: bool,
    pub agent_start: Instant,
    pub spinner_text: String,
    pub step_log: Vec<String>,
    pub last_result: Option<AgentResult>,
    pub show_help: bool,
    pub show_banner: bool,
    pub show_side_panel: bool,
    #[allow(dead_code)]
    pub side_panel_tab: SideTab,
    pub output_text: String,
}

#[derive(Clone, Copy, PartialEq)]
#[allow(dead_code)]
pub enum SideTab {
    Skills,
    Memory,
    Schedule,
    Status,
}

impl App {
    pub fn new(provider: String, model: Option<String>, headless: bool, bridge: ApiClient) -> Self {
        let mut layout = LayoutManager::new();
        layout.show_banner = true;

        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);

        Self {
            provider,
            model,
            headless,
            bridge,
            theme: Theme::default(),
            layout,
            command_registry: registry,
            editor: TextEditor::new(),
            permission: PermissionManager::new(),
            interrupt: InterruptManager::new(),

            running: true,
            task_count: 0,
            session_start: Instant::now(),
            session_name: None,
            session_color: None,
            agent_running: false,
            agent_start: Instant::now(),
            spinner_text: String::new(),
            step_log: Vec::new(),
            last_result: None,
            show_help: false,
            show_banner: true,
            show_side_panel: false,
            side_panel_tab: SideTab::Skills,
            output_text: String::new(),
        }
    }
}

pub async fn run(
    mut app: App,
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
) -> Result<(), Box<dyn std::error::Error>> {
    let event_loop = EventLoop::new(10.0);
    let event_tx = event_loop.sender();

    let (step_tx, mut step_rx) = tokio::sync::mpsc::unbounded_channel::<WsMessage>();
    let (_scheduler_tx, mut scheduler_rx) = tokio::sync::mpsc::unbounded_channel::<String>();

    let event_tx_clone = event_tx.clone();
    let _step_tx_clone = step_tx.clone();

    let handle = tokio::spawn(async move {
        event_loop
            .run(move |event| {
                let event_tx = event_tx_clone.clone();
                async move {
                    let _ = event_tx.send(event);
                }
            })
            .await;
    });

    loop {
        terminal.draw(|frame| {
            crate::view::render(frame, &mut app);
        })?;

        tokio::select! {
            Some(msg) = step_rx.recv() => {
                handle_message(&mut app, AppEvent::Channel(Box::new(msg))).await;
            }
            Some(msg) = scheduler_rx.recv() => {
                app.output_text.push_str(&format!("\n[Cron] {}", msg));
            }
            _ = tokio::time::sleep(Duration::from_millis(50)) => {
                if app.agent_running {
                    app.spinner_text = format!("running... {}s", app.agent_start.elapsed().as_secs());
                }
            }
        }

        if !app.running {
            break;
        }
    }

    handle.abort();
    Ok(())
}
