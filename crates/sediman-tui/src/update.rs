use std::sync::Arc;
use std::sync::atomic::AtomicBool;

use tokio::sync::mpsc;

use sediman_tui_core::event::AppEvent;

use crate::app::{App, AppModal};
use crate::commands::{
    browser, coder, connect, delegate, hub, memory, model, plan, provider, schedule, sessions,
    skills, soul, system, theming,
};

fn send_desktop_notification(title: &str, body: &str) {
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("osascript")
            .arg("-e")
            .arg(format!("display notification \"{}\" with title \"{}\"", body.replace('"', "\\\""), title.replace('"', "\\\"")))
            .spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = std::process::Command::new("notify-send")
            .arg(title)
            .arg(body)
            .spawn();
    }
}

const DEFAULT_SOUL: &str = "You are OpenSkynet, a self-improving browser automation agent.

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

            // Clipboard: Ctrl+V or Cmd+V paste
            if key.code == KeyCode::Char('v')
                && !key.modifiers.contains(KeyModifiers::SHIFT)
                && (key.modifiers.contains(KeyModifiers::CONTROL) || key.modifiers.contains(KeyModifiers::SUPER))
            {
                if let Ok(mut clipboard) = arboard::Clipboard::new() {
                    if let Ok(text) = clipboard.get_text() {
                        let line_count = text.lines().count();
                        if line_count > 1 {
                            app.editor.insert_str(&format!("[paste {} lines]", line_count));
                        } else {
                            app.editor.insert_str(&text);
                        }
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
                // ── Unified ModelPicker — exact OpenCode copy: ←/→/H/L provider, ↑/↓/J/K model ──
                if matches!(app.active_modal, Some(AppModal::ModelPicker)) {
                    match key.code {
                        KeyCode::Esc => {
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.active_modal = None;
                            return;
                        }
                        // ← / H: previous provider (wraps around)
                        KeyCode::Left | KeyCode::Char('h') => {
                            if app.available_providers.len() > 1 {
                                if app.model_dialog_provider_idx > 0 {
                                    app.model_dialog_provider_idx -= 1;
                                } else {
                                    app.model_dialog_provider_idx = app.available_providers.len().saturating_sub(1);
                                }
                                app.model_dialog_model_idx = 0;
                                app.model_dialog_scroll = 0;
                            }
                            return;
                        }
                        // → / L: next provider (wraps around)
                        KeyCode::Right | KeyCode::Char('l') => {
                            if app.available_providers.len() > 1 {
                                if app.model_dialog_provider_idx < app.available_providers.len().saturating_sub(1) {
                                    app.model_dialog_provider_idx += 1;
                                } else {
                                    app.model_dialog_provider_idx = 0;
                                }
                                app.model_dialog_model_idx = 0;
                                app.model_dialog_scroll = 0;
                            }
                            return;
                        }
                        // ↑ / K: previous model (wraps to bottom)
                        KeyCode::Up | KeyCode::Char('k') => {
                            let provider_name = app.available_providers
                                .get(app.model_dialog_provider_idx)
                                .map(|p| p.name.as_str())
                                .unwrap_or("");
                            let count = app.filtered_models_for_provider(provider_name).len();
                            if app.model_dialog_model_idx > 0 {
                                app.model_dialog_model_idx -= 1;
                            } else {
                                // Wrap to bottom
                                app.model_dialog_model_idx = count.saturating_sub(1);
                                app.model_dialog_scroll = count.saturating_sub(10.min(count));
                            }
                            // Keep cursor visible
                            if app.model_dialog_model_idx < app.model_dialog_scroll {
                                app.model_dialog_scroll = app.model_dialog_model_idx;
                            }
                            return;
                        }
                        // ↓ / J: next model (wraps to top)
                        KeyCode::Down | KeyCode::Char('j') => {
                            let provider_name = app.available_providers
                                .get(app.model_dialog_provider_idx)
                                .map(|p| p.name.as_str())
                                .unwrap_or("");
                            let count = app.filtered_models_for_provider(provider_name).len();
                            if app.model_dialog_model_idx < count.saturating_sub(1) {
                                app.model_dialog_model_idx += 1;
                            } else {
                                // Wrap to top
                                app.model_dialog_model_idx = 0;
                                app.model_dialog_scroll = 0;
                            }
                            // Keep cursor visible (max 10 visible)
                            let visible = 10;
                            if app.model_dialog_model_idx >= app.model_dialog_scroll + visible {
                                app.model_dialog_scroll = app.model_dialog_model_idx - (visible - 1);
                            }
                            return;
                        }
                        // Enter: select model and sync with backend
                        KeyCode::Enter => {
                            let provider_info = app.available_providers
                                .get(app.model_dialog_provider_idx)
                                .cloned();
                            if let Some(p) = provider_info {
                                let models = app.filtered_models_for_provider(&p.name);
                                if let Some(selected_model) = models.get(app.model_dialog_model_idx) {
                                    // Check if provider needs API key and doesn't have one
                                    if p.needs_api_key && !p.has_key {
                                        app.connect_target = Some(p.name.clone());
                                        app.api_key_input.clear();
                                        app.active_modal = Some(AppModal::ApiKeyPrompt);
                                        return;
                                    }
                                    // Sync with backend
                                    let model_id = selected_model.id.clone();
                                    if let Err(e) = app.bridge.switch_model(
                                        &p.name,
                                        Some(&model_id),
                                        p.default_base_url.as_deref(),
                                    ).await {
                                        app.add_error_message(format!("Failed to switch: {}", e));
                                        app.active_modal = None;
                                        return;
                                    }
                                    app.provider = p.name.clone();
                                    app.model = Some(model_id);
                                    app.add_system_message(format!("Switched to {}", app.display_model_id()));
                                }
                            }
                            app.active_modal = None;
                            return;
                        }
                        _ => return,
                    }
                }

                // CoderPicker — select coder backend
                if matches!(app.active_modal, Some(AppModal::CoderPicker)) {
                    const CODER_BACKENDS: &[&str] = &["internal", "claude-code", "codex", "opencode"];
                    match key.code {
                        KeyCode::Esc => {
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Up | KeyCode::Char('k') => {
                            if app.coder_picker_selected > 0 {
                                app.coder_picker_selected -= 1;
                            }
                            return;
                        }
                        KeyCode::Down | KeyCode::Char('j') => {
                            if app.coder_picker_selected < CODER_BACKENDS.len() - 1 {
                                app.coder_picker_selected += 1;
                            }
                            return;
                        }
                        KeyCode::Enter => {
                            if let Some(backend) = CODER_BACKENDS.get(app.coder_picker_selected) {
                                let old = app.coder_backend.clone();
                                app.coder_backend = backend.to_string();
                                if old != app.coder_backend {
                                    // Persist
                                    let config = crate::config::TuiConfig::load();
                                    let mut config = config;
                                    config.coder_backend = app.coder_backend.clone();
                                    if let Err(e) = config.save() {
                                        app.add_error_message(format!("Failed to save: {}", e));
                                    }
                                    app.add_system_message(format!("Coder backend: {} → {}", old, backend));
                                }
                            }
                            app.active_modal = None;
                            return;
                        }
                        _ => return,
                    }
                }

                // ApiKeyPrompt — type API key, Enter to save
                if matches!(app.active_modal, Some(AppModal::ApiKeyPrompt)) {
                    match key.code {
                        KeyCode::Esc => {
                            app.api_key_input.clear();
                            app.connect_target = None;
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            app.api_key_input.clear();
                            app.connect_target = None;
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Enter => {
                            if !app.api_key_input.is_empty() {
                                let target = app.connect_target.clone().unwrap_or_default();
                                let key_val = app.api_key_input.clone();
                                match app.bridge.auth_set(&target, &key_val).await {
                                    Ok(()) => {
                                        app.provider = target.clone();
                                        if let Ok(providers) = app.bridge.list_providers().await {
                                            app.available_providers = providers;
                                        }
                                        app.add_system_message(format!("Key saved for {} — provider switched.", target));
                                    }
                                    Err(e) => {
                                        app.add_error_message(format!("Failed to save key: {}", e));
                                    }
                                }
                            }
                            app.api_key_input.clear();
                            app.connect_target = None;
                            app.active_modal = None;
                            return;
                        }
                        KeyCode::Backspace | KeyCode::Delete => {
                            app.api_key_input.pop();
                            return;
                        }
                        KeyCode::Char(c) => {
                            app.api_key_input.push(c);
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
                        KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            if let Some((target, content)) = app.memory_entries.get(app.memory_editor_index).cloned() {
                                let _ = app.bridge.memory_remove(&target, &content).await;
                                app.memory_entries.remove(app.memory_editor_index);
                                if app.memory_editor_index > 0 {
                                    app.memory_editor_index -= 1;
                                }
                            }
                            return;
                        }
                        KeyCode::Backspace => {
                            app.memory_editor_input.pop();
                            return;
                        }
                        KeyCode::Char(c) => {
                            app.memory_editor_input.push(c);
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
                                app.show_toast("Personality updated.".into());
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
                        KeyCode::Esc => {
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

            // ScheduleBrowser — interactive schedule management
            if matches!(app.active_modal, Some(AppModal::ScheduleBrowser)) {
                match key.code {
                    KeyCode::Esc => {
                        app.schedule_input.clear();
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                        app.schedule_input.clear();
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Down | KeyCode::Char('j') => {
                        if app.schedule_selected < app.schedule_jobs.len().saturating_sub(1) {
                            app.schedule_selected += 1;
                        }
                        return;
                    }
                    KeyCode::Up | KeyCode::Char('k') => {
                        if app.schedule_selected > 0 {
                            app.schedule_selected -= 1;
                        }
                        return;
                    }
                    KeyCode::Enter => {
                        if app.schedule_input.is_empty() {
                            // Toggle enabled/disabled on selected job
                            if let Some(job) = app.schedule_jobs.get(app.schedule_selected).cloned() {
                                if job.enabled {
                                    let _ = app.bridge.remove_schedule(&job.id).await;
                                    app.add_system_message(format!("Paused job: {}", job.id));
                                } else {
                                    app.add_system_message("Job is paused. Press 'd' to delete.".into());
                                }
                            }
                        } else {
                            // Parse: <cron> <task>
                            let input = app.schedule_input.trim().to_string();
                            let parts: Vec<&str> = input.splitn(2, ' ').collect();
                            if parts.len() >= 2 {
                                match app.bridge.add_schedule(parts[0], parts[1]).await {
                                    Ok(id) => {
                                        app.add_system_message(format!("Scheduled: {}", id));
                                        app.schedule_input.clear();
                                        if let Ok(jobs) = app.bridge.list_schedules().await {
                                            app.schedule_jobs = jobs;
                                            app.schedule_selected = 0;
                                        }
                                    }
                                    Err(e) => app.add_error_message(format!("Failed: {}", e)),
                                }
                            } else {
                                app.add_error_message("Format: <cron> <task>".into());
                            }
                        }
                        return;
                    }
                    KeyCode::Char('d') => {
                        if app.schedule_input.is_empty() {
                            if let Some(job) = app.schedule_jobs.get(app.schedule_selected).cloned() {
                                match app.bridge.remove_schedule(&job.id).await {
                                    Ok(_) => {
                                        app.add_system_message(format!("Deleted: {}", job.task));
                                        if app.schedule_selected > 0 { app.schedule_selected -= 1; }
                                        if let Ok(jobs) = app.bridge.list_schedules().await {
                                            app.schedule_jobs = jobs;
                                        }
                                    }
                                    Err(e) => app.add_error_message(format!("Failed: {}", e)),
                                }
                            }
                        } else {
                            app.schedule_input.push('d');
                        }
                        return;
                    }
                    KeyCode::Backspace | KeyCode::Delete => {
                        if app.schedule_input.is_empty() {
                            // Delete selected job
                            if let Some(job) = app.schedule_jobs.get(app.schedule_selected).cloned() {
                                match app.bridge.remove_schedule(&job.id).await {
                                    Ok(_) => {
                                        app.add_system_message(format!("Deleted: {}", job.task));
                                        if app.schedule_selected > 0 { app.schedule_selected -= 1; }
                                        if let Ok(jobs) = app.bridge.list_schedules().await {
                                            app.schedule_jobs = jobs;
                                        }
                                    }
                                    Err(e) => app.add_error_message(format!("Failed: {}", e)),
                                }
                            }
                        } else {
                            app.schedule_input.pop();
                        }
                        return;
                    }
                    KeyCode::Char(c) => {
                        app.schedule_input.push(c);
                        return;
                    }
                    _ => return,
                }
            }

            // SessionBrowser — interactive session management
            if matches!(app.active_modal, Some(AppModal::SessionBrowser)) {
                let query = app.session_filter.to_lowercase();
                let filtered_count = app.session_list
                    .iter()
                    .filter(|s| {
                        if query.is_empty() { return true; }
                        let searchable = format!("{} {}", s.task, s.id).to_lowercase();
                        searchable.contains(&query)
                    })
                    .count();

                match key.code {
                    KeyCode::Esc => {
                        app.session_filter.clear();
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                        app.session_filter.clear();
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Down | KeyCode::Char('j') => {
                        if app.session_selected < filtered_count.saturating_sub(1) {
                            app.session_selected += 1;
                        }
                        return;
                    }
                    KeyCode::Up | KeyCode::Char('k') => {
                        if app.session_selected > 0 {
                            app.session_selected -= 1;
                        }
                        return;
                    }
                    KeyCode::Enter => {
                        // View session detail
                        let filtered: Vec<&sediman_tui_bridge::SessionInfo> = app.session_list
                            .iter()
                            .filter(|s| {
                                if query.is_empty() { return true; }
                                let searchable = format!("{} {}", s.task, s.id).to_lowercase();
                                searchable.contains(&query)
                            })
                            .collect();
                        if let Some(session) = filtered.get(app.session_selected) {
                            let sid = session.id.to_string();
                            let task_preview = session.task.clone();
                            match app.bridge.get_session_detail(&sid).await {
                                Ok(detail) => {
                                    let mut lines = vec![
                                        crate::app::ModalLine::heading(format!("  Session #{}", sid)),
                                        crate::app::ModalLine::muted(format!("  Task: {}", task_preview)),
                                        crate::app::ModalLine::muted(format!("  Created: {}", session.created_at)),
                                        crate::app::ModalLine::blank(),
                                    ];
                                    if let Some(steps) = detail.get("steps").and_then(|s| s.as_array()) {
                                        lines.push(crate::app::ModalLine::accent(format!("  Steps ({})", steps.len())));
                                        for step in steps.iter().take(20) {
                                            let action = step.get("action").and_then(|a| a.as_str()).unwrap_or("");
                                            if !action.is_empty() {
                                                lines.push(crate::app::ModalLine::normal(format!("    {}", action)));
                                            }
                                        }
                                    }
                                    if let Some(result) = session.result.as_deref() {
                                        if !result.is_empty() {
                                            lines.push(crate::app::ModalLine::blank());
                                            lines.push(crate::app::ModalLine::accent("  Result"));
                                            let max_len = 300.min(result.len());
                                            lines.push(crate::app::ModalLine::normal(format!("    {}...", &result[..max_len])));
                                        }
                                    }
                                    app.active_modal = Some(crate::app::AppModal::Info {
                                        title: format!("Session #{}", sid),
                                        lines,
                                        scroll: 0,
                                    });
                                }
                                Err(e) => {
                                    app.add_error_message(format!("Failed to load session: {}", e));
                                }
                            }
                        }
                        return;
                    }
                    KeyCode::Char('d') => {
                        if app.session_filter.is_empty() {
                            let filtered: Vec<&sediman_tui_bridge::SessionInfo> = app.session_list
                                .iter()
                                .filter(|s| {
                                    if query.is_empty() { return true; }
                                    let searchable = format!("{} {}", s.task, s.id).to_lowercase();
                                    searchable.contains(&query)
                                })
                                .collect();
                            if let Some(session) = filtered.get(app.session_selected) {
                                let sid = session.id.to_string();
                                match app.bridge.delete_session(&sid).await {
                                    Ok(()) => {
                                        app.add_system_message(format!("Deleted session #{}", sid));
                                        if app.session_selected > 0 {
                                            app.session_selected -= 1;
                                        }
                                        // Refresh list
                                        if let Ok(sessions) = app.bridge.get_sessions().await {
                                            app.session_list = sessions;
                                        }
                                    }
                                    Err(e) => app.add_error_message(format!("Failed to delete: {}", e)),
                                }
                            }
                        } else {
                            app.session_filter.push('d');
                        }
                        return;
                    }
                    KeyCode::Backspace | KeyCode::Delete => {
                        if app.session_filter.is_empty() {
                            // Delete selected session
                            let filtered: Vec<&sediman_tui_bridge::SessionInfo> = app.session_list
                                .iter()
                                .filter(|s| {
                                    if query.is_empty() { return true; }
                                    let searchable = format!("{} {}", s.task, s.id).to_lowercase();
                                    searchable.contains(&query)
                                })
                                .collect();
                            if let Some(session) = filtered.get(app.session_selected) {
                                let sid = session.id.to_string();
                                match app.bridge.delete_session(&sid).await {
                                    Ok(()) => {
                                        app.add_system_message(format!("Deleted session #{}", sid));
                                        if app.session_selected > 0 {
                                            app.session_selected -= 1;
                                        }
                                        if let Ok(sessions) = app.bridge.get_sessions().await {
                                            app.session_list = sessions;
                                        }
                                    }
                                    Err(e) => app.add_error_message(format!("Failed to delete: {}", e)),
                                }
                            }
                        } else {
                            app.session_filter.pop();
                            app.session_selected = 0;
                        }
                        return;
                    }
                    KeyCode::Char(c) => {
                        app.session_filter.push(c);
                        app.session_selected = 0;
                        return;
                    }
                    _ => return,
                }
            }

            // ThemePicker — interactive theme browser with live preview
            if matches!(app.active_modal, Some(AppModal::ThemePicker)) {
                let count = app.theme_picker_names.len();
                match key.code {
                    KeyCode::Esc | KeyCode::Char('q') => {
                        app.theme = app.theme_picker_saved_theme.clone();
                        app.theme_name = app.theme_picker_saved_name.clone();
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                        app.theme = app.theme_picker_saved_theme.clone();
                        app.theme_name = app.theme_picker_saved_name.clone();
                        app.active_modal = None;
                        return;
                    }
                    KeyCode::Down | KeyCode::Char('j') => {
                        if app.theme_picker_selected < count.saturating_sub(1) {
                            app.theme_picker_selected += 1;
                        }
                        if let Some(name) = app.theme_picker_names.get(app.theme_picker_selected) {
                            if let Some(theme) = sediman_tui_core::styling::load_theme(name) {
                                app.theme = theme;
                                app.theme_name = name.clone();
                            }
                        }
                        return;
                    }
                    KeyCode::Up | KeyCode::Char('k') => {
                        if app.theme_picker_selected > 0 {
                            app.theme_picker_selected -= 1;
                        }
                        if let Some(name) = app.theme_picker_names.get(app.theme_picker_selected) {
                            if let Some(theme) = sediman_tui_core::styling::load_theme(name) {
                                app.theme = theme;
                                app.theme_name = name.clone();
                            }
                        }
                        return;
                    }
                    KeyCode::Enter => {
                        crate::commands::theming::save_config_now(&*app);
                        app.add_system_message(format!("Theme: {}", app.theme_name));
                        app.active_modal = None;
                        return;
                    }
                    _ => return,
                }
            }

            // Help / Info modal handling — vim-style navigation
            if matches!(app.active_modal, Some(AppModal::Help { .. }) | Some(AppModal::Info { .. })) {
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
                        match &mut app.active_modal {
                            Some(AppModal::Info { scroll, .. }) | Some(AppModal::Help { scroll }) => {
                                *scroll = scroll.saturating_add(1);
                            }
                            _ => {}
                        }
                        return;
                    }
                    KeyCode::Up | KeyCode::Char('k') => {
                        match &mut app.active_modal {
                            Some(AppModal::Info { scroll, .. }) | Some(AppModal::Help { scroll }) => {
                                *scroll = scroll.saturating_sub(1);
                            }
                            _ => {}
                        }
                        return;
                    }
                    KeyCode::PageDown => {
                        match &mut app.active_modal {
                            Some(AppModal::Info { scroll, .. }) | Some(AppModal::Help { scroll }) => {
                                *scroll = scroll.saturating_add(10);
                            }
                            _ => {}
                        }
                        return;
                    }
                    KeyCode::PageUp => {
                        match &mut app.active_modal {
                            Some(AppModal::Info { scroll, .. }) | Some(AppModal::Help { scroll }) => {
                                *scroll = scroll.saturating_sub(10);
                            }
                            _ => {}
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
            } // close if app.active_modal.is_some()

            // ── Non-modal key handling ──
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
                    if matches!(app.active_modal, Some(AppModal::Help { .. })) {
                        app.active_modal = None;
                    } else {
                        app.active_modal = Some(AppModal::Help { scroll: 0 });
                    }
                }
                // Keep Ctrl+P as alias for help toggle
                KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if matches!(app.active_modal, Some(AppModal::Help { .. })) {
                        app.active_modal = None;
                    } else {
                        app.active_modal = Some(AppModal::Help { scroll: 0 });
                    }
                }
                KeyCode::Enter => {
                    // Ctrl+Enter or Shift+Enter → newline in editor
                    // Plain Enter → submit (or accept completion if popup visible)
                    let has_modifier = key.modifiers.contains(KeyModifiers::SHIFT)
                        || key.modifiers.contains(KeyModifiers::CONTROL);
                    if has_modifier {
                        app.editor.input(key);
                    } else if let Some(cmd) = app.completer.selected_text() {
                        // Accept completion selection
                        app.editor.delete_line_by_head();
                        app.editor.insert_str(cmd);
                        app.completer.complete("");
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
                        // Auto-complete slash commands
                        if let Some(selected) = app.completer.selected_text() {
                            app.editor.delete_line_by_head();
                            app.editor.insert_str(selected);
                            app.completer.complete("");
                        } else {
                            app.completer.complete(&prefix);
                            app.completer.next();
                        }
                    } else {
                        app.agent_mode = app.agent_mode.cycle();
                    }
                }
                KeyCode::Up => {
                    if key.modifiers.contains(KeyModifiers::SHIFT) {
                        scroll_up(app, 3);
                    } else {
                        let input = app.editor.lines().join(" ").trim().to_string();
                        if input.starts_with('/') && !app.completer.filtered().is_empty() {
                            app.completer.up();
                        } else {
                            app.editor.history_up();
                        }
                    }
                }
                KeyCode::Down => {
                    if key.modifiers.contains(KeyModifiers::SHIFT) {
                        scroll_down(app, 3);
                    } else {
                        let input = app.editor.lines().join(" ").trim().to_string();
                        if input.starts_with('/') && !app.completer.filtered().is_empty() {
                            app.completer.down();
                        } else {
                            app.editor.history_down();
                        }
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
                KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if app.editor.is_searching() {
                        let query = app.editor.search_query().to_string();
                        if !query.is_empty() {
                            let query_lower = query.to_lowercase();
                            let current_pos = app.editor.history_pos().unwrap_or(app.editor.history().len());
                            if let Some((i, _entry)) = app.editor.history().iter().enumerate().rev()
                                .filter(|(i, _)| *i < current_pos)
                                .find(|(_, entry)| entry.to_lowercase().contains(&query_lower))
                            {
                                app.editor.load_history_entry(i);
                            }
                        }
                    } else {
                        app.editor.start_history_search();
                    }
                }
                _ => {
                    if app.editor.is_searching() {
                        match key.code {
                            KeyCode::Char(c) => {
                                if key.modifiers.contains(KeyModifiers::CONTROL) {
                                    app.editor.cancel_history_search();
                                } else {
                                    app.editor.history_search_char(c);
                                }
                            }
                            KeyCode::Backspace => {
                                app.editor.history_search_backspace();
                            }
                            KeyCode::Enter | KeyCode::Esc => {
                                app.editor.accept_history_search();
                            }
                            _ => {}
                        }
                    } else {
                        app.editor.input(key);
                        let current = app.editor.lines().join(" ").trim().to_string();
                        if current.starts_with('/') {
                            app.completer.complete(&current);
                        } else {
                            app.completer.complete("");
                        }
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
            let line_count = text.lines().count();
            if line_count > 1 {
                app.editor.insert_str(&format!("[paste {} lines]", line_count));
            } else {
                app.editor.insert_str(&text);
            }
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
            if elapsed_secs >= 30 {
                let status = if success { "Completed" } else { "Failed" };
                send_desktop_notification("OpenSkynet", &format!("Task {} in {}s", status, elapsed_secs));
            }
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

fn scroll_down(app: &mut App, amount: u16) {
    app.scroll_offset = app.scroll_offset.saturating_add(amount);
    app.auto_scroll = false;
}

async fn handle_slash(app: &mut App, input: &str) {
    let input = input.trim();
    let (cmd_name, args) = parse_command(input);

    match cmd_name {
        "/help" => system::handle_help(app, args).await,
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
        "/hub" => hub::handle_hub_browse(app, args).await,
        "/memory" => {
            memory::handle_memory(app, args).await;
            refresh_sidebar(app).await;
        }
        "/remember" => memory::handle_remember(app, args).await,
        "/model" | "/models" => model::handle_model(app, args).await,
        "/provider" => provider::handle_provider(app, args).await,
        "/connect" => connect::handle_connect(app, args).await,
        "/schedule" => {
            schedule::handle_schedule(app, args).await;
            refresh_sidebar(app).await;
        }
        "/sessions" | "/session" => sessions::handle_sessions(app, args).await,
        "/browser" => browser::handle_browser(app, args).await,
        "/screenshot" => browser::handle_screenshot(app, args).await,
        "/delegate" => delegate::handle_delegate(app, args).await,
        "/parallel" => delegate::handle_parallel(app, args).await,
        "/plan" => plan::handle_plan(app, args).await,
        "/soul" => soul::handle_soul(app, args).await,
        "/themes" => theming::handle_themes(app, args).await,
        "/coder" => coder::handle_coder(app, args).await,
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

/// Launch an external coder tool (claude-code, codex, opencode) as a subprocess.
async fn handle_coder_external(app: &mut App, task: &str) {
    let (cmd_name, args) = match app.coder_backend.as_str() {
        "claude-code" => ("claude", vec!["--print", task]),
        "codex" => ("codex", vec!["-q", task]),
        "opencode" => ("opencode", vec!["-p", task]),
        other => {
            app.add_error_message(format!("Unknown coder backend: {}", other));
            return;
        }
    };

    app.show_banner = false;
    app.task_count += 1;
    app.agent_running = true;
    app.agent_start = std::time::Instant::now();
    app.spinner_text = format!("Running {}...", cmd_name);
    app.interrupt.clear();

    app.add_user_message(task.to_string(), app.task_count);
    app.start_agent_message(task);

    let output = tokio::process::Command::new(cmd_name)
        .args(&args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()
        .await;

    let elapsed = app.agent_start.elapsed().as_secs();

    match output {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout).to_string();
            let stderr = String::from_utf8_lossy(&out.stderr).to_string();
            let success = out.status.success();
            let result_text = if stdout.is_empty() { stderr.clone() } else { stdout };

            app.complete_agent_message(success, result_text, elapsed, None, None);

            if success {
                app.add_system_message(format!("{} done ({}s)", cmd_name, elapsed));
            } else {
                app.add_error_message(format!("{} failed ({}s): {}", cmd_name, elapsed, stderr));
            }
        }
        Err(e) => {
            app.complete_agent_message(false, format!("Failed to launch {}: {}", cmd_name, e), elapsed, None, None);
            app.add_error_message(format!("Is '{}' installed? Error: {}", cmd_name, e));
        }
    }
}

pub async fn handle_task(app: &mut App, task: &str, event_tx: &mpsc::UnboundedSender<AppEvent>) {
    // Route Coder mode with external backend to subprocess
    if app.agent_mode == crate::app::AgentMode::Coder && app.coder_backend != "internal" {
        handle_coder_external(app, task).await;
        return;
    }

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
    async fn test_handle_slash_hub_opens_browser() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub").await;
        // /hub now opens the skill browser directly (or shows message if no connection)
        assert!(app.active_modal.is_some() || app.messages.iter().any(|m| matches!(m, ChatMessage::Error { .. })));
    }

    #[tokio::test]
    async fn test_themes_opens_picker() {
        let mut app = test_app();
        let original_theme = app.theme_name.clone();
        handle_slash(&mut app, "/themes").await;
        assert!(matches!(app.active_modal, Some(crate::app::AppModal::ThemePicker)));
        assert!(app.theme_picker_names.len() >= 8);
        assert_eq!(app.theme_picker_saved_name, original_theme);
    }

    #[tokio::test]
    async fn test_themes_saves_original_for_revert() {
        let mut app = test_app();
        let original_bg = app.theme.background;
        handle_slash(&mut app, "/themes").await;
        assert_eq!(app.theme_picker_saved_theme.background, original_bg);
    }

    #[tokio::test]
    async fn test_themes_no_alias() {
        let mut app = test_app();
        handle_slash(&mut app, "/theme").await;
        assert!(app.active_modal.is_none());
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
        let has_unknown = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text.contains("Unknown command")));
        assert!(has_unknown);
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
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_parallel_too_many() {
        let mut app = test_app();
        handle_slash(&mut app, "/parallel a | b | c | d | e | f").await;
        let has_max = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text.contains("Max 5")));
        assert!(has_max);
    }

    #[tokio::test]
    async fn test_handle_slash_parallel_empty() {
        let mut app = test_app();
        handle_slash(&mut app, "/parallel").await;
        let has_usage = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text.contains("Usage")));
        assert!(has_usage);
    }

    #[tokio::test]
    async fn test_handle_slash_parallel_pipes_only() {
        let mut app = test_app();
        handle_slash(&mut app, "/parallel  |  |  ").await;
        let has_empty = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text.contains("No tasks")));
        assert!(has_empty);
    }

    #[tokio::test]
    async fn test_handle_slash_hub_no_subcommand() {
        let mut app = test_app();
        handle_slash(&mut app, "/hub").await;
        assert!(app.active_modal.is_some());
    }

    #[tokio::test]
    async fn test_handle_slash_compress_keeps_recent() {
        let mut app = test_app();
        for i in 0..25 {
            app.add_system_message(format!("msg {}", i));
        }
        handle_slash(&mut app, "/compress").await;
        let has_compress_msg = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text.contains("compressed")));
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
        let has_err = app.messages.iter().any(|m| matches!(m, ChatMessage::Error { text, .. } if text.contains("timeout")));
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
        let has_msg = app.messages.iter().any(|m| matches!(m, ChatMessage::System { text, .. } if text == "output text"));
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
    async fn test_skill_browser_q_types_into_filter() {
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
        assert!(app.active_modal.is_some());
        assert_eq!(app.skill_browser_filter, "q");
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
        let has_err = app.messages.iter().any(|m| matches!(m, ChatMessage::Error { text, .. } if text.contains("not installed")));
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
            matches!(m, ChatMessage::System { text, .. } if text.contains("Uninstalling"))
        });
        assert!(has_uninstall);
    }

    // ── /hub tests ──
}

