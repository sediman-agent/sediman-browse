mod title_bar;
mod messages;
mod banner;
mod modals;
mod status_bar;
mod completion;
mod sidebar;
mod input;

use sediman_tui_core::renderer::CellBuffer;
use crate::app::{App, AppModal};

pub fn render_into(buf: &mut CellBuffer, app: &mut App) {
    let area = buf.area();
    buf.fill(area, sediman_tui_core::renderer::Cell::EMPTY);
    buf.fill_style(area, sediman_tui_core::renderer::Style::new().bg(app.theme.background));

    // Dynamically expand input area based on visual lines (accounts for wrapping)
    // Approximate inner width: total width minus borders(2) + badge(~8) + padding(2)
    let approx_inner = area.width.saturating_sub(12) as usize;
    let editor_lines = app.editor.visual_lines(approx_inner).max(1) as u16;
    // Layout: separator(1) + top_border(1) + content(editor_lines) + bottom_border+hints(1)
    let needed = editor_lines + 3;
    app.layout.input_lines = needed.clamp(5, 15); // min 5 rows, max 15 rows

    let show_side = app.show_side_panel;
    app.layout.show_side_panel = show_side;
    let zones = app.layout.split(area);

    title_bar::render_title_bar(buf, zones.title_bar, app);

    if let Some(side_area) = zones.side_panel {
        sidebar::render_side_panel(buf, side_area, app);
    }

    messages::render_messages(buf, zones.main, app);
    status_bar::render_status_bar(buf, zones.status_bar, app);
    input::render_input(buf, zones.input, app);

    if let Some(ref modal) = app.active_modal {
        match modal {
            AppModal::Help { scroll } => modals::render_help_modal(buf, zones.main, app, *scroll as usize),
            AppModal::ModelPicker => modals::render_model_picker(buf, zones.main, app),
            AppModal::ProviderPicker => modals::render_provider_picker(buf, zones.main, app),
            AppModal::ConnectPicker => modals::render_connect_picker(buf, zones.main, app),
            AppModal::ApiKeyPrompt => modals::render_api_key_prompt(buf, zones.main, app),
            AppModal::MemoryEditor => modals::render_memory_editor(buf, zones.main, app),
            AppModal::SoulEditor => modals::render_soul_editor(buf, zones.main, app),
            AppModal::SkillBrowser => modals::render_skill_browser(buf, zones.main, app),
            AppModal::ScheduleBrowser => modals::render_schedule_browser(buf, zones.main, app),
            AppModal::ThemePicker => modals::render_theme_picker(buf, zones.main, app),
            AppModal::Info { title, lines, scroll } => {
                modals::render_info_modal(buf, zones.main, app, title, lines, *scroll);
            }
            AppModal::Doctor { .. } => {
                modals::render_doctor_modal(buf, zones.main, app);
            }
        }
    }

    if completion::show_completion(app) {
        completion::render_completion_popup(buf, zones.input, app);
    }

    if !app.toast_text.is_empty() && app.toast_expiry.is_some() {
        use sediman_tui_core::renderer::{Style, TextAttributes, display_width};
        let t = &app.theme;
        let text = &app.toast_text;
        let tw = display_width(text) + 4;
        let area = buf.area();
        let tx = area.x + (area.width.saturating_sub(tw)) / 2;
        let ty = area.bottom().saturating_sub(3);
        for sx in tx..tx + tw {
            if sx < area.right() {
                buf.put_char(sx, ty, ' ', Style::new().bg(t.primary).fg(t.background));
            }
        }
        buf.draw_str(tx + 2, ty, text, Style::new().bg(t.primary).fg(t.background).add_modifier(TextAttributes::bold()));
    }
}
