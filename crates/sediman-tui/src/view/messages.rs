use sediman_tui_core::renderer::{CellBuffer, Color, Line, Rect, Style, TextAttributes, display_width};
use sediman_tui_core::markdown;

use crate::app::{App, ChatMessage};

struct PhaseInfo {
    name: &'static str,
    color_fn: fn(&App) -> Color,
    symbol: &'static str,
}

const PHASES: &[PhaseInfo] = &[
    PhaseInfo { name: "planning", color_fn: |a| a.theme.warning, symbol: "\u{25c6}" },
    PhaseInfo { name: "executing", color_fn: |a| a.theme.primary, symbol: "\u{25b8}" },
    PhaseInfo { name: "observing", color_fn: |a| a.theme.secondary, symbol: "\u{25cb}" },
    PhaseInfo { name: "reflecting", color_fn: |a| a.theme.info, symbol: "\u{25c6}" },
    PhaseInfo { name: "delegating", color_fn: |a| a.theme.success, symbol: "\u{25c7}" },
    PhaseInfo { name: "done", color_fn: |a| a.theme.success, symbol: "\u{2713}" },
    PhaseInfo { name: "failed", color_fn: |a| a.theme.error, symbol: "\u{2717}" },
    PhaseInfo { name: "Interrupted", color_fn: |a| a.theme.warning, symbol: "\u{26a0}" },
];

pub fn render_messages(buf: &mut CellBuffer, area: Rect, app: &mut App) {
    if app.show_banner && app.messages.is_empty() {
        super::banner::render_banner(buf, area, app);
        return;
    }

    if app.messages.is_empty() {
        super::banner::render_idle(buf, area, app);
        return;
    }

    let max_width = area.width.saturating_sub(6) as usize; // 3px padding each side
    let mut lines: Vec<(String, Style)> = Vec::new();

    // ── Compact running indicator ──
    if app.agent_running {
        let spinner = app.spinner_char();
        let elapsed = app.agent_start.elapsed().as_secs();
        let elapsed_str = format_elapsed(elapsed);
        let step_count = app.step_log.len();
        let last_step = app.step_log.last().map(|s| truncate_end(s, max_width.saturating_sub(18))).unwrap_or_else(|| "Starting...".into());

        lines.push((String::new(), Style::new()));
        lines.push((format!("  {} Working \u{2026} {} \u{00b7} {} steps", spinner, elapsed_str, step_count),
            Style::new().fg(app.theme.primary).add_modifier(TextAttributes::bold())));
        lines.push((format!("    {}", last_step),
            Style::new().fg(app.theme.text_muted)));
    }

    // ── Render all messages ──
    for msg in &app.messages {
        match msg {
            ChatMessage::User { text, task_num } => {
                lines.push((String::new(), Style::new()));
                // User message: bold prompt prefix
                lines.push((format!("  \u{276f} Task #{}", task_num),
                    Style::new().fg(app.theme.secondary).add_modifier(TextAttributes::bold())));
                push_wrapped(&mut lines, &format!("    {}", text), Style::new().fg(app.theme.text), max_width);
            }
            ChatMessage::Agent { steps, result, success, elapsed_secs, skill_created, scheduled_job, .. } => {
                // ── Steps: show only last 3 to keep it clean ──
                let show_steps: Vec<_> = if steps.len() > 3 {
                    steps.iter().rev().take(3).collect::<Vec<_>>().into_iter().rev().collect()
                } else {
                    steps.iter().collect()
                };

                if !show_steps.is_empty() && result.is_none() {
                    lines.push((String::new(), Style::new()));
                }

                // Collapsed step count if many
                if steps.len() > 3 {
                    lines.push((format!("    \u{2026} {} earlier steps", steps.len() - 3),
                        Style::new().fg(app.theme.text_muted)));
                }

                for step in &show_steps {
                    let (style, symbol) = parse_step_style(step, app);
                    let truncated = truncate_end(step, max_width.saturating_sub(6));
                    lines.push((format!("    {} {}", symbol, truncated), style));
                }

                // ── Result section ──
                if let Some(res) = result {
                    lines.push((String::new(), Style::new()));
                    let icon = if *success { "\u{2713}" } else { "\u{2717}" };
                    let color = if *success { app.theme.success } else { app.theme.error };
                    let elapsed_str = format_elapsed(*elapsed_secs);
                    lines.push((format!("  {} Done \u{00b7} {}", icon, elapsed_str),
                        Style::new().fg(color).add_modifier(TextAttributes::bold())));

                    if !res.is_empty() {
                        lines.push((String::new(), Style::new()));
                        // Render markdown result with proper padding
                        let md_lines = markdown::render_markdown(res);
                        for md_line in &md_lines {
                            let (text, style) = flatten_line(md_line, app);
                            if !text.is_empty() {
                                push_wrapped(&mut lines, &format!("    {}", text), style, max_width);
                            } else {
                                lines.push((String::new(), Style::new()));
                            }
                        }
                    }

                    if let Some(skill) = skill_created {
                        lines.push((String::new(), Style::new()));
                        lines.push((format!("    \u{2726} Skill created: {}", skill), Style::new().fg(app.theme.info)));
                    }
                    if let Some(job) = scheduled_job {
                        lines.push((format!("    \u{25c8} Scheduled: {}", job), Style::new().fg(app.theme.secondary)));
                    }
                }
            }
            ChatMessage::System { text } => {
                lines.push((String::new(), Style::new()));
                push_wrapped(&mut lines, &format!("  {}", text), Style::new().fg(app.theme.text_muted), max_width);
            }
            ChatMessage::Error { text } => {
                lines.push((String::new(), Style::new()));
                push_wrapped(&mut lines, &format!("  \u{2717} {}", text), Style::new().fg(app.theme.error), max_width);
            }
        }
    }

    // ── Render lines with scroll ──
    let total_lines = lines.len() as u16;
    let visible_height = area.height.saturating_sub(2).max(1);
    let max_scroll = total_lines.saturating_sub(visible_height);

    if app.auto_scroll {
        app.scroll_offset = 0;
    }
    let scroll = app.scroll_offset.min(max_scroll);

    // Fill background
    for sy in area.y..area.bottom() {
        for sx in area.x..area.right() {
            buf.put_char(sx, sy, ' ', Style::new().bg(app.theme.background));
        }
    }

    let mut y = area.y;
    for (i, (text, style)) in lines.iter().enumerate() {
        let i = i as u16;
        if i < scroll {
            continue;
        }
        if y >= area.bottom() {
            break;
        }
        if text.is_empty() {
            y += 1;
            continue;
        }
        buf.draw_str(area.x + 2, y, text, *style);
        y += 1;
    }

    // Scroll indicator
    if total_lines > visible_height {
        let pct = if max_scroll > 0 {
            (scroll as f64 / max_scroll as f64 * 100.0) as u16
        } else {
            0
        };
        let indicator = format!(" {}% ", pct);
        let ix = area.right().saturating_sub(display_width(&indicator));
        let iy = area.bottom().saturating_sub(1);
        if iy > area.y && ix < area.right() {
            buf.draw_str(ix, iy, &indicator, Style::new().fg(app.theme.text_muted));
        }
    }
}

