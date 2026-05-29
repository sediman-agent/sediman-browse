use sediman_tui_core::renderer::{CellBuffer, Rect, Style, TextAttributes, display_width};
use crate::app::{App, SideTab};

const MAX_ENTRY_DISPLAY: usize = 35;

pub fn render_side_panel(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let tab_labels: &[(&str, SideTab)] = &[
        ("Skills", SideTab::Skills),
        ("Memory", SideTab::Memory),
        ("Schedule", SideTab::Schedule),
        ("Status", SideTab::Status),
    ];

    let current = app.side_panel_tab;
    let content_area = Rect::new(area.x, area.y + 1, area.width, area.height - 1);

    let mut x = area.x;
    for (label, tab) in tab_labels {
        let active = *tab == current;
        let sep = if active { " \u{25b8} " } else { "   " };
        let style = if active {
            Style::new().fg(t.primary).add_modifier(TextAttributes::bold())
        } else {
            Style::new().fg(t.text_muted)
        };
        let full = format!("{}{}", sep, label);
        buf.draw_str(x, area.y, &full, style);
        x += display_width(&full) + 1;
    }

    let sy = content_area.y;
    for sx in content_area.x..content_area.right() {
        buf.put_char(sx, sy.saturating_sub(1), '\u{2500}', Style::new().fg(t.border));
    }

    let lines: Vec<(String, Style)> = match current {
        SideTab::Skills => render_list_tab("Skills", "/skills to load", &app.skills_cache, t),
        SideTab::Memory => render_list_tab("Memory", "/memory to load", &app.memory_cache, t),
        SideTab::Schedule => render_list_tab("Schedule", "/schedule to load", &app.schedule_cache, t),
        SideTab::Status => render_status_tab_inner(app),
    };

    let mut y = content_area.y;
    for (text, style) in &lines {
        if y >= content_area.bottom() {
            break;
        }
        buf.draw_str(content_area.x, y, text, *style);
        y += 1;
    }
}

fn render_list_tab(title: &str, empty_hint: &str, cache: &[String], t: &sediman_tui_core::styling::Theme) -> Vec<(String, Style)> {
    let mut out = Vec::new();
    out.push(("".into(), Style::new()));
    out.push((format!("  {}", title), Style::new().fg(t.secondary).add_modifier(TextAttributes::bold())));

    if cache.is_empty() {
        out.push(("  none yet".into(), Style::new().fg(t.text_muted)));
        out.push((format!("  \u{2502} {}", empty_hint), Style::new().fg(t.text_muted)));
    } else {
        for entry in cache {
            let d: String = entry.chars().take(MAX_ENTRY_DISPLAY).collect();
            out.push((format!("  \u{2022} {}", d), Style::new().fg(t.text)));
        }
    }
    out
}

fn render_status_tab_inner(app: &App) -> Vec<(String, Style)> {
    let t = &app.theme;
    let mode = app.permission.current_label();
    let agent_status = if app.agent_running { "running" } else { "idle" };
    let agent_style = if app.agent_running { Style::new().fg(t.success) } else { Style::new().fg(t.text_muted) };

    vec![
        ("".into(), Style::new()),
        ("  Status".into(), Style::new().fg(t.secondary).add_modifier(TextAttributes::bold())),
        ("".into(), Style::new()),
        (format!("  Model   {}", app.model.as_deref().unwrap_or("default")), Style::new().fg(t.text)),
        (format!("  Mode    {}", mode), Style::new().fg(t.text)),
        (format!("  Tasks   {}", app.task_count), Style::new().fg(t.text)),
        (format!("  Browser {}", if app.headless { "headless" } else { "headed" }), Style::new().fg(t.text)),
        (format!("  Agent   {}", agent_status), agent_style),
    ]
}
