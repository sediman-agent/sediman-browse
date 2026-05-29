use sediman_tui_core::renderer::{CellBuffer, Rect, Style};
use crate::app::App;

pub fn render_input(buf: &mut CellBuffer, area: Rect, app: &mut App) {
    let t = &app.theme;

    // area is 4 rows: [separator, top-border, input+bottom-border, hints]
    let sep_y = area.y;

    // ── Muted separator ──
    for sx in area.x..area.right() {
        buf.put_char(sx, sep_y, '\u{2500}', Style::new().fg(t.border_dim).bg(t.background));
    }

    let x_left = area.x + 1;
    let x_right = area.right().saturating_sub(2);
    let box_w = x_right.saturating_sub(x_left);
    let border = Style::new().fg(t.border).bg(t.background);
    let panel = Style::new().bg(t.background_panel).fg(t.text);

    // ── Top border: ╭──────────────╮ ──
    let row_top = area.y + 1;
    buf.put_char(x_left, row_top, '\u{256d}', border);
    buf.put_char(x_right, row_top, '\u{256e}', border);
    for sx in (x_left + 1)..x_right {
        buf.put_char(sx, row_top, '\u{2500}', border);
    }

    // ── Input row: │ ❯ text... │ ──
    let row_input = area.y + 2;
    for sx in x_left..=x_right {
        buf.put_char(sx, row_input, ' ', panel);
    }
    buf.put_char(x_left, row_input, '\u{2502}', border);
    buf.put_char(x_right, row_input, '\u{2502}', border);

    let prompt = if app.agent_running { "\u{25cf} " } else { "\u{276f} " };
    app.editor.set_prompt(prompt);

    let inner = Rect::new(x_left + 1, row_input, box_w.saturating_sub(1), 1);
    app.editor.render_into(buf, inner, &app.theme);

    // ── Bottom border: ╰──────────────╯ ──
    let row_bot = area.y + 3;
    buf.put_char(x_left, row_bot, '\u{2570}', border);
    buf.put_char(x_right, row_bot, '\u{256f}', border);
    for sx in (x_left + 1)..x_right {
        buf.put_char(sx, row_bot, '\u{2500}', border);
    }

    // ── Hint row inside the bottom border area ──
    let hint = if app.agent_running {
        " esc cancel"
    } else {
        " enter send \u{2502} / commands \u{2502} ctrl+enter newline"
    };
    let hint_x = x_right.saturating_sub(hint.len() as u16 + 1);
    buf.draw_str(hint_x, row_bot, hint, Style::new().fg(t.text_muted).bg(t.background));
}