/// Truncate a string to max_len, adding "..." if truncated.
fn truncate_end(s: &str, max_len: usize) -> String {
    if max_len < 4 {
        return s.chars().take(max_len).collect();
    }
    if s.len() <= max_len {
        return s.to_string();
    }
    let end = s.char_indices().take_while(|(i, _)| *i < max_len - 3).last();
    match end {
        Some((i, c)) => {
            let cut = i + c.len_utf8();
            format!("{}...", &s[..cut])
        }
        None => format!("{}...", &s[..max_len.saturating_sub(3)]),
    }
}

/// Push a line, wrapping it into multiple lines if it exceeds max_width.
fn push_wrapped(lines: &mut Vec<(String, Style)>, text: &str, style: Style, max_width: usize) {
    if max_width < 4 {
        lines.push((text.to_string(), style));
        return;
    }

    let text_width = display_width(text) as usize;
    if text_width <= max_width {
        lines.push((text.to_string(), style));
        return;
    }

    let chars: Vec<char> = text.chars().collect();
    let inner_width = max_width.saturating_sub(2);
    let mut first = true;
    let mut pos = 0;

    while pos < chars.len() {
        let limit = if first { max_width } else { inner_width };
        let mut end = (pos + limit).min(chars.len());

        // Try to break at a space or punctuation
        if end < chars.len() {
            for i in (pos..end).rev() {
                if chars[i] == ' ' || chars[i] == '-' || chars[i] == ',' || chars[i] == ')' {
                    end = i + 1;
                    break;
                }
            }
        }

        let chunk: String = chars[pos..end].iter().collect();
        let line = if first { chunk } else { format!("    {}", chunk) };
        lines.push((line, style));

        pos = end;
        first = false;
        while pos < chars.len() && chars[pos] == ' ' {
            pos += 1;
        }
    }
}

pub fn format_elapsed(secs: u64) -> String {
    if secs >= 3600 {
        format!("{}h {:02}m", secs / 3600, (secs % 3600) / 60)
    } else if secs >= 60 {
        format!("{}m {:02}s", secs / 60, secs % 60)
    } else {
        format!("{}s", secs)
    }
}

