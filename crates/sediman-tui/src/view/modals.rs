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

/// Rounded border (╭╮╰╯) — used by the model dialog, matching OpenCode's lipgloss.RoundedBorder().
pub fn draw_rounded_border(buf: &mut CellBuffer, modal: Rect, style: Style) {
    buf.put_char(modal.x, modal.y, '\u{256d}', style);           // ╭
    buf.put_char(modal.right() - 1, modal.y, '\u{256e}', style);  // ╮
    buf.put_char(modal.x, modal.bottom() - 1, '\u{2570}', style); // ╰
    buf.put_char(modal.right() - 1, modal.bottom() - 1, '\u{256f}', style); // ╯
    for sx in (modal.x + 1)..(modal.right() - 1) {
        buf.put_char(sx, modal.y, '\u{2500}', style);
        buf.put_char(sx, modal.bottom() - 1, '\u{2500}', style);
    }
    for sy in (modal.y + 1)..(modal.bottom() - 1) {
        buf.put_char(modal.x, sy, '\u{2502}', style);
        buf.put_char(modal.right() - 1, sy, '\u{2502}', style);
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

/// OpenCode-style model dialog — 1:1 copy of dialog/models.go View().
///
/// Layout (inside border):
///   y+1: title "Select {Provider} Model" (Primary, Bold)
///   y+2: blank (title bottom padding)
///   y+3..y+3+visible: model items (selected = full row Primary bg)
///   y+3+visible: scroll indicators (right-aligned, Primary, Bold)
///
/// Border: rounded corners (╭╮╰╯) with TextMuted color.
/// Width: 44 (40 inner + 2 padding + 2 border).
pub fn render_model_dialog(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;

    let provider_info = app.available_providers.get(app.model_dialog_provider_idx);
    let provider_name = provider_info.map(|p| p.name.as_str()).unwrap_or("");
    let models: Vec<&sediman_tui_bridge::ModelInfo> = app.filtered_models_for_provider(provider_name);

    const NUM_VISIBLE: usize = 10;
    const MODAL_W: u16 = 44;
    let visible = models.len().min(NUM_VISIBLE);

    // Calculate if scroll indicators are needed
    let has_scroll_up = models.len() > NUM_VISIBLE && app.model_dialog_scroll > 0;
    let has_scroll_down = models.len() > NUM_VISIBLE && app.model_dialog_scroll + NUM_VISIBLE < models.len();
    let has_prov_left = app.available_providers.len() > 1 && app.model_dialog_provider_idx > 0;
    let has_prov_right = app.available_providers.len() > 1 && app.model_dialog_provider_idx < app.available_providers.len().saturating_sub(1);
    let has_indicators = has_scroll_up || has_scroll_down || has_prov_left || has_prov_right;

    // Height: border(2) + top_pad(1) + title(1) + blank(1) + visible + indicators?(0|1) + bottom_pad(1)
    let modal_h = (6u16 + visible as u16 + if has_indicators { 1u16 } else { 0u16 })
        .max(8)
        .min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, MODAL_W, modal_h);
    let inner_x = frame.inner_x;

    // Border: rounded corners, TextMuted color (matching OpenCode exactly)
    let border_style = Style::new().fg(t.text_muted).bg(t.background);
    draw_rounded_border(buf, frame.modal, border_style);

    // y+1: title "Select {Provider} Model" — Primary, Bold
    let provider_display = if provider_name.is_empty() {
        "Select Model".to_string()
    } else {
        let mut chars = provider_name.chars();
        let first = chars.next().unwrap_or('?').to_uppercase().collect::<String>();
        let rest: String = chars.collect();
        format!("Select {}{} Model", first, rest)
    };
    buf.draw_str(inner_x, frame.modal.y + 1, &provider_display,
        Style::new().fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));

    // y+2: blank (title bottom padding — already blank from fill_modal_bg)

    // y+3..y+3+visible: model items
    let model_start_y = frame.modal.y + 3;
    let scroll = app.model_dialog_scroll;

    if models.is_empty() {
        buf.draw_str(inner_x, model_start_y, "No models available.",
            Style::new().fg(t.text_muted).bg(t.background));
    } else {
        let end_idx = (scroll + NUM_VISIBLE).min(models.len());
        for i in scroll..end_idx {
            let row_y = model_start_y + (i - scroll) as u16;
            if row_y >= frame.modal.bottom().saturating_sub(2) { break; }
            let model_info = &models[i];
            let selected = i == app.model_dialog_model_idx;
            let display = truncate_str(&model_info.name, frame.inner_w);

            if selected {
                // Full row highlight: Primary bg, Background fg, Bold (OpenCode style)
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, row_y, ' ', Style::new().bg(t.primary).fg(t.background));
                }
                buf.draw_str(inner_x, row_y, display,
                    Style::new().bg(t.primary).fg(t.background).add_modifier(TextAttributes::bold()));
            } else {
                // Plain text — no markers, no ◆ (OpenCode style)
                buf.draw_str(inner_x, row_y, display,
                    Style::new().fg(t.text).bg(t.background));
            }
        }
    }

    // Scroll indicators — bottom-right, Primary, Bold (exact copy of OpenCode getScrollIndicators)
    if has_indicators {
        let mut indicator = String::new();
        if has_prov_left { indicator = "\u{2190} ".to_string() + &indicator; }
        if has_scroll_up { indicator.push_str("\u{2191} "); }
        if has_scroll_down { indicator.push_str("\u{2193} "); }
        if has_prov_right { indicator.push('\u{2192}'); }

        let iy = model_start_y + visible as u16;
        let ix = frame.modal.right().saturating_sub(display_width(&indicator) + 2);
        buf.draw_str(ix, iy, &indicator,
            Style::new().fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));
    }
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

