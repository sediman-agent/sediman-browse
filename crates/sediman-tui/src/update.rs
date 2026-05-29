use sediman_tui_bridge::WsMessage;

use sediman_tui_core::event::AppEvent;

use crate::app::App;
use crate::commands::{
    browser, delegate, hub, memory, misc, model, plan, record, schedule, sessions,
    skills, soul, system, terminal,
};

pub async fn handle_message(app: &mut App, event: AppEvent) {
    match event {
        AppEvent::Key(key) => {
            use crossterm::event::KeyCode;
            match key.code {
                KeyCode::Esc => {
                    if app.agent_running {
                        app.interrupt.trigger();
                        app.agent_running = false;
                        app.step_log.push("-- Interrupted --".to_string());
                    }
                }
                KeyCode::Enter => {
                    if key.modifiers.contains(crossterm::event::KeyModifiers::SHIFT) {
                        app.editor.input(key);
                    } else {
                        let input = app.editor.submit();
                        if !input.is_empty() {
                            if input.starts_with('/') {
                                handle_slash(app, &input).await;
                            } else if let Some(stripped) = input.strip_prefix('!') {
                                handle_shell(app, stripped).await;
                            } else {
                                handle_task(app, &input).await;
                            }
                        }
                    }
                }
                KeyCode::Tab => {
                    let prefix = app.editor.lines().join(" ").trim().to_string();
                    if let Some(cmd) = app.command_registry.find_fuzzy(&prefix) {
                        app.editor.delete_line_by_head();
                        app.editor.insert_str(cmd.name);
                    }
                }
                KeyCode::Up => app.editor.history_up(),
                KeyCode::Down => app.editor.history_down(),
                KeyCode::BackTab => {
                    app.permission.cycle();
                    app.step_log
                        .push(format!("Mode: {}", app.permission.current_label()));
                }
                _ => {
                    app.editor.input(key);
                }
            }
        }
        AppEvent::Tick => {}
        AppEvent::Resize(_, _) => {}
        AppEvent::Channel(msg) => {
            if let Some(ws_msg) = msg.downcast_ref::<WsMessage>() {
                match ws_msg.msg_type.as_str() {
                    "step" => {
                        if let Some(event) = &ws_msg.event {
                            let line = format!("{} {}", event.phase, event.action);
                            app.step_log.push(line);
                            app.step_log.truncate(200);
                        }
                    }
                    "result" => {
                        app.agent_running = false;
                        app.last_result = ws_msg.result.clone();
                        if let Some(ref result) = app.last_result {
                            let status = if result.success { "✓" } else { "✗" };
                            app.step_log
                                .push(format!("{} Done ({}s)", status, result.elapsed_secs));
                            if result.skill_created.is_some() {
                                app.step_log
                                    .push("◆ Skill created from this task".to_string());
                            }
                            if result.scheduled_job_id.is_some() {
                                app.step_log
                                    .push("◇ Scheduled job created".to_string());
                            }
                        }
                    }
                    "error" => {
                        app.agent_running = false;
                        if let Some(err) = &ws_msg.error {
                            app.step_log.push(format!("✗ Error: {}", err));
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}

async fn handle_slash(app: &mut App, input: &str) {
    let input = input.trim();
    let space_idx = input.find(' ');
    let (cmd_name, args) = match space_idx {
        Some(i) => (input[..i].to_string(), input[i + 1..].trim().to_string()),
        None => (input.to_string(), String::new()),
    };

    match cmd_name.as_str() {
        "/help" | "/h" | "/?" => system::handle_help(app, &args).await,
        "/exit" | "/quit" | "/q" => system::handle_exit(app, &args).await,
        "/clear" => system::handle_clear(app, &args).await,
        "/reset" => system::handle_reset(app, &args).await,
        "/compress" => system::handle_compress(app, &args).await,
        "/status" => system::handle_status(app, &args).await,
        "/skills" | "/skill list" => skills::handle_skills(app, &args).await,
        "/skill" => skills::handle_skill(app, &args).await,
        "/run-skill" => skills::handle_run_skill(app, &args).await,
        "/hub browse" => hub::handle_hub_browse(app, &args).await,
        "/hub search" => hub::handle_hub_search(app, &args).await,
        "/hub install" => hub::handle_hub_install(app, &args).await,
        "/hub info" => hub::handle_hub_info(app, &args).await,
        "/hub publish" => hub::handle_hub_publish(app, &args).await,
        "/memory" => memory::handle_memory(app, &args).await,
        "/remember" => memory::handle_remember(app, &args).await,
        "/model" => model::handle_model(app, &args).await,
        "/models" => model::handle_models(app, &args).await,
        "/schedule" => schedule::handle_schedule(app, &args).await,
        "/schedule-add" => schedule::handle_schedule_add(app, &args).await,
        "/schedule-remove" => schedule::handle_schedule_remove(app, &args).await,
        "/sessions" => sessions::handle_sessions(app, &args).await,
        "/resume" => sessions::handle_resume(app, &args).await,
        "/browser" => browser::handle_browser(app, &args).await,
        "/screenshot" => browser::handle_screenshot(app, &args).await,
        "/record" => record::handle_record(app, &args).await,
        "/stop" => record::handle_stop(app, &args).await,
        "/delegate" => delegate::handle_delegate(app, &args).await,
        "/parallel" => delegate::handle_parallel(app, &args).await,
        "/terminal" => terminal::handle_terminal(app, &args).await,
        "/plan" => plan::handle_plan(app, &args).await,
        "/soul" => soul::handle_soul(app, &args).await,
        "/usage" => misc::handle_usage(app, &args).await,
        "/doctor" => misc::handle_doctor(app, &args).await,
        "/export" => misc::handle_export(app, &args).await,
        "/btw" => misc::handle_btw(app, &args).await,
        "/color" => misc::handle_color(app, &args).await,
        "/rename" => misc::handle_rename(app, &args).await,
        _ => {
            app.step_log.push(format!("Unknown command: {}. Type /help", cmd_name));
        }
    }
}

async fn handle_shell(app: &mut App, cmd: &str) {
    if !app.permission.is_allowed(cmd) {
        app.step_log
            .push("Shell command denied by permission mode".to_string());
        return;
    }
    app.step_log.push(format!("$ {}", cmd));
    crate::shell::run_shell_command(app, cmd).await;
}

async fn handle_task(app: &mut App, task: &str) {
    app.show_banner = false;
    app.show_side_panel = true;
    app.agent_running = true;
    app.agent_start = std::time::Instant::now();
    app.task_count += 1;
    app.step_log.clear();
    app.step_log.push(format!("Task: {}", task));
    app.spinner_text = "Starting...".to_string();

    if let Err(e) = run_agent_task(app, task).await {
        app.agent_running = false;
        app.step_log.push(format!("✗ Failed: {}", e));
    }
}

async fn run_agent_task(app: &mut App, task: &str) -> Result<(), Box<dyn std::error::Error>> {
    let bridge_url = "http://localhost:8080";
    let mut stream =
        sediman_tui_bridge::agent::TaskStream::submit(bridge_url, task).await?;

    let mut final_result = None;
    while let Some(msg) = stream.rx.recv().await {
        match msg.msg_type.as_str() {
            "step" => {
                if let Some(event) = &msg.event {
                    let line = format!("{} {}", event.phase, event.action);
                    app.step_log.push(line);
                    app.step_log.truncate(200);
                    if let Some(ref url) = event.url {
                        app.step_log.push(format!("  └ {}", url));
                    }
                }
            }
            "result" => {
                final_result = msg.result;
                break;
            }
            "error" => {
                let err = msg.error.unwrap_or("Unknown".into());
                app.step_log.push(format!("✗ {}", err));
                return Err(err.into());
            }
            _ => {}
        }
    }

    match final_result {
        Some(result) => {
            app.last_result = Some(result.clone());
            let status = if result.success { "✓" } else { "✗" };
            app.step_log.push(format!("{} Done ({}s)", status, result.elapsed_secs));
            if result.skill_created.is_some() {
                app.step_log.push("◆ Skill created from this task".to_string());
            }
            if let Some(ref job) = result.scheduled_job_id {
                app.step_log.push(format!("◇ Scheduled: {}", job));
            }
            Ok(())
        }
        None => Err("No result received".into()),
    }
}
