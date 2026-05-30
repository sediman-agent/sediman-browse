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
            AppModal::Help => modals::render_help_modal(buf, zones.main, app),
            AppModal::ModelPicker => modals::render_model_picker(buf, zones.main, app),
            AppModal::ProviderPicker => modals::render_provider_picker(buf, zones.main, app),
            AppModal::MemoryEditor => modals::render_memory_editor(buf, zones.main, app),
            AppModal::SoulEditor => modals::render_soul_editor(buf, zones.main, app),
            AppModal::SkillBrowser => modals::render_skill_browser(buf, zones.main, app),
            AppModal::Info { title, lines, scroll } => {
                modals::render_info_modal(buf, zones.main, app, title, lines, *scroll);
            }
        }
    }

    if completion::show_completion(app) {
        completion::render_completion_popup(buf, zones.input, app);
    }
}