pub fn render_session_browser(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let query = app.session_filter.to_lowercase();
    let filtered: Vec<(usize, &sediman_tui_bridge::SessionInfo)> = app.session_list
        .iter()
        .enumerate()
        .filter(|(_, s)| {
            if query.is_empty() { return true; }
            let searchable = format!("{} {}", s.task, s.id).to_lowercase();
            searchable.contains(&query)
        })
        .collect();

    let modal_w = (area.width * 7 / 10).clamp(52, 72);
    let content_rows = filtered.len().min(8);
    let modal_h = (content_rows as u16 + 9).max(10).min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_w = frame.inner_w;

    frame.draw_border(buf, Style::new().fg(t.primary), Style::new().fg(t.border));
    frame.draw_title(buf, &format!(" Sessions ({}) ", app.session_list.len()), Style::new()
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
    if app.session_filter.is_empty() {
        buf.draw_str(inner_x + 2, y, "Type to search sessions...", Style::new().fg(t.text_muted).bg(input_bg));
        buf.put_char(inner_x + 2, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
    } else {
        let max_input = inner_w.saturating_sub(4);
        let display: String = app.session_filter.chars().take(max_input).collect();
        buf.draw_str(inner_x + 2, y, &display, Style::new().fg(t.text).bg(input_bg));
        let cx = inner_x + 2 + display_width(&display);
        if cx < frame.modal.right() - 2 {
            buf.put_char(cx, y, '\u{2588}', Style::new().fg(t.primary).bg(input_bg));
        }
    }
    y += 2;

    let max_y = frame.modal.bottom().saturating_sub(3);

    if filtered.is_empty() {
        if app.session_list.is_empty() {
            buf.draw_str(inner_x, y, "No sessions yet. Tasks will appear here.", Style::new().fg(t.text_muted).bg(t.background));
        } else {
            buf.draw_str(inner_x, y, "No matches for filter.", Style::new().fg(t.text_muted).bg(t.background));
        }
    } else {
        for (i, (_, session)) in filtered.iter().enumerate() {
            if y >= max_y { break; }
            let selected = i == app.session_selected;
            let max_task = inner_w.saturating_sub(8);
            let task_display = truncate_str(&session.task, max_task);
            let id_str = format!("#{}", session.id);

            if selected {
                for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                    buf.put_char(sx, y, ' ', Style::new().bg(t.primary).fg(t.background_darker));
                }
                buf.draw_str(inner_x, y, &format!("\u{25b8} {} {}", id_str, task_display),
                    Style::new().bg(t.primary).fg(t.background_darker).add_modifier(TextAttributes::bold()));
            } else {
                buf.draw_str(inner_x, y, &format!("  {} {}", id_str, task_display),
                    Style::new().fg(t.text).bg(t.background));
            }

            // Second line: timestamp
            if y + 1 < max_y {
                y += 1;
                let ts = truncate_str(&session.created_at, inner_w.saturating_sub(4));
                let ts_style = if selected {
                    Style::new().bg(t.primary).fg(t.background_darker)
                } else {
                    Style::new().fg(t.text_muted).bg(t.background)
                };
                buf.draw_str(inner_x + 2, y, &ts, ts_style);
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
        " Enter view \u{2502} d delete \u{2502} \u{2191}\u{2193} navigate \u{2502} Type to search ",
        Style::new().fg(t.text_muted).bg(t.background));
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

// ── Coder Picker Modal ──

const CODER_BACKENDS: &[&str] = &["internal", "claude-code", "codex", "opencode"];

/// Render the coder backend picker — same style as model dialog (rounded border, OpenCode look).
pub fn render_coder_picker(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let count = CODER_BACKENDS.len();
    let modal_w: u16 = 44;
    // Height: border(2) + top_pad(1) + title(1) + blank(1) + items + bottom_pad(1)
    let modal_h = (6u16 + count as u16).min(area.height.saturating_sub(2));
    let frame = ModalFrame::new(buf, area, app, modal_w, modal_h);
    let inner_x = frame.inner_x;

    // Border: rounded corners, TextMuted
    let border_style = Style::new().fg(t.text_muted).bg(t.background);
    draw_rounded_border(buf, frame.modal, border_style);

    // Title
    buf.draw_str(inner_x, frame.modal.y + 1, "Select Coder Backend",
        Style::new().fg(t.primary).bg(t.background).add_modifier(TextAttributes::bold()));

    // Items starting at y+3
    let start_y = frame.modal.y + 3;
    for (i, backend) in CODER_BACKENDS.iter().enumerate() {
        let row_y = start_y + i as u16;
        let selected = i == app.coder_picker_selected;
        let is_current = *backend == app.coder_backend;
        let label = if is_current { format!("{} (current)", backend) } else { backend.to_string() };
        let display = truncate_str(&label, frame.inner_w);

        if selected {
            for sx in (frame.modal.x + 1)..(frame.modal.right() - 1) {
                buf.put_char(sx, row_y, ' ', Style::new().bg(t.primary).fg(t.background));
            }
            buf.draw_str(inner_x, row_y, display,
                Style::new().bg(t.primary).fg(t.background).add_modifier(TextAttributes::bold()));
        } else {
            let fg = if is_current { t.secondary } else { t.text };
            buf.draw_str(inner_x, row_y, display, Style::new().fg(fg).bg(t.background));
        }
    }
}

