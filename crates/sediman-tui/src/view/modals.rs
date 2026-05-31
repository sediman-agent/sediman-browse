use sediman_tui_core::renderer::{CellBuffer, Rect, Style, TextAttributes, display_width, truncate_str};
use sediman_tui_core::renderer::Color;
use crate::app::{App, ModalLineStyle, DoctorStatus};

struct ModalFrame {
    modal: Rect,
    inner_x: u16,
    inner_w: usize,
}

impl ModalFrame {
    fn new(buf: &mut CellBuffer, area: Rect, app: &App, modal_w: u16, modal_h: u16) -> Self {
        let t = &app.theme;
        let modal_x = area.x + (area.width.saturating_sub(modal_w)) / 2;
        let modal_y = area.y + (area.height.saturating_sub(modal_h)) / 2;
        let modal = Rect::new(modal_x, modal_y, modal_w, modal_h);

        dim_background(buf, area, t.background_darker, t.text_muted);
        fill_modal_bg(buf, modal, t.background, t.text);

        Self {
            modal,
            inner_x: modal.x + 2,
            inner_w: modal.width.saturating_sub(4) as usize,
        }
    }

    fn draw_border(&self, buf: &mut CellBuffer, top_style: Style, bottom_style: Style) {
        draw_modal_border(buf, self.modal, top_style, bottom_style);
    }

    fn draw_title(&self, buf: &mut CellBuffer, title: &str, style: Style) {
        buf.draw_str(self.modal.x + 2, self.modal.y, title, style);
    }

    fn draw_close_hint(&self, buf: &mut CellBuffer, hint: &str, style: Style) {
        let x = self.modal.right().saturating_sub(display_width(hint) + 2);
        buf.draw_str(x, self.modal.y, hint, style);
    }
}

pub fn draw_modal_border(buf: &mut CellBuffer, modal: Rect, top_style: Style, bottom_style: Style) {
    buf.put_char(modal.x, modal.y, '\u{250c}', top_style);
    buf.put_char(modal.right() - 1, modal.y, '\u{2510}', top_style);
    buf.put_char(modal.x, modal.bottom() - 1, '\u{2514}', bottom_style);
    buf.put_char(modal.right() - 1, modal.bottom() - 1, '\u{2518}', bottom_style);
    for sx in (modal.x + 1)..(modal.right() - 1) {
        buf.put_char(sx, modal.y, '\u{2500}', top_style);
        buf.put_char(sx, modal.bottom() - 1, '\u{2500}', bottom_style);
    }
    for sy in (modal.y + 1)..(modal.bottom() - 1) {
        buf.put_char(modal.x, sy, '\u{2502}', top_style);
        buf.put_char(modal.right() - 1, sy, '\u{2502}', bottom_style);
    }
}

fn dim_background(buf: &mut CellBuffer, area: Rect, bg: Color, fg: Color) {
    for sy in area.y..area.bottom() {
        for sx in area.x..area.right() {
            if let Some(cell) = buf.get_mut(sx, sy) {
                cell.style = Style::new().bg(bg).fg(fg);
            }
        }
    }
}

fn fill_modal_bg(buf: &mut CellBuffer, modal: Rect, bg: Color, fg: Color) {
    for sy in modal.y..modal.bottom() {
        for sx in modal.x..modal.right() {
            buf.put_char(sx, sy, ' ', Style::new().bg(bg).fg(fg));
        }
    }
}

