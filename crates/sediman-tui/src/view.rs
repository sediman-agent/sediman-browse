use ratatui::{
    layout::{Alignment, Constraint, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph, Wrap},
    Frame,
};

use crate::app::App;

pub fn render(frame: &mut Frame, app: &mut App) {
    let area = frame.area();
    let input_height = 3u16;

    let chunks = Layout::vertical([
        Constraint::Length(2),
        Constraint::Min(0),
        Constraint::Length(1),
        Constraint::Length(input_height),
    ])
    .areas::<4>(area);

    render_title_bar(frame, chunks[0], app);
    render_main(frame, chunks[1], app);
    render_status_bar(frame, chunks[2], app);
    render_input(frame, chunks[3], app);
}

fn render_title_bar(frame: &mut Frame, area: Rect, app: &App) {
    let model = app.model.as_deref().unwrap_or("default");
    let title = format!(" sediman  {} ", model);
    let paragraph = Paragraph::new(Line::from(Span::styled(
        title,
        Style::new()
            .fg(Color::White)
            .bg(Color::Blue)
            .add_modifier(Modifier::BOLD),
    )))
    .style(Style::new().bg(Color::Blue));
    frame.render_widget(paragraph, area);
}

fn render_main(frame: &mut Frame, area: Rect, app: &App) {
    if app.show_help {
        render_help(frame, area);
    } else if app.show_banner {
        render_banner(frame, area);
    } else if app.agent_running || !app.step_log.is_empty() {
        render_progress(frame, area, app);
    } else if let Some(result) = &app.last_result {
        render_result(frame, area, result);
    } else {
        render_idle(frame, area);
    }
}

fn render_banner(frame: &mut Frame, area: Rect) {
    let lines = vec![
        Line::from(Span::styled(
            "  sediman",
            Style::new()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::styled(
            "  a self-improving browser agent",
            Style::new().fg(Color::DarkGray).italic(),
        )),
        Line::from(Span::raw("")),
        Line::from(Span::styled(
            "  type /help for commands, /exit to quit",
            Style::new().fg(Color::DarkGray),
        )),
        Line::from(Span::styled(
            "  or just type a task and press Enter",
            Style::new().fg(Color::DarkGray),
        )),
    ];
    let paragraph = Paragraph::new(lines);
    frame.render_widget(paragraph, area);
}

fn render_idle(frame: &mut Frame, area: Rect) {
    let lines = vec![
        Line::from(Span::styled(
            "  ready — type a task or /help",
            Style::new().fg(Color::DarkGray).italic(),
        )),
    ];
    let paragraph = Paragraph::new(lines);
    frame.render_widget(paragraph, area);
}

fn render_progress(frame: &mut Frame, area: Rect, app: &App) {
    let elapsed = app.agent_start.elapsed().as_secs();
    let elapsed_str = if elapsed >= 60 {
        format!("{}m {}s", elapsed / 60, elapsed % 60)
    } else {
        format!("{}s", elapsed)
    };

    let title = format!(" {}  {}  {}", "⏳", elapsed_str, app.spinner_text);

    let lines: Vec<Line> = app
        .step_log
        .iter()
        .rev()
        .take(100)
        .rev()
        .map(|s| {
            let (style, prefix) = if s.starts_with("✓") || s.starts_with("◆") {
                (Style::new().green(), " ")
            } else if s.starts_with("✗") || s.starts_with("⚠") {
                (Style::new().red(), " ")
            } else if s.starts_with("ℹ") {
                (Style::new().yellow(), " ")
            } else {
                (Style::new().white(), " ")
            };
            Line::from(Span::styled(format!("{}{}", prefix, s), style))
        })
        .collect();

    let paragraph = Paragraph::new(lines)
        .block(
            Block::default()
                .title(title)
                .title_alignment(Alignment::Left)
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::new().fg(Color::Blue)),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(paragraph, area);
}

fn render_result(frame: &mut Frame, area: Rect, result: &sediman_tui_bridge::AgentResult) {
    let (icon, border_color) = if result.success {
        ("✓", Color::Green)
    } else {
        ("✗", Color::Red)
    };
    let title = format!(" {}  completed ({}s)", icon, result.elapsed_secs);

    let lines = vec![Line::from(Span::styled(
        &result.result,
        Style::new().white(),
    ))];

    let paragraph = Paragraph::new(lines)
        .block(
            Block::default()
                .title(title)
                .title_alignment(Alignment::Left)
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::new().fg(border_color)),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(paragraph, area);
}

fn render_help(frame: &mut Frame, area: Rect) {
    let categories = [
        ("general", &["/help", "/exit", "/status", "/clear", "/reset"] as &[&str]),
        ("agent", &["/model", "/models", "/compress", "/soul", "/plan"]),
        ("skills", &["/skills", "/skill <name>", "/run-skill <name>", "/record", "/stop"]),
        ("hub", &["/hub browse", "/hub search", "/hub install", "/hub info", "/hub publish"]),
        ("browser", &["/browser", "/screenshot"]),
        ("sessions", &["/sessions", "/memory", "/remember", "/resume"]),
        ("schedule", &["/schedule", "/schedule-add", "/schedule-remove"]),
        ("terminal", &["/terminal", "/color", "/rename"]),
        ("tasks", &["/delegate", "/parallel"]),
        ("utilities", &["/usage", "/doctor", "/export", "/btw"]),
    ];

    let mut lines = vec![
        Line::from(Span::styled(
            "  commands",
            Style::new().fg(Color::Cyan).add_modifier(Modifier::BOLD),
        )),
        Line::from(Span::raw("")),
    ];

    for (category, cmds) in &categories {
        lines.push(Line::from(Span::styled(
            format!("  \u{2502} {} \u{2502}", category),
            Style::new()
                .fg(Color::Yellow)
                .add_modifier(Modifier::DIM),
        )));
        for cmd in *cmds {
            lines.push(Line::from(Span::styled(
                format!("    {}", cmd),
                Style::new().white(),
            )));
        }
        lines.push(Line::from(Span::raw("")));
    }

    let paragraph = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::new().fg(Color::DarkGray)),
        )
        .wrap(Wrap { trim: false });
    frame.render_widget(paragraph, area);
}

