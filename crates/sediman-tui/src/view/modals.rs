use sediman_tui_core::renderer::{CellBuffer, Rect, Style, TextAttributes, display_width, truncate_str};
use sediman_tui_core::renderer::Color;
use crate::app::{App, ModalLineStyle};

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

pub fn render_help_modal(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;

    let modal_w = (area.width as usize * 7 / 10).max(50).min(80) as u16;
    let modal_h = (area.height as usize * 8 / 10).max(20).min(40) as u16;
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Commands Reference ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " q to close ", Style::new().fg(t.text_muted).bg(t.background));

    let categories: &[(&str, &[(&str, &str)])] = &[
        ("General", &[
            ("/help", "Show this help dialog"),
            ("/exit", "Quit sediman"),
            ("/status", "Show connection & session status"),
            ("/clear", "Clear conversation history"),
            ("/reset", "Full reset \u{2014} clear everything"),
        ]),
        ("Agent", &[
            ("/model <name>", "Switch AI model"),
            ("/models", "List available models"),
            ("/plan", "Toggle plan-only mode"),
            ("/compress", "Compress conversation context"),
            ("/soul", "Show agent personality config"),
        ]),
        ("Skills", &[
            ("/skills", "List learned skills"),
            ("/skill <name>", "Run a specific skill"),
            ("/run-skill <name>", "Alias for /skill"),
            ("/record", "Start recording a new skill"),
            ("/stop", "Stop skill recording"),
        ]),
        ("Hub", &[
            ("/hub browse", "Browse the skill hub"),
            ("/hub search <q>", "Search hub for skills"),
            ("/hub install <id>", "Install a hub skill"),
            ("/hub info <id>", "Show skill details"),
            ("/hub publish", "Publish skill to hub"),
        ]),
        ("Browser", &[
            ("/browser", "Toggle headless/headed mode"),
            ("/screenshot", "Capture browser screenshot"),
        ]),
        ("Sessions", &[
            ("/sessions", "List saved sessions"),
            ("/memory", "Show agent memory store"),
            ("/remember <text>", "Save to agent memory"),
            ("/resume <id>", "Resume a saved session"),
        ]),
        ("Schedule", &[
            ("/schedule", "List scheduled jobs"),
            ("/schedule-add", "Add a recurring job"),
            ("/schedule-remove", "Remove a scheduled job"),
        ]),
        ("Terminal", &[
            ("/terminal", "Show terminal status"),
            ("/color", "Cycle color theme"),
            ("/rename <name>", "Rename current session"),
        ]),
        ("Tasks", &[
            ("/delegate <task>", "Spawn a sub-agent task"),
            ("/parallel <a|b>", "Run tasks in parallel"),
        ]),
        ("Utilities", &[
            ("/usage", "Show token usage & cost"),
            ("/doctor", "Run diagnostics check"),
            ("/export", "Export conversation to file"),
            ("/btw", "Fun fact about sediman"),
        ]),
    ];

    let cmd_style = Style::new().fg(t.primary).bg(t.background);
    let desc_style = Style::new().fg(t.text_muted).bg(t.background);
    let cat_style = Style::new().fg(t.accent).bg(t.background).add_modifier(TextAttributes::bold());

    let inner_x = frame.inner_x;
    let inner_w = frame.inner_w;
    let mut y = frame.modal.y + 2;
    let max_y = frame.modal.bottom().saturating_sub(2);

    for (category, cmds) in categories {
        if y >= max_y { break; }
        buf.draw_str(inner_x, y, category, cat_style);
        y += 1;
        for (cmd, desc) in *cmds {
            if y >= max_y { break; }
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
        y += 1;
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
    let modal_w = (area.width as usize * 7 / 10).max(50).min(80) as u16;
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
    let max_y = frame.modal.bottom() - 1;
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
    let modal_w = (area.width * 6 / 10).max(48).min(60);
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

/// Providers shown in the picker. Others can be set via `/provider <url>`.
const KNOWN_PROVIDERS: &[&str] = &["openai", "ollama"];

pub fn render_provider_picker(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let current = app.provider.as_str();
    let modal_w = 48u16;
    let modal_h = 12u16;
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, " Provider ", Style::new()
        .fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    frame.draw_close_hint(buf, " Esc ", Style::new().fg(t.text_muted).bg(t.background));

    let inner_x = frame.inner_x;
    let mut y = frame.modal.y + 2;

    // Input field for custom URL
    let input_bg = t.background_panel;
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, ' ', Style::new().bg(input_bg).fg(t.text));
    }
    buf.draw_str(inner_x, y, "\u{276f} ", Style::new().fg(t.primary).bg(input_bg));
    if app.provider_picker_input.is_empty() {
        buf.draw_str(inner_x + 2, y, "Type custom URL...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let max_input = inner_w.saturating_sub(4);
        let display: String = app.provider_picker_input.chars().take(max_input).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cx = inner_x + 2 + display_width(&display);
        if cx < frame.modal.right() - 2 {
            buf.put_char(cx, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }
    y += 1;

    // Separator
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    y += 1;

    // Quick-select: openai, ollama
    buf.draw_str(inner_x, y, "Quick select:", Style::new().fg(t.text_muted).bg(t.background));
    y += 1;

    for (i, name) in KNOWN_PROVIDERS.iter().enumerate() {
        if y >= frame.modal.bottom().saturating_sub(3) { break; }
        let selected = i == app.provider_picker_index;
        let is_current = *name == current;

        if selected {
            for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
            }
            let marker = if is_current { "\u{25c6} " } else { "  " };
            buf.draw_str(inner_x, y, &format!("{}\u{25b8} {}", marker, name),
                Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
        } else {
            let marker = if is_current { "\u{25c6} " } else { "  " };
            buf.draw_str(inner_x, y, &format!("{} {}", marker, name),
                Style::new().fg(if is_current { t.primary } else { t.text }).bg(t.background));
        }
        y += 1;
    }

    let _ = y; // used in loop above, last increment not read

    let hints_sep_y = frame.modal.bottom().saturating_sub(3);
    let hints_y = frame.modal.bottom().saturating_sub(2);
    for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
        buf.put_char(sx, hints_sep_y, '\u{2500}', Style::new().fg(t.border_dim));
    }
    buf.draw_str(frame.modal.x + 2, hints_y, " Enter confirm \u{2502} Type URL for other \u{2502} \u{25c6} current ",
        Style::new().fg(t.text_muted).bg(t.background));
}

pub fn render_memory_editor(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let entry_count = app.memory_entries.len();
    let max_visible = 10u16;
    let visible = (entry_count as u16).min(max_visible);
    let modal_w = (area.width * 7 / 10).max(50).min(64);
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
    let modal_w = (area.width * 7 / 10).max(50).min(60);
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