pub fn render_help_modal(buf: &mut CellBuffer, area: Rect, app: &App, scroll: usize) {
    let t = &app.theme;

    let modal_w = (area.width as usize * 7 / 10).clamp(50, 80) as u16;
    let modal_h = (area.height as usize * 8 / 10).clamp(20, 40) as u16;
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Commands Reference ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " q to close ", Style::new().fg(t.text_muted).bg(t.background));

    let categories: &[(&str, &[(&str, &str)])] = &[
        ("General", &[
            ("/help", "Show this help dialog"),
            ("/exit", "Quit OpenSkynet"),
            ("/status", "Show connection & session status"),
            ("/clear", "Clear conversation history"),
            ("/reset", "Full reset \u{2014} clear everything"),
        ]),
        ("Agent", &[
            ("/model", "Switch or search AI models"),
            ("/provider", "Switch LLM provider"),
            ("/plan", "Toggle plan-only mode"),
            ("/compress", "Compress conversation context"),
            ("/soul", "Edit agent personality"),
        ]),
        ("Skills", &[
            ("/skills", "List & search learned skills"),
            ("/hub", "Browse, install & manage hub skills"),
            ("/record", "Start recording a new skill"),
            ("/stop", "Stop skill recording"),
        ]),
        ("Browser", &[
            ("/browser", "Toggle headless/headed mode"),
            ("/screenshot", "Capture browser screenshot"),
        ]),
        ("Sessions", &[
            ("/sessions", "List & manage saved sessions"),
            ("/memory", "View & edit agent memory"),
            ("/remember <text>", "Save to agent memory"),
        ]),
        ("Schedule", &[
            ("/schedule", "List & manage scheduled jobs"),
        ]),
        ("Tasks", &[
            ("/delegate <task>", "Spawn a sub-agent task"),
            ("/parallel <a|b>", "Run tasks in parallel"),
        ]),
        ("Utilities", &[
            ("/themes", "Browse & apply color themes"),
            ("/connect", "Connect a new provider"),
            ("/terminal", "Show terminal status"),
            ("/doctor", "Run diagnostics check"),
            ("/export", "Export conversation to file"),
        ]),
    ];

    let cmd_style = Style::new().fg(t.primary).bg(t.background);
    let desc_style = Style::new().fg(t.text_muted).bg(t.background);
    let cat_style = Style::new().fg(t.accent).bg(t.background).add_modifier(TextAttributes::bold());

    let inner_x = frame.inner_x;
    let inner_w = frame.inner_w;
    let mut y = frame.modal.y + 2;
    let max_y = frame.modal.bottom().saturating_sub(2);
    let mut line_idx = 0usize;

    for (category, cmds) in categories {
        if y >= max_y { break; }
        if line_idx >= scroll {
            buf.draw_str(inner_x, y, category, cat_style);
            y += 1;
        }
        line_idx += 1;
        for (cmd, desc) in *cmds {
            if y >= max_y { break; }
            if line_idx >= scroll {
                let cmd_display = truncate_str(cmd, 22);
                buf.draw_str(inner_x + 1, y, cmd_display, cmd_style);
                let desc_x = inner_x + 24;
                if desc_x < frame.modal.right() - 2 {
                    let max_desc = inner_w.saturating_sub(25);
                    let desc_display = truncate_str(desc, max_desc);
                    buf.draw_str(desc_x, y, desc_display, desc_style);
                }
                y += 1;
            }
            line_idx += 1;
        }
        if line_idx >= scroll {
            y += 1;
        }
    }
}

pub fn render_info_modal(
    buf: &mut CellBuffer,
    area: Rect,
    app: &App,
    title: &str,
    lines: &[crate::app::ModalLine],
    scroll: u16,
) {
    let t = &app.theme;

    let line_count = lines.len() as u16;
    let modal_w = (area.width as usize * 7 / 10).clamp(50, 80) as u16;
    let content_h = line_count.min(area.height.saturating_sub(4));
    let modal_h = content_h + 4;
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);

    let border_style = Style::new().fg(t.primary);
    frame.draw_border(buf, border_style, border_style);

    let title_display = format!(" {} ", title);
    frame.draw_title(buf, &title_display, Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " q to close ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let inner_w = frame.inner_w;
    let mut y = frame.modal.y + 2;
    let needs_indicator = line_count > content_h;
    let max_y = if needs_indicator {
        frame.modal.bottom() - 2
    } else {
        frame.modal.bottom() - 1
    };
    let scroll = scroll as usize;

    for (i, line) in lines.iter().enumerate() {
        if i < scroll { continue; }
        if y >= max_y { break; }

        let display = truncate_str(&line.text, inner_w);

        let style = match line.style {
            ModalLineStyle::Normal => Style::new().fg(t.text).bg(t.background),
            ModalLineStyle::Accent => Style::new().fg(t.accent).bg(t.background).add_modifier(TextAttributes::bold()),
            ModalLineStyle::Muted => Style::new().fg(t.text_muted).bg(t.background),
            ModalLineStyle::Primary => Style::new().fg(t.primary).bg(t.background),
            ModalLineStyle::Error => Style::new().fg(t.error).bg(t.background),
            ModalLineStyle::Heading => Style::new().fg(t.secondary).bg(t.background).add_modifier(TextAttributes::bold()),
        };

        buf.draw_str(inner_x, y, display, style);
        y += 1;
    }

    if line_count > content_h {
        let pct = if line_count > content_h {
            (scroll as u16 * 100) / (line_count - content_h)
        } else {
            0
        };
        let indicator = format!(" {}% ", pct.min(100));
        let ix = frame.modal.right().saturating_sub(display_width(&indicator) + 2);
        let iy = frame.modal.bottom() - 2;
        if iy > frame.modal.y + 1 {
            buf.draw_str(ix, iy, &indicator, Style::new().fg(t.text_muted).bg(t.background));
        }
    }
}