fn render_status_bar(frame: &mut Frame, area: Rect, app: &App) {
    let mut spans = Vec::new();

    if app.agent_running {
        let elapsed = app.agent_start.elapsed().as_secs();
        let e = if elapsed >= 60 {
            format!("{}m {}s", elapsed / 60, elapsed % 60)
        } else {
            format!("{}s", elapsed)
        };
        spans.push(Span::styled(
            format!(" {} {} ", "⏳", e),
            Style::new().green().bold(),
        ));
    } else {
        spans.push(Span::styled("  idle  ", Style::new().dim()));
    }

    spans.push(Span::styled(
        format!(" {} ", app.model.as_deref().unwrap_or("default")),
        Style::new().dim(),
    ));

    let mode = app.permission.current_label();
    let mc = match mode {
        "acceptEdits" => Color::Green,
        "plan" => Color::Magenta,
        "auto" => Color::Red,
        _ => Color::White,
    };
    spans.push(Span::styled(format!(" {} ", mode), Style::new().fg(mc)));

    if let Some(ref name) = app.session_name {
        let c = match app.session_color.as_deref() {
            Some("red") => Color::Red,
            Some("blue") => Color::Blue,
            Some("green") => Color::Green,
            Some("yellow") => Color::Yellow,
            Some("purple") => Color::Magenta,
            Some("cyan") => Color::Cyan,
            _ => Color::Cyan,
        };
        spans.push(Span::styled(format!(" {} ", name), Style::new().fg(c)));
    }

    spans.push(Span::styled(
        format!(" {} tasks ", app.task_count),
        Style::new().dim(),
    ));

    let est_tokens: usize = app.step_log.iter().map(|s| s.len()).sum::<usize>() / 4;
    let pct = (est_tokens as f64 / 128_000.0).min(1.0);
    let filled = (10.0 * pct).round() as usize;
    let bar: String = "▓".chars().cycle().take(filled).collect::<String>()
        + &"░".chars().cycle().take(10 - filled).collect::<String>();
    let bc = if pct > 0.8 { Color::Red } else if pct > 0.5 { Color::Yellow } else { Color::Green };
    spans.push(Span::styled(
        format!(" [{}] {}K ", bar, est_tokens / 1000),
        Style::new().fg(bc),
    ));

    let paragraph = Paragraph::new(Line::from(spans))
        .style(Style::new().bg(Color::Blue).fg(Color::White));
    frame.render_widget(paragraph, area);
}

fn render_input(frame: &mut Frame, area: Rect, app: &mut App) {
    app.editor
        .set_prompt(&format!(" [{}] > ", app.task_count + 1));
    app.editor.render(frame, area);
}
