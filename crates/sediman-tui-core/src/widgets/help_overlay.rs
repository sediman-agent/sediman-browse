use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
    Frame,
};

pub struct HelpOverlay<'a> {
    pub categories: &'a [(&'a str, &'a [&'a str])],
}

impl<'a> HelpOverlay<'a> {
    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let mut lines = Vec::new();
        lines.push(Line::from(Span::styled(
            "Commands",
            Style::new()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )));
        lines.push(Line::from(Span::raw("")));

        for (category, cmds) in self.categories {
            lines.push(Line::from(Span::styled(
                format!("[{}]", category),
                Style::new().fg(Color::Yellow).add_modifier(Modifier::DIM),
            )));
            for cmd in *cmds {
                lines.push(Line::from(Span::styled(
                    format!("  {}", cmd),
                    Style::new().fg(Color::White),
                )));
            }
            lines.push(Line::from(Span::raw("")));
        }

        lines.push(Line::from(Span::styled(
            "Or just type a task and press Enter to run it.",
            Style::new().fg(Color::DarkGray),
        )));

        let paragraph = Paragraph::new(lines).wrap(Wrap { trim: false });
        frame.render_widget(paragraph, area);
    }
}