pub fn render_model_picker(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let current = format!("{}/{}", app.provider, app.model.as_deref().unwrap_or("default"));

    let query = app.model_picker_input.to_lowercase();
    let filtered: Vec<(usize, &String)> = app.model_picker_list
        .iter()
        .enumerate()
        .filter(|(_, m)| query.is_empty() || m.to_lowercase().contains(&query))
        .collect();

    let max_visible = 8u16;
    let visible = (filtered.len() as u16).min(max_visible);
    let modal_w = (area.width * 6 / 10).clamp(48, 60);
    let modal_h = (visible + 7).max(10).min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Select Model ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let mut y = frame.modal.y + 2;

    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }

    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));

    if app.model_picker_input.is_empty() {
        buf.draw_str(inner_x + 2, y, "Type to search or add a model...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let input_chars: String = app.model_picker_input.chars().collect();
        let display: String = if input_chars.len() > inner_w.saturating_sub(4) {
            input_chars.chars().skip(input_chars.len() - (inner_w - 4)).collect()
        } else {
            input_chars
        };
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cursor_x = inner_x + 2 + display_width(&display);
        if cursor_x < frame.modal.right() - 2 {
            buf.put_char(cursor_x, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }

    y += 1;

    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    y += 1;

    let max_y = frame.modal.bottom().saturating_sub(3);

    if filtered.is_empty() {
        if app.model_picker_list.is_empty() {
            buf.draw_str(inner_x, y, "No models saved yet.", Style::new().fg(t.text_muted).bg(t.background));
            y += 1;
            buf.draw_str(inner_x, y, "Type a name above and press Enter to add.", Style::new().fg(t.text_muted).bg(t.background));
        } else {
            buf.draw_str(inner_x, y, "No matches.", Style::new().fg(t.text_muted).bg(t.background));
            y += 1;
            buf.draw_str(inner_x, y, "Press Enter to add as a new model.", Style::new().fg(t.text_muted).bg(t.background));
        }
    } else {
        for (i, (_, model_name)) in filtered.iter().enumerate() {
            if y >= max_y { break; }
            let selected = i == app.model_picker_index;
            let is_current = model_name.as_str() == current;

            let max_display = inner_w.saturating_sub(6);
            let display: String = truncate_str(model_name, max_display).to_string();

            if selected {
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
                }
                let marker = if is_current { "\u{25c6} " } else { "  " };
                buf.draw_str(inner_x, y, &format!("{}\u{25b8} {}", marker, display),
                    Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
            } else {
                let marker = if is_current { "\u{25c6} " } else { "  " };
                buf.draw_str(inner_x, y, &format!("{} {}", marker, display),
                    Style::new().fg(if is_current { t.primary } else { t.text }).bg(t.background));
            }
            y += 1;
        }
    }

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);

    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }

    buf.draw_str(frame.modal.x + 2, hints_y, " Enter select \u{2502} \u{232b} remove \u{2502} Type to search ",
        Style::new().fg(t.text_muted).bg(t.background));
}

pub fn render_provider_picker(buf: &mut CellBuffer, area: Rect, app: &App) {
    render_provider_list(buf, area, app, " Provider ", false);
}

pub fn render_connect_picker(buf: &mut CellBuffer, area: Rect, app: &App) {
    render_provider_list(buf, area, app, " Connect Provider ", true);
}

pub fn render_api_key_prompt(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let target = app.connect_target.as_deref().unwrap_or("unknown");
    let modal_w = 50u16;
    let modal_h = 8u16;
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_x = frame.inner_x;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, &format!(" {} ", target), Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let mut y = frame.modal.y + 2;
    buf.draw_str(inner_x, y, &format!("Enter API key for {}:", target),
        Style::new().fg(t.text).bg(t.background));
    y += 1;

    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }
    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));

    if app.api_key_input.is_empty() {
        buf.draw_str(inner_x + 2, y, "sk-...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let masked: String = "\u{2022}".repeat(app.api_key_input.len().min(30));
        let display: String = masked.chars().take(frame.inner_w.saturating_sub(4)).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
    }

    let hints_y = frame.modal.bottom().saturating_sub(2);
    buf.draw_str(frame.modal.x + 2, hints_y, " Enter confirm \u{2502} Esc cancel",
        Style::new().fg(t.text_muted).bg(t.background));
}

