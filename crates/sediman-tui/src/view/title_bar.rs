use sediman_tui_core::renderer::{CellBuffer, Rect, Style, TextAttributes, display_width};
use crate::app::App;

use super::messages::format_elapsed;

pub fn render_title_bar(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;

    // ── Fill background ──
    for sx in area.x..area.right() {
        buf.put_char(sx, area.y, ' ', Style::new().bg(t.background).fg(t.text));
    }

    // ── Left: logo + spinner ──
    let spinner = if app.agent_running {
        format!(" {} ", app.spinner_char())
    } else {
        String::new()
    };

    let logo = format!(" \u{25c6} sediman{}", spinner);
    buf.draw_str(area.x, area.y, &logo, Style::new()
        .fg(t.primary)
        .add_modifier(TextAttributes::bold()));

    let version = format!(" v{}", env!("CARGO_PKG_VERSION"));
    let vx = area.x + display_width(&logo);
    if vx < area.right() {
        buf.draw_str(vx, area.y, &version, Style::new().fg(t.text_muted).bg(t.background));
    }

    // ── Right: provider/model + status ──
    let provider = &app.provider;
    let model = app.model.as_deref().unwrap_or("default");

    let status_text = if app.agent_running {
        format_elapsed(app.agent_start.elapsed().as_secs())
    } else {
        "idle".into()
    };
    let status_color = if app.agent_running { t.success } else { t.text_muted };

    // Provider pill
    let provider_pill = format!(" {} ", provider);
    let model_label = format!(" {} ", model);
    let sep = " \u{b7} ";
    let status = format!(" {} ", status_text);

    let right_w = display_width(&provider_pill) + display_width(&model_label) + display_width(sep) + display_width(&status);
    let mut rx = area.right().saturating_sub(right_w);

    buf.draw_str(rx, area.y, &provider_pill, Style::new().bg(t.secondary).fg(t.background));
    rx += display_width(&provider_pill) as u16;
    buf.draw_str(rx, area.y, &model_label, Style::new().bg(t.background_darker).fg(t.text));
    rx += display_width(&model_label) as u16;
    buf.draw_str(rx, area.y, sep, Style::new().fg(t.border_dim).bg(t.background));
    rx += display_width(sep);
    buf.draw_str(rx, area.y, &status, Style::new().fg(status_color).bg(t.background));

    // ── Reconnecting warning ──
    if app.reconnecting {
        let warn = " \u{26a0} reconnecting ";
        let wx = area.x + display_width(&logo) + display_width(&version);
        if wx + display_width(warn) < rx {
            buf.draw_str(wx, area.y, warn, Style::new().fg(t.warning).bg(t.background).add_modifier(TextAttributes::bold()));
        }
    }
}
