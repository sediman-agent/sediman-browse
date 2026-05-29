use sediman_tui_core::renderer::{CellBuffer, Rect, Style, TextAttributes};
use crate::app::App;

pub fn render_banner(buf: &mut CellBuffer, area: Rect, app: &App) {
    let t = &app.theme;
    let mut y = area.y + 1;

    let muted = Style::new().fg(t.text_muted);
    let success = Style::new().fg(t.success);
    let text_style = Style::new().fg(t.text);

    let gradient: [sediman_tui_core::renderer::Color; 5] = [
        t.primary,
        t.warning,
        t.accent,
        t.secondary,
        t.info,
    ];

    if y >= area.bottom() { return; }
    let top_border = " \u{25c6}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{25c6}";
    buf.draw_str(area.x, y, top_border, Style::new().fg(t.border));
    y += 2;

    let logo: [(&str, sediman_tui_core::renderer::Color); 5] = [
        ("  _____ ______ _____ _____ __  __          _   _ ", gradient[0]),
        (" / ____|  ____|  __ \\_   _|  \\/  |   /\\   | \\ | |", gradient[1]),
        ("| (___ | |__  | |  | || | | \\  / |  /  \\  |  \\| |", gradient[2]),
        (" \\___ \\|  __| | |  | || | | |\\/| | / /\\ \\ | . ` |", gradient[3]),
        (" ____) | |____| |__| || |_| |  | |/ ____ \\| |\\  |", gradient[4]),
    ];

    for (line, color) in &logo {
        if y >= area.bottom() { return; }
        buf.draw_str(area.x + 2, y, line, Style::new().fg(*color).add_modifier(TextAttributes::bold()));
        y += 1;
    }

    if y >= area.bottom() { return; }
    buf.draw_str(area.x + 2, y, "|_____/|______|_____/_____|_|  |_/_/    \\_\\_| \\_|", Style::new().fg(gradient[4]).add_modifier(TextAttributes::bold()));
    y += 2;

    if y >= area.bottom() { return; }
    buf.draw_str(area.x + 4, y, "AI-Powered Browser Automation", Style::new().fg(t.accent).add_modifier(TextAttributes::italic()));
    y += 1;

    if y >= area.bottom() { return; }
    let ver = format!("v{}", env!("CARGO_PKG_VERSION"));
    buf.draw_str(area.x + 4, y, &ver, muted);
    y += 1; y += 1;

    if y >= area.bottom() { return; }
    let browser_str = if app.headless { "headless" } else { "headed + vision" };
    buf.draw_str(area.x + 4, y, "\u{25cf} ", success);
    buf.draw_str(area.x + 6, y, &format!("Browser: {}", browser_str), text_style);
    y += 1;

    if y >= area.bottom() { return; }
    let cwd = std::env::current_dir()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| ".".into());
    let cwd_display = if cwd.chars().count() > 50 {
        let tail: String = cwd.chars().skip(cwd.chars().count() - 47).collect();
        format!("...{}", tail)
    } else {
        cwd
    };
    buf.draw_str(area.x + 4, y, "\u{25ce} ", Style::new().fg(t.secondary));
    buf.draw_str(area.x + 6, y, &format!("Path: {}", cwd_display), text_style);
    y += 2;

    if y >= area.bottom() { return; }
    let bot_border = " \u{25c6}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{2501}\u{25c6}";
    buf.draw_str(area.x, y, bot_border, Style::new().fg(t.border));
    y += 2;

    if y >= area.bottom() { return; }
    buf.draw_str(area.x + 4, y, "Type a task or /help to begin.", muted);
}

pub fn render_idle(buf: &mut CellBuffer, area: Rect, app: &App) {
    buf.draw_str(area.x + 2, area.y, "ready \u{2014} type a task or /help",
        Style::new().fg(app.theme.text_muted).add_modifier(TextAttributes::italic()));
}