fn render_provider_list(buf: &mut CellBuffer, area: Rect, app: &App, title: &str, show_key_status: bool) {
    let t = &app.theme;
    let current = app.provider.as_str();
    let filter = app.provider_filter.to_lowercase();

    let cat_order: &[(&str, &str)] = &[
        ("cloud", "Cloud Providers"),
        ("cloud-cn", "Chinese Cloud"),
        ("inference", "Inference Platforms"),
        ("local", "Local / Self-hosted"),
    ];

    #[allow(clippy::type_complexity)]
    let mut categories: Vec<(&str, Vec<(&str, bool, bool)>)> = Vec::new();
    let mut total_items = 0usize;
    for (cat_key, cat_label) in cat_order {
        let mut items: Vec<(&str, bool, bool)> = Vec::new();
        for p in &app.available_providers {
            if p.category != *cat_key { continue; }
            if !filter.is_empty() && !p.name.to_lowercase().contains(&filter) && !p.default_model.to_lowercase().contains(&filter) {
                continue;
            }
            items.push((&p.name, p.has_key, p.needs_api_key));
        }
        total_items += items.len();
        if !items.is_empty() {
            categories.push((*cat_label, items));
        }
    }

    let total_rows = total_items + categories.len() * 2;
    let max_visible = (area.height / 2).saturating_sub(6).max(6) as usize;
    let modal_h = (total_rows as u16 + 5).min(max_visible as u16 + 5).min(area.height.saturating_sub(2));
    let modal_w = (area.width * 7 / 10).clamp(52u16, 72u16);
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_x = frame.inner_x;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, title, Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let mut y = frame.modal.y + 2;

    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }
    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));
    if app.provider_filter.is_empty() {
        buf.draw_str(inner_x + 2, y, "Search providers...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let display: String = app.provider_filter.chars().take(frame.inner_w.saturating_sub(4)).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cx = inner_x + 2 + display_width(&display);
        if cx < frame.modal.right() - 2 {
            buf.put_char(cx, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }
    y += 2;

    let max_y = frame.modal.bottom().saturating_sub(3);
    let mut idx = 0usize;

    for (cat_label, items) in &categories {
        if y >= max_y { break; }
        buf.draw_str(inner_x, y, &format!("\u{2500} {} ", cat_label),
            Style::new().fg(t.text_muted).bg(t.background).add_modifier(TextAttributes::bold()));
        y += 1;
        for (name, has_key, needs_key) in items {
            if y >= max_y { break; }
            let selected = idx == app.provider_picker_index;
            let is_current = *name == current;

            let key_marker = if show_key_status {
                if *needs_key {
                    if *has_key { " \u{2713}" } else { "" }
                } else {
                    " (local)"
                }
            } else {
                ""
            };
            let display = format!("{}{}", name, key_marker);

            if selected {
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
                }
                let marker = if is_current { "\u{25c6} " } else { "  " };
                buf.draw_str(inner_x, y, &format!("{}\u{25b8} {}", marker, display),
                    Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
            } else {
                let marker = if is_current { "\u{25c6} " } else { "  " };
                buf.draw_str(inner_x, y, &format!("{} {}", marker, display),
                    Style::new().fg(if is_current { t.primary } else { t.text }).bg(t.background));
            }
            y += 1;
            idx += 1;
        }
    }

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    buf.draw_str(frame.modal.x + 2, hints_y, " Enter select \u{2502} Type to search \u{2502} \u{25c6} current",
        Style::new().fg(t.text_muted).bg(t.background));
}

pub fn render_memory_editor(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let entry_count = app.memory_entries.len();
    let max_visible = 10u16;
    let visible = (entry_count as u16).min(max_visible);
    let modal_w = (area.width * 7 / 10).clamp(50, 64);
    let modal_h = (visible + 9).max(12).min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Memory ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let mut y = frame.modal.y + 2;

    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }
    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));
    if app.memory_editor_input.is_empty() {
        buf.draw_str(inner_x + 2, y, "Type to add...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let max_input = inner_w.saturating_sub(4);
        let display: String = app.memory_editor_input.chars().take(max_input).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cx = inner_x + 2 + display_width(&display);
        if cx < frame.modal.right() - 2 {
            buf.put_char(cx, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }
    y += 1;

    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    y += 1;

    let max_y = frame.modal.bottom().saturating_sub(3);
    if app.memory_entries.is_empty() {
        buf.draw_str(inner_x, y, "No entries yet. Type above to add.", Style::new().fg(t.text_muted).bg(t.background));
    } else {
        for (i, (target, content)) in app.memory_entries.iter().enumerate() {
            if y >= max_y { break; }
            let selected = i == app.memory_editor_index;
            let max_display = inner_w.saturating_sub(8);
            let display: String = content.chars().take(max_display).collect();
            let tag = if target == "user" { "[user]" } else { "[agent]" };

            if selected {
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
                }
                buf.draw_str(inner_x, y, &format!("\u{25b8} {} {}", tag, display),
                    Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
            } else {
                let tag_color = if target == "user" { t.secondary } else { t.text_muted };
                buf.draw_str(inner_x, y, &format!("  {} {}", tag, display),
                    Style::new().fg(tag_color).bg(t.background));
            }
            y += 1;
        }
    }

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    buf.draw_str(frame.modal.x + 2, hints_y, " Enter add \u{2502} d delete \u{2502} \u{2191}\u{2193} navigate ",
        Style::new().fg(t.text_muted).bg(t.background));
}

// ── Soul Editor Modal (view and modify personality) ──

pub fn render_soul_editor(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let modal_w = (area.width * 7 / 10).clamp(50, 60);
    let modal_h = 14u16;
    let modal_x = area.x + (area.width.saturating_sub(modal_w)) / 2;
    let modal_y = area.y + (area.height.saturating_sub(modal_h)) / 2;
    let modal = Rect::new(modal_x, modal_y, modal_w, modal_h);
    let inner_w = (modal.width as usize).saturating_sub(4);

    dim_background(buf, area, t.background_darker, t.text_muted);
    fill_modal_bg(buf, modal, t.background, t.text);

    let border_top = Style::new().fg(t.primary);
    let border_bot = Style::new().fg(t.border);
    draw_modal_border(buf, modal, border_top, border_bot);

    buf.draw_str(modal.x + 2, modal.y, " Soul ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    buf.draw_str(modal.right().saturating_sub(6), modal.y, " Esc ",
        Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = modal.x + 2;
    let mut y = modal.y + 2;

    if app.soul_editor_input.is_empty() {
        buf.draw_str(inner_x, y, "Default personality active", Style::new().fg(t.text_muted).bg(t.background));
    } else {
        buf.draw_str(inner_x, y, "Current personality:", Style::new().fg(t.text_muted).bg(t.background));
    }
    y += 1;

    // Editable text area
    let text_area_h = 5u16;
    let text_bg = t.background_panel;
    for ty in 0..text_area_h {
        let row_y = y + ty;
        for sx in (modal.x + 1)..(modal.right() - 1) {
            buf.put_char(sx, row_y, ' ', Style::new().bg(text_bg).fg(t.text));
        }
    }

    // Show input text, or placeholder if empty
    let display_text = if app.soul_editor_input.is_empty() {
        ""  // Empty = default personality
    } else {
        &app.soul_editor_input
    };

    let max_chars = inner_w.saturating_sub(2);
    let chars: Vec<char> = display_text.chars().collect();
    let mut row = 0u16;
    let mut col = 0usize;
    for &ch in &chars {
        if row >= text_area_h { break; }
        let cx = inner_x + 1 + col as u16;
        if cx < modal.right() - 2 {
            buf.put_char(cx, y + row, ch, Style::new().fg(t.text).bg(text_bg));
        }
        col += 1;
        if col >= max_chars {
            col = 0;
            row += 1;
        }
    }

    let cursor_row = row.min(text_area_h - 1);
    let cursor_col = col.min(max_chars.saturating_sub(1)) as u16;
    let cx = inner_x + 1 + cursor_col;
    if cx < modal.right() - 2 && cursor_row < text_area_h {
        buf.put_char(cx, y + cursor_row, '\u{2588}', Style::new().fg(t.primary).bg(text_bg));
    }

    y += text_area_h;

    for sx in (modal.x + 1)..(modal.right() - 1) {
        buf.put_char(sx, y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    y += 1;
    buf.draw_str(modal.x + 2, y, " Enter save \u{2502} Ctrl+R reset \u{2502} Type to edit ",
        Style::new().fg(t.text_muted).bg(t.background));
}

pub fn render_skill_browser(buf: &mut CellBuffer, area: Rect, app: &mut App) {
    let t = &app.theme;
    let query = app.skill_browser_filter.to_lowercase();
    let filtered: Vec<(usize, &sediman_tui_bridge::HubSkill)> = app
        .skill_browser_skills
        .iter()
        .enumerate()
        .filter(|(_, s)| {
            if query.is_empty() {
                return true;
            }
            let searchable = format!("{} {} {} {}", s.name, s.description, s.category, s.author).to_lowercase();
            searchable.contains(&query)
        })
        .collect();

    let modal_w = (area.width * 85 / 100).max(60).min(area.width.saturating_sub(4));
    let max_items_on_screen = area.height.saturating_sub(8) as usize;
    app.skill_browser_visible_rows = max_items_on_screen as u16;
    let max_visible = filtered.len().min(max_items_on_screen);
    let modal_h = (max_visible as u16 + 7).max(12).min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(
        buf,
        &format!(
            " Hub Skills ({}/{}) ",
            if query.is_empty() { app.skill_browser_skills.len() } else { filtered.len() },
            app.skill_browser_skills.len()
        ),
        Style::new().fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()),
    );
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let mut y = frame.modal.y + 2;

    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }
    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));
    if app.skill_browser_filter.is_empty() {
        buf.draw_str(
            inner_x + 2,
            y,
            "Type to filter skills...",
            Style::new().fg(t.text_muted).bg(input_bg),
        );
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let max_input = inner_w.saturating_sub(4);
        let display: String = app.skill_browser_filter.chars().take(max_input).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cx = inner_x + 2 + display_width(&display);
        if cx < frame.modal.right() - 2 {
            buf.put_char(cx, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }
    y += 1;

    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    y += 1;

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let desc_area_y = hints_sep_y.saturating_sub(2);
    let max_y = desc_area_y;

    if filtered.is_empty() {
        if app.skill_browser_skills.is_empty() {
            buf.draw_str(inner_x, y, "No skills found in hub.", Style::new().fg(t.text_muted).bg(t.background));
        } else {
            buf.draw_str(inner_x, y, "No matches for filter.", Style::new().fg(t.text_muted).bg(t.background));
        }
    } else {
        let scroll = app.skill_browser_scroll as usize;
        let visible_items: Vec<_> = filtered.iter().skip(scroll).collect();
        for (row_idx, &(orig_idx, skill)) in visible_items.iter().enumerate() {
            let row_y = y + row_idx as u16;
            if row_y >= max_y {
                break;
            }
            let selected = *orig_idx == app.skill_browser_selected;
            let is_installed = app.skill_browser_installed.contains(&skill.name);
            let badge_w = if is_installed { 13 } else { 0 };
            let max_name = inner_w.saturating_sub(6 + badge_w);
            let name_display: String = truncate_str(&skill.name, max_name).to_string();
            let badge = if is_installed { " \u{2713}installed" } else { "" };

            if selected {
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, row_y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
                }
                buf.draw_str(
                    inner_x,
                    row_y,
                    &format!("\u{25b8} {}{}", name_display, badge),
                    Style::new()
                        .bg(t.primary)
                        .fg(t.background_darker)
                        .add_modifier(TextAttributes::bold()),
                );
            } else {
                let name_style = if is_installed {
                    Style::new().fg(t.secondary).bg(t.background)
                } else {
                    Style::new().fg(t.text).bg(t.background)
                };
                buf.draw_str(inner_x, row_y, &format!("  {}{}", name_display, badge), name_style);
            }
        }

        let sep_y = desc_area_y;
        for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
            buf.put_char(sx, sep_y, '\u{2500}', Style::new().fg(t.border_dim));
        }

        let preview_y = sep_y + 1;
        if let Some(&(_, selected_skill)) = filtered.get(app.skill_browser_selected) {
            let max_desc = inner_w.saturating_sub(4);
            let desc = truncate_str(&selected_skill.description, max_desc);
            buf.draw_str(inner_x, preview_y, desc, Style::new().fg(t.text).bg(t.background));
        }
    }

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    buf.draw_str(
        frame.modal.x + 2,
        hints_y,
        " Enter install \u{2502} d uninstall \u{2502} i info \u{2502} \u{2191}\u{2193} navigate \u{2502} Type to filter ",
        Style::new().fg(t.text_muted).bg(t.background),
    );
}

pub fn render_theme_picker(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let modal_w = (area.width as usize * 6 / 10).clamp(36, 50) as u16;
    let modal_h = (app.theme_picker_names.len().min(14) as u16 + 6).clamp(10, 24);

    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Themes ", Style::new().fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc close ", Style::new().fg(t.text_muted).bg(t.background));

    let list_start = frame.modal.y + 2;
    let inner_x = frame.modal.x + 2;

    for (i, name) in app.theme_picker_names.iter().enumerate() {
        let row_y = list_start + i as u16;
        if row_y >= frame.modal.bottom().saturating_sub(3) { break; }

        let is_current = *name == app.theme_name;
        let is_selected = i == app.theme_picker_selected;

        let (marker, row_style) = if is_selected {
            ("\u{25b8}", Style::new().fg(t.background).bg(t.primary))
        } else if is_current {
            ("\u{25c6}", Style::new().fg(t.secondary).bg(t.background))
        } else {
            (" ", Style::new().fg(t.text).bg(t.background))
        };

        buf.draw_str(inner_x, row_y, marker, row_style);

        let label = if is_current { format!(" {} (current)", name) } else { format!(" {}", name) };
        buf.draw_str(inner_x + 2, row_y, &label, row_style);

        if let Some(theme) = sediman_tui_core::styling::load_theme(name) {
            let swatches = theme.swatch_colors();
            let swatch_x = frame.modal.right().saturating_sub(12);
            for (si, &color) in swatches.iter().enumerate() {
                let sx = swatch_x + si as u16 * 2;
                let s = Style::new().fg(color).bg(if is_selected { t.primary } else { t.background });
                buf.draw_str(sx, row_y, "\u{2588}\u{2588}", s);
            }
        }
    }

    let sep_y = frame.modal.bottom().saturating_sub(3);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }

    let hints_y = frame.modal.bottom().saturating_sub(2);
    buf.draw_str(frame.modal.x + 2, hints_y,
        " \u{2191}\u{2193} navigate \u{2502} Enter select \u{2502} Esc cancel ",
        Style::new().fg(t.text_muted).bg(t.background));
}