fn parse_step_style(step: &str, app: &App) -> (Style, &'static str) {
    for info in PHASES {
        if step.contains(info.name) {
            let color = (info.color_fn)(app);
            return (Style::new().fg(color), info.symbol);
        }
    }

    let t = &app.theme;
    if step.contains("done") || step.starts_with('\u{2713}') {
        return (Style::new().fg(t.success), "\u{2713}");
    }
    if step.contains("fail") || step.starts_with('\u{2717}') {
        return (Style::new().fg(t.error), "\u{2717}");
    }

    (Style::new().fg(t.text), "\u{2022}")
}

pub fn detect_phase(step: &str) -> Option<&str> {
    for info in PHASES {
        if step.contains(info.name) {
            return Some(info.name);
        }
    }
    None
}

fn flatten_line(line: &Line, app: &App) -> (String, Style) {
    if line.spans.is_empty() {
        return (String::new(), Style::new());
    }

    let text: String = line.spans.iter().map(|s| s.text.as_str()).collect();
    let style = line.spans.first()
        .map(|s| s.style)
        .unwrap_or_else(|| Style::new().fg(app.theme.text));

    (text, style)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::App;
    use sediman_tui_bridge::ApiClient;

    fn make_app() -> App {
        App::new("test".into(), Some("gpt-4".into()), None, true, ApiClient::new("/tmp/test.sock"))
    }

    #[test]
    fn test_format_elapsed_zero() {
        assert_eq!(format_elapsed(0), "0s");
    }

    #[test]
    fn test_format_elapsed_seconds() {
        assert_eq!(format_elapsed(45), "45s");
    }

    #[test]
    fn test_format_elapsed_minutes() {
        assert_eq!(format_elapsed(125), "2m 05s");
    }

    #[test]
    fn test_format_elapsed_hours() {
        assert_eq!(format_elapsed(3661), "1h 01m");
    }

    #[test]
    fn test_format_elapsed_large() {
        assert_eq!(format_elapsed(86400), "24h 00m");
    }

    #[test]
    fn test_format_elapsed_boundary_minute() {
        assert_eq!(format_elapsed(59), "59s");
    }

    #[test]
    fn test_format_elapsed_exact_minute() {
        assert_eq!(format_elapsed(60), "1m 00s");
    }

    #[test]
    fn test_format_elapsed_boundary_hour() {
        assert_eq!(format_elapsed(3599), "59m 59s");
    }

    #[test]
    fn test_format_elapsed_exact_hour() {
        assert_eq!(format_elapsed(3600), "1h 00m");
    }

    #[test]
    fn test_detect_phase_known() {
        assert_eq!(detect_phase("planning routes"), Some("planning"));
        assert_eq!(detect_phase("executing click"), Some("executing"));
        assert_eq!(detect_phase("observing results"), Some("observing"));
        assert_eq!(detect_phase("reflecting on output"), Some("reflecting"));
        assert_eq!(detect_phase("delegating task"), Some("delegating"));
        assert_eq!(detect_phase("done!"), Some("done"));
        assert_eq!(detect_phase("failed!"), Some("failed"));
        assert_eq!(detect_phase("Interrupted"), Some("Interrupted"));
    }

    #[test]
    fn test_detect_phase_unknown() {
        assert_eq!(detect_phase("unknown phase"), None);
        assert_eq!(detect_phase(""), None);
    }

    #[test]
    fn test_parse_step_style_known_phases() {
        let app = make_app();
        let (_, symbol) = parse_step_style("planning", &app);
        assert_eq!(symbol, "\u{25c6}");

        let (_, symbol) = parse_step_style("executing", &app);
        assert_eq!(symbol, "\u{25b8}");

        let (_, symbol) = parse_step_style("done", &app);
        assert_eq!(symbol, "\u{2713}");

        let (_, symbol) = parse_step_style("failed", &app);
        assert_eq!(symbol, "\u{2717}");
    }

    #[test]
    fn test_parse_step_style_unknown() {
        let app = make_app();
        let (_, symbol) = parse_step_style("something random", &app);
        assert_eq!(symbol, "\u{2022}");
    }

    #[test]
    fn test_push_wrapped_short_line() {
        let mut lines = Vec::new();
        push_wrapped(&mut lines, "hello", Style::new(), 80);
        assert_eq!(lines.len(), 1);
        assert_eq!(lines[0].0, "hello");
    }

    #[test]
    fn test_push_wrapped_long_line() {
        let mut lines = Vec::new();
        let long = "abcdefghijklmnopqrstuvwxyz";
        push_wrapped(&mut lines, long, Style::new(), 10);
        assert!(lines.len() > 1, "Should wrap into multiple lines");
        assert!(lines[0].0.starts_with("abcdefg"));
    }

    #[test]
    fn test_truncate_end_short() {
        assert_eq!(truncate_end("hello", 10), "hello");
    }

    #[test]
    fn test_truncate_end_long() {
        assert_eq!(truncate_end("abcdefghijklmnopqrstuvwxyz", 10), "abcdefg...");
    }
}
