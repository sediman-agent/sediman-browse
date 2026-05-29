use sediman_tui_core::renderer::{CellBuffer, Rect, Style, TextAttributes, truncate_str};
use crate::app::App;

use super::modals::draw_modal_border;

pub fn show_completion(app: &App) -> bool {
    let input = app.editor.lines().join(" ").trim().to_string();
    input.starts_with('/') && !app.completer.filtered().is_empty()
}

pub fn render_completion_popup(buf: &mut CellBuffer, input_area: Rect, app: &App) {
    let completions = app.completer.filtered();
    if completions.is_empty() {
        return;
    }

    let t = &app.theme;
    let max_items = 10.min(completions.len());
    let popup_height = max_items as u16 + 2;
    let popup_y = input_area.y.saturating_sub(popup_height).max(1);
    let popup_area = Rect::new(
        input_area.x,
        popup_y,
        input_area.width.min(40),
        popup_height,
    );

    for py in popup_area.y..popup_area.bottom() {
        for px in popup_area.x..popup_area.right() {
            buf.put_char(px, py, ' ', Style::new().bg(t.background_panel));
        }
    }

    let border_style = Style::new().fg(t.border);
    draw_modal_border(buf, popup_area, border_style, border_style);

    let title = " Commands ";
    let tlen = title.chars().count().min(popup_area.width as usize - 2);
    let title_display = truncate_str(title, tlen);
    buf.draw_str(popup_area.x + 1, popup_area.y, title_display, Style::new().fg(t.primary).add_modifier(TextAttributes::bold()));

    let inner_x = popup_area.x + 1;
    let inner_y = popup_area.y + 1;
    for (i, cmd) in completions.iter().take(max_items).enumerate() {
        if inner_y + i as u16 >= popup_area.bottom() - 1 {
            break;
        }
        let text = format!("  {}", cmd);
        buf.draw_str(inner_x, inner_y + i as u16, &text, Style::new().fg(t.text).bg(t.background_panel));
    }
}