pub fn render_schedule_browser(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let modal_w = (area.width * 7 / 10).clamp(52, 72);
    let content_rows = app.schedule_jobs.len().min(8);
    let modal_h = (content_rows as u16 + 9).max(10).min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, &format!(" Schedule ({}) ", app.schedule_jobs.len()), Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let mut y = frame.modal.y + 2;

    // Input row
    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }
    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));
    if app.schedule_input.is_empty() {
        buf.draw_str(inner_x + 2, y, "<cron> <task> to add...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let max_input = inner_w.saturating_sub(4);
        let display: String = app.schedule_input.chars().take(max_input).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cx = inner_x + 2 + display_width(&display);
        if cx < frame.modal.right() - 2 {
            buf.put_char(cx, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }
    y += 2;

    let max_y = frame.modal.bottom().saturating_sub(3);

    if app.schedule_jobs.is_empty() {
        buf.draw_str(inner_x, y, "No scheduled jobs. Type above to add one.", Style::new().fg(t.text_muted).bg(t.background));
    } else {
        for (i, job) in app.schedule_jobs.iter().enumerate() {
            if y >= max_y { break; }
            let selected = i == app.schedule_selected;
            let status_icon = if job.enabled { "\u{25cf}" } else { "\u{25cb}" };
            let max_task = inner_w.saturating_sub(12);
            let task_display = truncate_str(&job.task, max_task);

            if selected {
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
                }
                buf.draw_str(inner_x, y, &format!("{} {} {}", status_icon, task_display, job.cron_expr),
                    Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
            } else {
                buf.draw_str(inner_x, y, &format!("{} {} {}", status_icon, task_display, job.cron_expr),
                    Style::new().fg(if job.enabled { t.text } else { t.text_muted }).bg(t.background));
            }

            // Next run on second line
            if y + 1 < max_y {
                if let Some(ref next) = job.next_run {
                    y += 1;
                    buf.draw_str(inner_x + 2, y, &format!("next: {}", next),
                        Style::new().fg(t.text_muted).bg(t.background));
                }
            }
            y += 1;
        }
    }

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    buf.draw_str(frame.modal.x + 2, hints_y,
        " Enter toggle/add \u{2502} d/\u{232b} delete \u{2502} \u{2191}\u{2193} navigate \u{2502} Type to add ",
        Style::new().fg(t.text_muted).bg(t.background));
}

pub fn render_doctor_modal(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;

    let (checks, cursor, scroll, installing, install_output) = match &app.active_modal {
        Some(crate::app::AppModal::Doctor { checks, cursor, scroll, installing, install_output }) => {
            (checks.clone(), *cursor, *scroll, *installing, install_output.clone())
        }
        _ => return,
    };

    let display_rows = doctor_display_rows(&checks);
    let output_rows = if install_output.is_empty() { 0 } else { install_output.len().min(6) };
    let modal_w = (area.width * 8 / 10).clamp(56, 76);
    let modal_h = (display_rows as u16 + 7 + output_rows as u16)
        .max(14u16)
        .min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Doctor ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " q to close ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let mut y = frame.modal.y + 2;

    let scroll_us = scroll as usize;
    let max_y = frame.modal.bottom().saturating_sub(3 + output_rows as u16);

    let cat_style = Style::new().fg(t.accent).bg(t.background).add_modifier(TextAttributes::bold());
    let name_style = Style::new().fg(t.text).bg(t.background);

    let mut line_idx = 0usize;
    let mut prev_cat = "";

    for (ci, check) in checks.iter().enumerate() {
        if line_idx >= scroll_us && check.category != prev_cat {
            if y >= max_y { break; }
            if !prev_cat.is_empty() {
                y += 1;
                line_idx += 1;
                if line_idx < scroll_us || y >= max_y {
                    prev_cat = check.category;
                    continue;
                }
            }
            buf.draw_str(inner_x, y, &format!("\u{2500} {} ", check.category), cat_style);
            y += 1;
            line_idx += 1;
        }
        prev_cat = check.category;

        if y >= max_y { break; }
        if line_idx < scroll_us {
            line_idx += 1;
            continue;
        }

        let selected = ci == cursor;
        let (icon, icon_color) = match check.status {
            DoctorStatus::Pass => ("\u{2713}", t.success),
            DoctorStatus::Warn => ("\u{26a0}", t.warning),
            DoctorStatus::Fail => ("\u{2717}", t.error),
            DoctorStatus::Pending => ("\u{25cb}", t.text_muted),
        };

        let name_w: u16 = 20;
        let name_display = truncate_str(check.name, name_w as usize);
        let max_msg = inner_w.saturating_sub(name_w as usize + 6);
        let msg = truncate_str(&check.message, max_msg);

        if selected {
            for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
            }
            let marker = if check.install_cmd.is_some() { "\u{25b8}" } else { " " };
            buf.draw_str(inner_x, y, &format!("{} ", marker),
                Style::new().bg(t.primary).fg(t.background_darker));
            buf.draw_str(inner_x + 2, y, icon,
                Style::new().fg(icon_color).bg(t.primary).add_modifier(TextAttributes::bold()));
            buf.draw_str(inner_x + 4, y, &format!("{:<width$}", name_display, width = name_w as usize),
                Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
            buf.draw_str(inner_x + 4 + name_w, y, msg,
                Style::new().bg(t.primary).fg(t.background_darker));
        } else {
            buf.draw_str(inner_x, y, "  ",
                Style::new().fg(t.text).bg(t.background));
            buf.draw_str(inner_x + 2, y, icon,
                Style::new().fg(icon_color).bg(t.background));
            buf.draw_str(inner_x + 4, y, &format!("{:<width$}", name_display, width = name_w as usize),
                name_style);
            buf.draw_str(inner_x + 4 + name_w, y, msg,
                Style::new().fg(t.text_muted).bg(t.background));
        }
        y += 1;
        line_idx += 1;
    }

    if !install_output.is_empty() || installing {
        if y < max_y { y = max_y; }
        let sep_y = y;
        for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
            buf.put_char(sx, sep_y, '\u{2500}', Style::new().fg(t.border_dim));
        }
        y += 1;

        if installing {
            buf.draw_str(inner_x, y, "\u{25cf} Running...", Style::new().fg(t.warning).bg(t.background));
            y += 1;
        }

        for line in install_output.iter().rev().take(output_rows).rev() {
            if y >= frame.modal.bottom().saturating_sub(2) { break; }
            let max_line = inner_w.saturating_sub(2);
            let display = truncate_str(line, max_line);
            let line_style = if line.starts_with("error") || line.starts_with("failed") {
                Style::new().fg(t.error).bg(t.background)
            } else if line.starts_with("done") {
                Style::new().fg(t.success).bg(t.background)
            } else {
                Style::new().fg(t.text_muted).bg(t.background)
            };
            buf.draw_str(inner_x, y, display, line_style);
            y += 1;
        }
    }

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    let hint = if installing {
        " Installing... please wait "
    } else {
        " \u{24a3} install \u{2502} r re-check \u{2502} \u{2191}\u{2193} navigate \u{2502} q close "
    };
    buf.draw_str(frame.modal.x + 2, hints_y, hint,
        Style::new().fg(t.text_muted).bg(t.background));
}

fn doctor_display_rows(checks: &[crate::app::DoctorCheck]) -> usize {
    let mut rows = 0usize;
    let mut prev_cat = "";
    for check in checks {
        if check.category != prev_cat {
            if !prev_cat.is_empty() {
                rows += 1;
            }
            rows += 1;
            prev_cat = check.category;
        }
        rows += 1;
    }
    rows
}
