use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use tokio::sync::mpsc;

use sediman_tui_core::event::AppEvent;

use crate::app::{App, AppModal};
use crate::commands::{
    browser, delegate, hub, memory, misc, model, plan, provider, record, schedule, sessions,
    skills, soul, system, terminal, theming,
};

const DEFAULT_SOUL: &str = "You are Sediman, a self-improving browser automation agent.

You are pragmatic, concise, and efficient. You complete browser tasks with minimal steps.

Communication style:
- Be brief but thorough
- When reporting results, lead with the answer
- If something fails, explain what went wrong and what you tried
- Proactively suggest improvements when you notice patterns";

pub async fn handle_message(app: &mut App, event: AppEvent, event_tx: &mpsc::UnboundedSender<AppEvent>) {
    match event {
        AppEvent::Key(key) => {
            use crossterm::event::{KeyCode, KeyModifiers};

            // Clipboard: Ctrl+V paste
            if key.code == KeyCode::Char('v') && key.modifiers.contains(KeyModifiers::CONTROL) && !key.modifiers.contains(KeyModifiers::SHIFT) {
                if let Ok(mut clipboard) = arboard::Clipboard::new() {
                    if let Ok(text) = clipboard.get_text() {
                        app.editor.insert_str(&text);
                    }
                }
                return;
            }
            if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) && key.modifiers.contains(KeyModifiers::SHIFT) {
                if let Some(result) = &app.last_result {
                    if let Ok(mut clipboard) = arboard::Clipboard::new() {
                        let _ = clipboard.set_text(&result.result);
                    }
                }
                return;
            }

            // ── Unified modal key handling ──
            if app.active_modal.is_some() {
                // ModelPicker has its own input mode — all chars go to search/add field
                if matches!(app.active_modal, Some(AppModal::ModelPicker)) {
                    match key.code {
                        KeyCode::Esc => {
                            app.model_picker_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.model_picker_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Enter => {
                            if !app.model_picker_input.is_empty() {
                                // Add/switch to the typed model
                                let input = app.model_picker_input.clone();
                                let (new_provider, new_model) = if let Some(idx) = input.find('/') {
                                    (input[..idx].to_string(), Some(input[idx + 1..].to_string()))
                                } else if let Some(idx) = input.find(':') {
                                    (input[..idx].to_string(), Some(input[idx + 1..].to_string()))
                                } else {
                                    (app.provider.clone(), Some(input))
                                };
                                app.provider = new_provider;
                                app.model = new_model;
                                let full = format!("{}/{}", app.provider, app.model.as_deref().unwrap_or("default"));
                                if !app.model_picker_list.contains(&full) {
                                    app.model_picker_list.push(full);
                                    model::save_model_list(&app.model_picker_list);
                                }
                                app.model_picker_input.clear();
                                app.active_modal = None;
                            } else {
                                // Select the highlighted item from list
                                let filtered = model_filtered_indices(app);
                                if let Some(&idx) = filtered.get(app.model_picker_index) {
                                    let model_str = app.model_picker_list.get(idx).cloned();
                                    if let Some(model_str) = model_str {
                                        let (new_provider, new_model) = if let Some(i) = model_str.find('/') {
                                            (model_str[..i].to_string(), Some(model_str[i + 1..].to_string()))
                                        } else if let Some(i) = model_str.find(':') {
                                            (model_str[..i].to_string(), Some(model_str[i + 1..].to_string()))
                                        } else {
                                            (app.provider.clone(), Some(model_str))
                                        };
                                        app.provider = new_provider;
                                        app.model = new_model;
                                    }
                                }
                                app.model_picker_input.clear();
                                app.active_modal = None;
                            }
                            return;
                        }
                        KeyCode::Up => {
                            if app.model_picker_index > 0 {
                                app.model_picker_index -= 1;
                            }
                            return;
                        }
                        KeyCode::Down => {
                            let filtered = model_filtered_indices(app);
                            if app.model_picker_index < filtered.len().saturating_sub(1) {
                                app.model_picker_index += 1;
                            }
                            return;
                        }
                        KeyCode::Backspace | KeyCode::Delete => {
                            if app.model_picker_input.is_empty() {
                                // Remove highlighted model from saved list
                                let filtered = model_filtered_indices(app);
                                if let Some(&idx) = filtered.get(app.model_picker_index) {
                                    if app.model_picker_list.len() > idx {
                                        let removed = app.model_picker_list.remove(idx);
                                        model::save_model_list(&app.model_picker_list);
                                        app.add_system_message(format!("Removed model: {}", removed));
                                        if app.model_picker_index > 0 {
                                            app.model_picker_index -= 1;
                                        }
                                    }
                                }
                            } else {
                                app.model_picker_input.pop();
                                app.model_picker_index = 0;
                            }
                            return;
                        }
                        KeyCode::Char('d') if app.model_picker_input.is_empty() => {
                            // 'd' key also deletes when input is empty (same as memory editor)
                            let filtered = model_filtered_indices(app);
                            if let Some(&idx) = filtered.get(app.model_picker_index) {
                                if app.model_picker_list.len() > idx {
                                    let removed = app.model_picker_list.remove(idx);
                                    model::save_model_list(&app.model_picker_list);
                                    app.add_system_message(format!("Removed model: {}", removed));
                                    if app.model_picker_index > 0 {
                                        app.model_picker_index -= 1;
                                    }
                                }
                            }
                            return;
                        }
                        KeyCode::Char(c) => {
                            app.model_picker_input.push(c);
                            app.model_picker_index = 0; // reset selection on type
                            return;
                        }
                        _ => return,
                    }
                }

                // ProviderPicker — input field for custom URL + quick-select list
                if matches!(app.active_modal, Some(AppModal::ProviderPicker)) {
                    match key.code {
                        KeyCode::Esc | KeyCode::Char('q') => {
                            app.provider_picker_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.provider_picker_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Up | KeyCode::Char('k') => {
                            if app.provider_picker_index > 0 {
                                app.provider_picker_index -= 1;
                            }
                            return;
                        }
                        KeyCode::Down | KeyCode::Char('j') => {
                            let max = 1usize; // openai(0), ollama(1) = max index 1
                            if app.provider_picker_index < max {
                                app.provider_picker_index += 1;
                            }
                            return;
                        }
                        KeyCode::Enter => {
                            if !app.provider_picker_input.is_empty() {
                                // Use typed custom URL/name as provider
                                let name = app.provider_picker_input.trim().to_string();
                                app.provider = name.clone();
                                app.add_system_message(format!("Provider: {}", name));
                            } else {
                                // Use selected quick-pick
                                let providers = ["openai", "ollama"];
                                if let Some(&name) = providers.get(app.provider_picker_index) {
                                    app.provider = name.to_string();
                                    app.add_system_message(format!("Provider: {}", name));
                                }
                            }
                            app.provider_picker_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Backspace | KeyCode::Delete => {
                            app.provider_picker_input.pop();
                            return;
                        }
                        KeyCode::Char(c) => {
                            app.provider_picker_input.push(c);
                            return;
                        }
                        _ => return,
                    }
                }

                // MemoryEditor — text input to add, d to delete, arrows to navigate
                if matches!(app.active_modal, Some(AppModal::MemoryEditor)) {
                    match key.code {
                        KeyCode::Esc | KeyCode::Char('q') => {
                            app.memory_editor_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.memory_editor_input.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Up => {
                            if app.memory_editor_index > 0 {
                                app.memory_editor_index -= 1;
                            }
                            return;
                        }
                        KeyCode::Down => {
                            if app.memory_editor_index < app.memory_entries.len().saturating_sub(1) {
                                app.memory_editor_index += 1;
                            }
                            return;
                        }
                        KeyCode::Enter => {
                            if !app.memory_editor_input.is_empty() {
                                let text = app.memory_editor_input.clone();
                                let _ = app.bridge.memory_add("memory", &text).await;
                                app.memory_entries.push(("memory".to_string(), text));
                                app.memory_editor_input.clear();
                            }
                            return;
                        }
                        KeyCode::Char('d') => {
                            if app.memory_editor_input.is_empty() {
                                if let Some((target, content)) = app.memory_entries.get(app.memory_editor_index).cloned() {
                                    let _ = app.bridge.memory_remove(&target, &content).await;
                                    app.memory_entries.remove(app.memory_editor_index);
                                    if app.memory_editor_index > 0 {
                                        app.memory_editor_index -= 1;
                                    }
                                }
                            } else {
                                app.memory_editor_input.push('d');
                            }
                            return;
                        }
                        KeyCode::Backspace => {
                            app.memory_editor_input.pop();
                            return;
                        }
                        KeyCode::Char(c) => {
                            if c != 'd' || !app.memory_editor_input.is_empty() {
                                app.memory_editor_input.push(c);
                            }
                            return;
                        }
                        _ => return,
                    }
                }

                // SoulEditor — text input to modify personality, Ctrl+R to reset
                if matches!(app.active_modal, Some(AppModal::SoulEditor)) {
                    match key.code {
                        KeyCode::Esc | KeyCode::Char('q') => {
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            let _ = app.bridge.reset_soul().await;
                            app.soul_editor_input = DEFAULT_SOUL.to_string();
                            app.add_system_message("Personality reset to default.".into());
                            return;
                        }
                        KeyCode::Enter => {
                            let text = app.soul_editor_input.trim().to_string();
                            if !text.is_empty() {
                                let _ = app.bridge.set_soul(&text).await;
                                app.add_system_message("Personality updated.".into());
                            }
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Backspace | KeyCode::Delete => {
                            app.soul_editor_input.pop();
                            return;
                        }
                        KeyCode::Char(c) => {
                            app.soul_editor_input.push(c);
                            return;
                        }
                        _ => return,
                    }
                }

                // SkillBrowser — interactive hub skill browsing with filter + install
                if matches!(app.active_modal, Some(AppModal::SkillBrowser)) {
                    let query = app.skill_browser_filter.to_lowercase();
                    let filtered_count = app
                        .skill_browser_skills
                        .iter()
                        .filter(|s| {
                            if query.is_empty() { return true; }
                            let searchable = format!("{} {} {} {}", s.name, s.description, s.category, s.author).to_lowercase();
                            searchable.contains(&query)
                        })
                        .count();

                    match key.code {
                        KeyCode::Esc | KeyCode::Char('q') => {
                            app.skill_browser_filter.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.skill_browser_filter.clear();
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Down | KeyCode::Char('j') | KeyCode::Tab => {
                            if app.skill_browser_selected < filtered_count.saturating_sub(1) {
                                app.skill_browser_selected += 1;
                                let vr = app.skill_browser_visible_rows.saturating_sub(1);
                                let max_scroll = (app.skill_browser_selected as u16).saturating_sub(vr);
                                if app.skill_browser_scroll < max_scroll {
                                    app.skill_browser_scroll = max_scroll;
                                }
                            }
                            return;
                        }
                        KeyCode::Up | KeyCode::Char('k') => {
                            if app.skill_browser_selected > 0 {
                                app.skill_browser_selected -= 1;
                                if app.skill_browser_selected < app.skill_browser_scroll as usize {
                                    app.skill_browser_scroll = app.skill_browser_selected as u16;
                                }
                            }
                            return;
                        }
                        KeyCode::PageDown => {
                            let jump = 5.min(filtered_count.saturating_sub(1));
                            app.skill_browser_selected = (app.skill_browser_selected + jump).min(filtered_count.saturating_sub(1));
                            let vr = app.skill_browser_visible_rows.saturating_sub(1);
                            let max_scroll = (app.skill_browser_selected as u16).saturating_sub(vr);
                            if app.skill_browser_scroll < max_scroll {
                                app.skill_browser_scroll = max_scroll;
                            }
                            return;
                        }
                        KeyCode::PageUp => {
                            let jump = 5.min(app.skill_browser_selected);
                            app.skill_browser_selected -= jump;
                            if app.skill_browser_selected < app.skill_browser_scroll as usize {
                                app.skill_browser_scroll = app.skill_browser_selected as u16;
                            }
                            return;
                        }
                        KeyCode::Enter => {
                            // Install the selected skill
                            let q = app.skill_browser_filter.to_lowercase();
                            let filtered: Vec<&sediman_tui_bridge::HubSkill> = app
                                .skill_browser_skills
                                .iter()
                                .filter(|s| {
                                    if q.is_empty() { return true; }
                                    let searchable = format!("{} {} {} {}", s.name, s.description, s.category, s.author).to_lowercase();
                                    searchable.contains(&q)
                                })
                                .collect();
                            if let Some(skill) = filtered.get(app.skill_browser_selected) {
                                let name = skill.name.clone();
                                app.add_system_message(format!("Installing {} from hub...", name));
                                match app.bridge.hub_install(&name, false).await {
                                    Ok(()) => {
                                        app.add_system_message(format!("Installed {}", name));
                                        if !app.skill_browser_installed.contains(&name) {
                                            app.skill_browser_installed.push(name);
                                        }
                                    }
                                    Err(e) => {
                                        app.add_error_message(format!("Install failed: {}", e));
                                    }
                                }
                            }
                            return;
                        }
                        KeyCode::Char('i') => {
                            let q = app.skill_browser_filter.to_lowercase();
                            let filtered: Vec<&sediman_tui_bridge::HubSkill> = app
                                .skill_browser_skills
                                .iter()
                                .filter(|s| {
                                    if q.is_empty() { return true; }
                                    let searchable = format!("{} {} {} {}", s.name, s.description, s.category, s.author).to_lowercase();
                                    searchable.contains(&q)
                                })
                                .collect();
                            if let Some(skill) = filtered.get(app.skill_browser_selected) {
                                let name = skill.name.clone();
                                app.skill_browser_filter.clear();
                                app.active_modal = None;
                                super::commands::hub::handle_hub_info(app, &name).await;
                            }
                            return;
                        }
                        KeyCode::Char('d') => {
                            let q = app.skill_browser_filter.to_lowercase();
                            let filtered: Vec<&sediman_tui_bridge::HubSkill> = app
                                .skill_browser_skills
                                .iter()
                                .filter(|s| {
                                    if q.is_empty() { return true; }
                                    let searchable = format!("{} {} {} {}", s.name, s.description, s.category, s.author).to_lowercase();
                                    searchable.contains(&q)
                                })
                                .collect();
                            if let Some(skill) = filtered.get(app.skill_browser_selected) {
                                let name = skill.name.clone();
                                if app.skill_browser_installed.contains(&name) {
                                    app.add_system_message(format!("Uninstalling {}...", name));
                                    match app.bridge.delete_skill(&name).await {
                                        Ok(()) => {
                                            app.skill_browser_installed.retain(|n| n != &name);
                                            app.add_system_message(format!("Uninstalled {}", name));
                                        }
                                        Err(e) => {
                                            app.add_error_message(format!("Uninstall failed: {}", e));
                                        }
                                    }
                                } else {
                                    app.add_error_message(format!("{} is not installed", name));
                                }
                            }
                            return;
                        }
                        KeyCode::Backspace | KeyCode::Delete => {
                            app.skill_browser_filter.pop();
                            app.skill_browser_selected = 0;
                            app.skill_browser_scroll = 0;
                            return;
                        }
                        KeyCode::Char(c) => {
                            app.skill_browser_filter.push(c);
                            app.skill_browser_selected = 0;
                            app.skill_browser_scroll = 0;
                            return;
                        }
                        _ => return,
                    }
                }

                // Help / Info modal handling — vim-style navigation
                match key.code {
                    KeyCode::Char('q') | KeyCode::Esc => {
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Down | KeyCode::Char('j') => {
                        if let Some(AppModal::Info { scroll, .. }) = &mut app.active_modal {
                            *scroll = scroll.saturating_add(1);
                        }
                        return;
                    }
                    KeyCode::Up | KeyCode::Char('k') => {
                        if let Some(AppModal::Info { scroll, .. }) = &mut app.active_modal {
                            *scroll = scroll.saturating_sub(1);
                        }
                        return;
                    }
                    KeyCode::PageDown => {
                        if let Some(AppModal::Info { scroll, .. }) = &mut app.active_modal {
                            *scroll = scroll.saturating_add(10);
                        }
                        return;
                    }
                    KeyCode::PageUp => {
                        if let Some(AppModal::Info { scroll, .. }) = &mut app.active_modal {
                            *scroll = scroll.saturating_sub(10);
                        }
                        return;
                    }
                    KeyCode::Enter => {
                        app.active_modal = None;
                        return;
                    }
                    _ => return,
                }
            }

            match key.code {
                KeyCode::Esc => {
                    if app.agent_running {
                        app.interrupt.trigger();
                        app.agent_running = false;
                        app.append_step("-- Interrupted --".to_string());
                    } else {
                        app.editor.delete_line_by_head();
                    }
                }
                KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    // OpenCode-style: Ctrl+C clears input or cancels agent
                    if app.agent_running {
                        app.interrupt.trigger();
                        app.agent_running = false;
                        app.append_step("-- Cancelled --".to_string());
                    } else {
                        app.editor.delete_line_by_head();
                    }
                }
                // Ctrl+/ toggles help (same as OpenCode's ctrl+?)
                KeyCode::Char('/') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if matches!(app.active_modal, Some(AppModal::Help)) {
                        app.active_modal = None;
                    } else {
                        app.active_modal = Some(AppModal::Help);
                    }
                }
                // Keep Ctrl+P as alias for help toggle
                KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if matches!(app.active_modal, Some(AppModal::Help)) {
                        app.active_modal = None;
                    } else {
                        app.active_modal = Some(AppModal::Help);
                    }
                }
                KeyCode::Enter => {
                    // Ctrl+Enter or Shift+Enter → newline in editor
                    // Plain Enter → submit
                    let has_modifier = key.modifiers.contains(KeyModifiers::SHIFT)
                        || key.modifiers.contains(KeyModifiers::CONTROL);
                    if has_modifier {
                        app.editor.input(key);
                    } else {
                        let input = app.editor.submit();
                        if !input.is_empty() {
                            if input.starts_with('/') {
                                // Slash commands always work, even while agent is running
                                handle_slash(app, &input).await;
                            } else if let Some(cmd) = input.strip_prefix('!') {
                                handle_shell(app, cmd).await;
                            } else if app.agent_running {
                                // Queue non-slash text as a follow-up message
                                app.add_system_message("Agent is busy. Queued.".into());
                            } else {
                                handle_task(app, &input, event_tx).await;
                            }
                        }
                    }
                }
                KeyCode::Tab => {
                    let prefix = app.editor.lines().join(" ").trim().to_string();
                    if prefix.starts_with('/') {
                        app.completer.complete(&prefix);
                        if let Some(cmd) = app.completer.next() {
                            app.editor.delete_line_by_head();
                            app.editor.insert_str(&cmd);
                        }
                    } else if let Some(cmd) = app.command_registry.find_fuzzy(&prefix) {
                        app.editor.delete_line_by_head();
                        app.editor.insert_str(cmd.name);
                    }
                }
                KeyCode::Up => {
                    if key.modifiers.contains(KeyModifiers::SHIFT) {
                        scroll_up(app, 3);
                    } else {
                        app.editor.history_up();
                    }
                }
                KeyCode::Down => {
                    if key.modifiers.contains(KeyModifiers::SHIFT) {
                        scroll_down(app, 3);
                    } else {
                        app.editor.history_down();
                    }
                }
                KeyCode::PageUp => {
                    scroll_up(app, 20);
                }
                KeyCode::PageDown => {
                    scroll_down(app, 20);
                }
                KeyCode::BackTab => {
                    app.permission.cycle();
                    app.add_system_message(format!("Mode: {}", app.permission.current_label()));
                }
                _ => {
                    app.editor.input(key);
                    // Update completer on every key press when typing a slash command
                    let current = app.editor.lines().join(" ").trim().to_string();
                    if current.starts_with('/') {
                        app.completer.complete(&current);
                    } else {
                        app.completer.complete(""); // clears filtered list
                    }
                }
            }
        }
        AppEvent::Mouse(mouse) => {
            use crossterm::event::MouseEventKind;
            match mouse.kind {
                MouseEventKind::ScrollUp => scroll_up(app, 3),
                MouseEventKind::ScrollDown => scroll_down(app, 3),
                _ => {}
            }
        }
        AppEvent::Tick => {
            if app.agent_running {
                app.advance_spinner();
            }
        }
        AppEvent::Resize(w, h) => {
            app.pending_resize = Some((w, h));
        }
        AppEvent::Paste(text) => {
            app.editor.insert_str(&text);
        }
        AppEvent::Shutdown => {
            app.running = false;
        }
        AppEvent::AgentStep(_phase, action) => {
            app.append_step(action);
        }
        AppEvent::AgentResult(success, result_text, elapsed_secs) => {
            let skill_created = None;
            let scheduled_job = None;
            app.complete_agent_message(success, result_text, elapsed_secs, skill_created, scheduled_job);
        }
        AppEvent::AgentError(err) => {
            app.agent_running = false;
            app.add_error_message(format!("Error: {}", err));
        }
        AppEvent::AgentDone => {
            app.agent_running = false;
        }
        AppEvent::CommandOutput(text) => {
            app.add_system_message(text);
        }
        AppEvent::StreamingToken(token, phase) => {
            app.append_streaming_token(&token, &phase);
        }
    }
}

fn scroll_up(app: &mut App, amount: u16) {
    app.scroll_offset = app.scroll_offset.saturating_sub(amount);
    app.auto_scroll = false;
}

/// Compute filtered model indices based on the picker input text.
fn model_filtered_indices(app: &App) -> Vec<usize> {
    let query = app.model_picker_input.to_lowercase();
    app.model_picker_list
        .iter()
        .enumerate()
        .filter(|(_, m)| query.is_empty() || m.to_lowercase().contains(&query))
        .map(|(i, _)| i)
        .collect()
}

fn scroll_down(app: &mut App, amount: u16) {
    app.scroll_offset = app.scroll_offset.saturating_add(amount);
    app.auto_scroll = false;
}

async fn handle_slash(app: &mut App, input: &str) {
    let input = input.trim();
    let (cmd_name, args) = parse_command(input);

    match cmd_name {
        "/help" | "/h" | "/?" => system::handle_help(app, args).await,
        "/exit" | "/quit" | "/q" => system::handle_exit(app, args).await,
        "/clear" => system::handle_clear(app, args).await,
        "/reset" => system::handle_reset(app, args).await,
        "/compress" => system::handle_compress(app, args).await,
        "/status" => {
            system::handle_status(app, args).await;
            refresh_sidebar(app).await;
        }
        "/skills" | "/skill" => {
            skills::handle_skills(app, args).await;
            refresh_sidebar(app).await;
        }
        "/run-skill" => skills::handle_run_skill(app, args).await,
        "/hub" => {
            let (sub_cmd, sub_args) = parse_command(args);
            match sub_cmd {
                "browse" => hub::handle_hub_browse(app, sub_args).await,
                "search" => hub::handle_hub_search(app, sub_args).await,
                "install" => hub::handle_hub_install(app, sub_args).await,
                "install-github" => hub::handle_hub_install_github(app, sub_args).await,
                "info" => hub::handle_hub_info(app, sub_args).await,
                "publish" => hub::handle_hub_publish(app, sub_args).await,
                "update" => hub::handle_hub_update(app, sub_args).await,
                "remove" => hub::handle_hub_remove(app, sub_args).await,
                "check-update" => hub::handle_hub_check_update(app, sub_args).await,
                _ => {
                    app.active_modal = Some(AppModal::Info {
                        title: "Hub".into(),
                        lines: vec![
                            crate::app::ModalLine::blank(),
                            crate::app::ModalLine::muted("  /hub browse            Browse skills"),
                            crate::app::ModalLine::muted("  /hub search <query>    Search skills"),
                            crate::app::ModalLine::muted("  /hub install <name>    Install a skill"),
                            crate::app::ModalLine::muted("  /hub info <name>       Show skill details"),
                            crate::app::ModalLine::muted("  /hub update <name>     Update a skill"),
                            crate::app::ModalLine::muted("  /hub remove <name>     Remove a skill"),
                            crate::app::ModalLine::muted("  /hub check-update <n>  Check for updates"),
                            crate::app::ModalLine::muted("  /hub publish <name>    Publish a skill"),
                        ],
                        scroll: 0,
                    });
                }
            }
        }
        "/memory" => {
            memory::handle_memory(app, args).await;
            refresh_sidebar(app).await;
        }
        "/remember" => memory::handle_remember(app, args).await,
        "/model" | "/models" => model::handle_model(app, args).await,
        "/provider" => provider::handle_provider(app, args).await,
        "/schedule" => {
            schedule::handle_schedule(app, args).await;
            refresh_sidebar(app).await;
        }
        "/schedule-add" => schedule::handle_schedule_add(app, args).await,
        "/schedule-remove" => schedule::handle_schedule_remove(app, args).await,
        "/sessions" => sessions::handle_sessions(app, args).await,
        "/resume" => sessions::handle_resume(app, args).await,
        "/browser" => browser::handle_browser(app, args).await,
        "/screenshot" => browser::handle_screenshot(app, args).await,
        "/record" => record::handle_record(app, args).await,
        "/stop" => record::handle_stop(app, args).await,
        "/delegate" => delegate::handle_delegate(app, args).await,
        "/parallel" => delegate::handle_parallel(app, args).await,
        "/terminal" => terminal::handle_terminal(app, args).await,
        "/plan" => plan::handle_plan(app, args).await,
        "/soul" => soul::handle_soul(app, args).await,
        "/usage" => misc::handle_usage(app, args).await,
        "/doctor" => misc::handle_doctor(app, args).await,
        "/export" => misc::handle_export(app, args).await,
        "/btw" => misc::handle_btw(app, args).await,
        "/color" => misc::handle_color(app, args).await,
        "/rename" => misc::handle_rename(app, args).await,
        "/themes" | "/theme" => theming::handle_themes(app, args).await,
        _ => {
            app.add_system_message(format!("Unknown command: {}. Type /help", cmd_name));
        }
    }
}

async fn refresh_sidebar(app: &mut App) {
    if let Ok(skills) = app.bridge.call_with_retry::<Vec<sediman_tui_bridge::SkillSummary>>("skills.list", serde_json::json!({}), 2).await {
        app.skills_cache = skills.iter().map(|s| {
            format!("{}: {}", s.name, s.description.chars().take(40).collect::<String>())
        }).collect();
    }

    if let Ok(mem) = app.bridge.call_with_retry::<sediman_tui_bridge::MemoryData>("memory.get", serde_json::json!({}), 2).await {
        let mut lines = Vec::new();
        if !mem.memory.is_empty() {
            lines.push(format!("Mem: {} chars", mem.memory.chars().count()));
        }
        if !mem.user.is_empty() {
            lines.push(format!("User: {} chars", mem.user.chars().count()));
        }
        app.memory_cache = lines;
    }

    // Populate schedule cache
    if let Ok(jobs) = app.bridge.call_with_retry::<Vec<sediman_tui_bridge::CronJob>>("schedule.list", serde_json::json!({}), 2).await {
        app.schedule_cache = jobs.iter().map(|j| {
            format!("{}: {}", j.cron_expr, j.task.chars().take(35).collect::<String>())
        }).collect();
    }
}

fn parse_command(input: &str) -> (&str, &str) {
    let mut parts = input.splitn(2, char::is_whitespace);
    let cmd = parts.next().unwrap_or("");
    let args = parts.next().unwrap_or("");
    (cmd, args.trim())
}

async fn handle_shell(app: &mut App, cmd: &str) {
    if !app.permission.is_allowed(cmd) {
        app.add_system_message("Shell command denied by permission mode".into());
        return;
    }
    app.add_system_message(format!("$ {}", cmd));
    crate::shell::run_shell_command(app, cmd).await;
}

pub async fn handle_task(app: &mut App, task: &str, event_tx: &mpsc::UnboundedSender<AppEvent>) {
    app.show_banner = false;
    app.task_count += 1;
    app.agent_running = true;
    app.agent_start = std::time::Instant::now();
    app.spinner_text = "Working...".to_string();
    app.interrupt.clear();

    app.add_user_message(task.to_string(), app.task_count);
    app.start_agent_message(task);

    let bridge_url = app.bridge_url().to_string();
    let task_owned = task.to_string();
    let tx = event_tx.clone();
    let interrupt_flag = app.interrupt.flag().clone();
    let start = std::time::Instant::now();

    tokio::spawn(async move {
        let result = run_agent_task_inner(&bridge_url, &task_owned, &tx, &interrupt_flag).await;
        let elapsed = start.elapsed().as_secs();
        match result {
            Ok(Some(agent_result)) => {
                let _ = tx.send(AppEvent::AgentResult(
                    agent_result.success,
                    agent_result.result.clone(),
                    elapsed,
                ));
                if agent_result.success {
                    let _ = tx.send(AppEvent::CommandOutput(format!(
                        "Done ({}s){}{}",
                        elapsed,
                        agent_result.skill_created
                            .as_ref()
                            .map(|s| format!(" - Skill: {}", s))
                            .unwrap_or_default(),
                        agent_result.scheduled_job_id
                            .as_ref()
                            .map(|s| format!(" - Job: {}", s))
                            .unwrap_or_default(),
                    )));
                }
            }
            Ok(None) => {
                let _ = tx.send(AppEvent::AgentError("No result received".into()));
            }
            Err(e) => {
                let _ = tx.send(AppEvent::AgentError(e.to_string()));
            }
        }
        let _ = tx.send(AppEvent::AgentDone);
    });
}

async fn run_agent_task_inner(
    bridge_url: &str,
    task: &str,
    tx: &mpsc::UnboundedSender<AppEvent>,
    interrupt_flag: &Arc<AtomicBool>,
) -> Result<Option<sediman_tui_bridge::AgentResult>, Box<dyn std::error::Error + Send + Sync>> {
    let mut stream = sediman_tui_bridge::agent::TaskStream::submit(bridge_url, task).await?;

    let mut final_result: Option<sediman_tui_bridge::AgentResult> = None;

    loop {
        if interrupt_flag.load(std::sync::atomic::Ordering::SeqCst) {
            stream.cancel();
            return Err("Interrupted by user".into());
        }

        tokio::select! {
            msg = stream.rx.recv() => {
                match msg {
                    Some(ws_msg) => {
                        match ws_msg.msg_type.as_str() {
                            "streaming" => {
                                if let Some(ref st) = ws_msg.streaming_token {
                                    let _ = tx.send(AppEvent::StreamingToken(st.token.clone(), st.phase.clone()));
                                }
                            }
                            "step" => {
                                if let Some(ref event) = ws_msg.event {
                                    let phase = event.phase.clone();
                                    let action = event.action.clone();
                                    let mut step_line = format!("{} {}", phase, action);
                                    if let Some(ref url) = event.url {
                                        step_line.push_str(&format!(" ({})", url));
                                    }
                                    if let Some(ref detail) = event.detail {
                                        step_line.push_str(&format!("\n  {}", detail));
                                    }
                                    let _ = tx.send(AppEvent::AgentStep(phase, step_line));
                                }
                            }
                            "result" => {
                                final_result = ws_msg.result;
                                break;
                            }
                            "error" => {
                                let err = ws_msg.error.unwrap_or("Unknown error".into());
                                return Err(err.into());
                            }
                            _ => {}
                        }
                    }
                    None => break,
                }
            }
            _ = tokio::time::sleep(std::time::Duration::from_millis(100)) => {
                if interrupt_flag.load(std::sync::atomic::Ordering::SeqCst) {
                    stream.cancel();
                    return Err("Interrupted by user".into());
                }
            }
        }
    }

    Ok(final_result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sediman_tui_bridge::ApiClient;
    use crate::app::ChatMessage;

    fn test_app() -> App {
        App::new("test".into(), Some("gpt-4".into()), None, true, ApiClient::new("/tmp/test.sock"))
    }

    fn test_tx() -> mpsc::UnboundedSender<AppEvent> {
        mpsc::unbounded_channel().0
    }

    #[test]
    fn test_parse_command_simple() {
        assert_eq!(parse_command("/help"), ("/help", ""));
    }

    #[test]
    fn test_parse_command_with_args() {
        assert_eq!(parse_command("/model openai:gpt-4"), ("/model", "openai:gpt-4"));
    }

    #[test]
    fn test_parse_command_multiple_spaces() {
        assert_eq!(parse_command("/hub   browse   foo"), ("/hub", "browse   foo"));
    }

    #[test]
    fn test_parse_command_empty() {
        assert_eq!(parse_command(""), ("", ""));
    }

    #[test]
    fn test_parse_command_trailing_space() {
        assert_eq!(parse_command("/help  "), ("/help", ""));
    }

    #[test]
    fn test_parse_command_single_word_no_args() {
        assert_eq!(parse_command("/exit"), ("/exit", ""));
    }

    #[tokio::test]
    async fn test_scroll_up_decreases_offset() {
        let mut app = test_app();
        app.scroll_offset = 10;
        scroll_up(&mut app, 5);
        assert_eq!(app.scroll_offset, 5);
        assert!(!app.auto_scroll);
    }

    #[tokio::test]
    async fn test_scroll_up_saturating_at_zero() {
        let mut app = test_app();
        app.scroll_offset = 3;
        scroll_up(&mut app, 10);
        assert_eq!(app.scroll_offset, 0);
    }

    #[tokio::test]
    async fn test_scroll_down_increases_offset() {
        let mut app = test_app();
        app.scroll_offset = 0;
        scroll_down(&mut app, 5);
        assert_eq!(app.scroll_offset, 5);
        assert!(!app.auto_scroll);
    }

    #[tokio::test]
    async fn test_scroll_down_saturating() {
        let mut app = test_app();
        app.scroll_offset = u16::MAX - 1;
        scroll_down(&mut app, 10);
        assert_eq!(app.scroll_offset, u16::MAX);
    }

    #[tokio::test]
    async fn test_handle_slash_help() {
        let mut app = test_app();
        handle_slash(&mut app, "/help").await;
        assert!(app.active_modal.is_some());
    }

    #[tokio::test]
    async fn test_handle_slash_exit() {
        let mut app = test_app();
        handle_slash(&mut app, "/exit").await;
        assert!(!app.running);
    }

    #[tokio::test]
    async fn test_handle_slash_quit_alias() {
        let mut app = test_app();
        handle_slash(&mut app, "/quit").await;
        assert!(!app.running);
    }

    #[tokio::test]
    async fn test_handle_slash_q_alias() {
        let mut app = test_app();
        handle_slash(&mut app, "/q").await;
        assert!(!app.running);
    }

    #[tokio::test]
    async fn test_handle_slash_clear() {
        let mut app = test_app();
        app.add_system_message("msg".into());
        app.step_log.push("step".into());
        handle_slash(&mut app, "/clear").await;
        let has_user_msgs = app.messages.iter().any(|m| !matches!(m, ChatMessage::System { .. }));
        assert!(!has_user_msgs);
        assert!(app.step_log.is_empty());
    }

    #[tokio::test]
    async fn test_handle_slash_reset() {
        let mut app = test_app();
        app.task_count = 5;
        app.add_system_message("msg".into());
        app.show_banner = false;
        handle_slash(&mut app, "/reset").await;
        assert_eq!(app.task_count, 0);
        assert!(app.show_banner);
        assert_eq!(app.scroll_offset, 0);
    }

    #[tokio::test]
    async fn test_handle_slash_unknown() {
        let mut app = test_app();
        handle_slash(&mut app, "/nonexistent").await;
        let has_unknown = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Unknown command")));
        assert!(has_unknown);
    }

    #[tokio::test]
    async fn test_handle_slash_color_valid() {
        let mut app = test_app();
        handle_slash(&mut app, "/color red").await;
        assert_eq!(app.session_color.as_deref(), Some("red"));
    }

    #[tokio::test]
    async fn test_handle_slash_color_default_clears() {
        let mut app = test_app();
        app.session_color = Some("red".into());
        handle_slash(&mut app, "/color default").await;
        assert!(app.session_color.is_none());
    }

    #[tokio::test]
    async fn test_handle_slash_color_invalid() {
        let mut app = test_app();
        handle_slash(&mut app, "/color magenta_fuchsia").await;
        assert!(app.session_color.is_none());
        let has_err = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Unknown color")));
        assert!(has_err);
    }

    #[tokio::test]
    async fn test_handle_slash_rename() {
        let mut app = test_app();
        handle_slash(&mut app, "/rename my session").await;
        assert_eq!(app.session_name.as_deref(), Some("my session"));
    }

    #[tokio::test]
    async fn test_handle_slash_rename_truncates_to_30() {
        let mut app = test_app();
        let long_name = "a".repeat(50);
        handle_slash(&mut app, &format!("/rename {}", long_name)).await;
        assert_eq!(app.session_name.as_ref().unwrap().len(), 30);
    }

    #[tokio::test]
    async fn test_handle_slash_rename_empty_shows_current() {
        let mut app = test_app();
        handle_slash(&mut app, "/rename ").await;
        assert!(app.session_name.is_none());
        let has_unnamed = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("(unnamed)")));
        assert!(has_unnamed);
    }

    #[tokio::test]
    async fn test_handle_slash_browser_headless() {
        let mut app = test_app();
        app.headless = false;
        handle_slash(&mut app, "/browser headless").await;
        assert!(app.headless);
    }

    #[tokio::test]
    async fn test_handle_slash_browser_headed() {
        let mut app = test_app();
        app.headless = true;
        handle_slash(&mut app, "/browser headed").await;
        assert!(!app.headless);
    }

    #[tokio::test]
    async fn test_handle_slash_browser_invalid() {
        let mut app = test_app();
        let prev = app.headless;
        handle_slash(&mut app, "/browser foobar").await;
        assert_eq!(app.headless, prev);
    }

    #[tokio::test]
    async fn test_handle_slash_delegate_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/delegate").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_parallel_too_many() {
        let mut app = test_app();
        handle_slash(&mut app, "/parallel a | b | c | d | e | f").await;
        let has_max = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Max 5")));
        assert!(has_max);
    }

    #[tokio::test]
    async fn test_handle_slash_parallel_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/parallel").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_parallel_pipes_only() {
        let mut app = test_app();
        handle_slash(&mut app, "/parallel  |  |  ").await;
        let has_empty = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("No tasks")));
        assert!(has_empty);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_no_subcommand() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub").await;
        // /hub without subcommand now shows a modal instead of chat message
        assert!(app.active_modal.is_some());
    }

    #[tokio::test]
    async fn test_handle_slash_btw_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/btw").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_btw_with_question() {
        let mut app = test_app();
        handle_slash(&mut app, "/btw what is 2+2").await;
        let has_q = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Side question")));
        assert!(has_q);
    }

    #[tokio::test]
    async fn test_handle_slash_compress_keeps_recent() {
        let mut app = test_app();
        for i in 0..25 {
            app.add_system_message(format!("msg {}", i));
        }
        handle_slash(&mut app, "/compress").await;
        let has_compress_msg = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("compressed")));
        assert!(has_compress_msg);
        assert!(app.messages.len() <= 22);
    }

    #[tokio::test]
    async fn test_handle_slash_plan_toggles() {
        let mut app = test_app();
        let was_plan = app.permission.is_plan_mode();
        handle_slash(&mut app, "/plan").await;
        assert_ne!(was_plan, app.permission.is_plan_mode());
        handle_slash(&mut app, "/plan").await;
        assert_eq!(was_plan, app.permission.is_plan_mode());
    }

    #[tokio::test]
    async fn test_handle_slash_terminal_empty_shows_status() {
        let mut app = test_app();
        handle_slash(&mut app, "/terminal").await;
        let has_status = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Terminal access")));
        assert!(has_status);
    }

    #[tokio::test]
    async fn test_handle_slash_terminal_invalid() {
        let mut app = test_app();
        handle_slash(&mut app, "/terminal maybe").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_message_tick() {
        let mut app = test_app();
        app.agent_running = true;
        app.agent_start = std::time::Instant::now();
        let tx = test_tx();
        handle_message(&mut app, AppEvent::Tick, &tx).await;
    }

    #[tokio::test]
    async fn test_handle_message_agent_step() {
        let mut app = test_app();
        app.start_agent_message("task");
        let tx = test_tx();
        let step_line = "planning reading code".to_string();
        handle_message(&mut app, AppEvent::AgentStep("planning".into(), step_line), &tx).await;
        let msg = &app.messages[0];
        assert!(matches!(msg, ChatMessage::Agent { .. }), "Expected Agent message, got {:?}", msg);
        if let ChatMessage::Agent { steps, .. } = msg {
            assert_eq!(steps.len(), 1);
            assert!(steps[0].contains("planning"));
            assert!(steps[0].contains("reading code"));
        }
    }

    #[tokio::test]
    async fn test_handle_message_agent_result() {
        let mut app = test_app();
        app.agent_running = true;
        app.start_agent_message("task");
        let tx = test_tx();
        handle_message(&mut app, AppEvent::AgentResult(true, "done".into(), 10), &tx).await;
        assert!(!app.agent_running);
        let msg = &app.messages[0];
        assert!(matches!(msg, ChatMessage::Agent { .. }), "Expected Agent message, got {:?}", msg);
        if let ChatMessage::Agent { result, success, elapsed_secs, .. } = msg {
            assert_eq!(result.as_deref(), Some("done"));
            assert!(*success);
            assert_eq!(*elapsed_secs, 10);
        }
    }

    #[tokio::test]
    async fn test_handle_message_agent_error() {
        let mut app = test_app();
        app.agent_running = true;
        let tx = test_tx();
        handle_message(&mut app, AppEvent::AgentError("timeout".into()), &tx).await;
        assert!(!app.agent_running);
        let has_err = app.messages.iter().any(|m| matches!(m, ChatMessage::Error { text } if text.contains("timeout")));
        assert!(has_err);
    }

    #[tokio::test]
    async fn test_handle_message_agent_done() {
        let mut app = test_app();
        app.agent_running = true;
        let tx = test_tx();
        handle_message(&mut app, AppEvent::AgentDone, &tx).await;
        assert!(!app.agent_running);
    }

    #[tokio::test]
    async fn test_handle_message_command_output() {
        let mut app = test_app();
        let tx = test_tx();
        handle_message(&mut app, AppEvent::CommandOutput("output text".into()), &tx).await;
        let has_msg = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text == "output text"));
        assert!(has_msg);
    }

    #[tokio::test]
    async fn test_handle_message_resize() {
        let mut app = test_app();
        let tx = test_tx();
        handle_message(&mut app, AppEvent::Resize(80, 24), &tx).await;
    }

    // ── SkillBrowser modal tests ──

    #[tokio::test]
    async fn test_skill_browser_esc_closes() {
        let mut app = test_app();
        app.skill_browser_skills = vec![sediman_tui_bridge::HubSkill {
            name: "test".into(), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }];
        app.skill_browser_filter = "foo".into();
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Esc, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert!(app.active_modal.is_none());
        assert!(app.skill_browser_filter.is_empty());
    }

    #[tokio::test]
    async fn test_skill_browser_down_moves_selection() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
            sediman_tui_bridge::HubSkill {
                name: "b".into(), description: "b".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        assert_eq!(app.skill_browser_selected, 0);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Down, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 1);
    }

    #[tokio::test]
    async fn test_skill_browser_up_does_not_underflow() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        assert_eq!(app.skill_browser_selected, 0);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Up, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 0);
    }

    #[tokio::test]
    async fn test_skill_browser_j_moves_down() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
            sediman_tui_bridge::HubSkill {
                name: "b".into(), description: "b".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
            sediman_tui_bridge::HubSkill {
                name: "c".into(), description: "c".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('j'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 1);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 2);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 2);
    }

    #[tokio::test]
    async fn test_skill_browser_k_moves_up() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
            sediman_tui_bridge::HubSkill {
                name: "b".into(), description: "b".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.skill_browser_selected = 1;
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('k'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 0);
    }

    #[tokio::test]
    async fn test_skill_browser_tab_moves_down() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
            sediman_tui_bridge::HubSkill {
                name: "b".into(), description: "b".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Tab, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 1);
    }

    #[tokio::test]
    async fn test_skill_browser_page_down() {
        let mut app = test_app();
        app.skill_browser_skills = (0..10).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::PageDown, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 5);
    }

    #[tokio::test]
    async fn test_skill_browser_page_up() {
        let mut app = test_app();
        app.skill_browser_skills = (0..10).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.skill_browser_selected = 7;
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::PageUp, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 2);
    }

    #[tokio::test]
    async fn test_skill_browser_typing_filters() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "google-search".into(), description: "Search Google".into(), category: "search".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
            sediman_tui_bridge::HubSkill {
                name: "web-scraper".into(), description: "Scrape websites".into(), category: "data".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('g'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_filter, "g");
        assert_eq!(app.skill_browser_selected, 0);
    }

    #[tokio::test]
    async fn test_skill_browser_backspace_removes_filter() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.skill_browser_filter = "abc".into();
        app.skill_browser_selected = 2;
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Backspace, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_filter, "ab");
        assert_eq!(app.skill_browser_selected, 0);
    }

    #[tokio::test]
    async fn test_skill_browser_ctrl_c_closes() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('c'), crossterm::event::KeyModifiers::CONTROL);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert!(app.active_modal.is_none());
    }

    #[tokio::test]
    async fn test_skill_browser_q_closes() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "a".into(), description: "a".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('q'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert!(app.active_modal.is_none());
    }

    #[tokio::test]
    async fn test_skill_browser_scroll_advances_on_down() {
        let mut app = test_app();
        app.skill_browser_skills = (0..50).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let down = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Down, crossterm::event::KeyModifiers::NONE);
        assert_eq!(app.skill_browser_scroll, 0);
        for _ in 0..15 {
            handle_message(&mut app, AppEvent::Key(down.clone()), &tx).await;
        }
        assert_eq!(app.skill_browser_selected, 15);
        assert!(app.skill_browser_scroll > 0, "scroll should have advanced past 0, got {}", app.skill_browser_scroll);
    }

    #[tokio::test]
    async fn test_skill_browser_scroll_retreats_on_up() {
        let mut app = test_app();
        app.skill_browser_skills = (0..50).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.skill_browser_selected = 20;
        app.skill_browser_scroll = 15;
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let up = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Up, crossterm::event::KeyModifiers::NONE);
        for _ in 0..5 {
            handle_message(&mut app, AppEvent::Key(up.clone()), &tx).await;
        }
        assert_eq!(app.skill_browser_selected, 15);
        assert!(app.skill_browser_scroll <= 15);
    }

    #[tokio::test]
    async fn test_skill_browser_scroll_resets_on_filter() {
        let mut app = test_app();
        app.skill_browser_skills = (0..50).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.skill_browser_selected = 30;
        app.skill_browser_scroll = 20;
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('s'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 0);
        assert_eq!(app.skill_browser_scroll, 0);
    }

    #[tokio::test]
    async fn test_skill_browser_scroll_resets_on_backspace() {
        let mut app = test_app();
        app.skill_browser_skills = (0..50).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.skill_browser_selected = 30;
        app.skill_browser_scroll = 20;
        app.skill_browser_filter = "abc".into();
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Backspace, crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        assert_eq!(app.skill_browser_selected, 0);
        assert_eq!(app.skill_browser_scroll, 0);
    }

    #[tokio::test]
    async fn test_skill_browser_page_down_scroll_advances() {
        let mut app = test_app();
        app.skill_browser_skills = (0..50).map(|i| sediman_tui_bridge::HubSkill {
            name: format!("skill-{}", i), description: "d".into(), category: "c".into(),
            author: "a".into(), version: 1, trust: "t".into(),
        }).collect();
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let pd = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::PageDown, crossterm::event::KeyModifiers::NONE);
        for _ in 0..3 {
            handle_message(&mut app, AppEvent::Key(pd.clone()), &tx).await;
        }
        assert!(app.skill_browser_selected > 10, "selected should be past 10 after 3 page downs");
        assert!(app.skill_browser_scroll > 0, "PageDown should advance scroll after enough pages");
    }

    #[tokio::test]
    async fn test_skill_browser_d_uninstall_not_installed() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "test-skill".into(), description: "d".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('d'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        let has_err = app.messages.iter().any(|m| matches!(m, ChatMessage::Error { text } if text.contains("not installed")));
        assert!(has_err);
    }

    #[tokio::test]
    async fn test_skill_browser_d_uninstall_installed() {
        let mut app = test_app();
        app.skill_browser_skills = vec![
            sediman_tui_bridge::HubSkill {
                name: "test-skill".into(), description: "d".into(), category: "c".into(),
                author: "a".into(), version: 1, trust: "t".into(),
            },
        ];
        app.skill_browser_installed = vec!["test-skill".into()];
        app.active_modal = Some(crate::app::AppModal::SkillBrowser);
        let tx = test_tx();
        let key = crossterm::event::KeyEvent::new(crossterm::event::KeyCode::Char('d'), crossterm::event::KeyModifiers::NONE);
        handle_message(&mut app, AppEvent::Key(key), &tx).await;
        let has_uninstall = app.messages.iter().any(|m| {
            matches!(m, ChatMessage::System { text } if text.contains("Uninstalling"))
        });
        assert!(has_uninstall);
    }

    // ── /skills search and /hub new subcommand routing tests ──

    #[tokio::test]
    async fn test_handle_slash_hub_update_routing() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub update my-skill").await;
        let has_msg = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Updating")));
        assert!(has_msg);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_remove_routing() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub remove my-skill").await;
        let has_remove = app.active_modal.is_some()
            || app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Removed")));
        assert!(has_remove);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_check_update_routing() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub check-update my-skill").await;
        let has_check = app.active_modal.is_some()
            || app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("up to date") || text.contains("Update available")));
        assert!(has_check);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_publish_routing() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub publish my-skill").await;
        let has_msg = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Publishing") || text.contains("Connection")));
        assert!(has_msg);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_update_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub update").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_remove_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub remove").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_check_update_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub check-update").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_publish_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub publish").await;
        assert!(app.active_modal.is_some());
    }

    #[tokio::test]
    async fn test_handle_slash_hub_shows_all_subcommands() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub").await;
        if let Some(crate::app::AppModal::Info { lines, .. }) = &app.active_modal {
            let text: String = lines.iter().map(|l| l.text.clone()).collect::<Vec<_>>().join(" ");
            assert!(text.contains("/hub update"));
            assert!(text.contains("/hub remove"));
            assert!(text.contains("/hub check-update"));
            assert!(text.contains("/hub publish"));
        } else {
            panic!("Expected Info modal");
        }
    }
}
