use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Wrap},
    Frame,
};

pub struct Banner<'a> {
    pub version: &'a str,
    pub headless: bool,
    pub skills: &'a [(&'a str, &'a str)],
}

impl<'a> Banner<'a> {
    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let mut lines = Vec::new();

        lines.push(Line::from(Span::styled(
            "SEDIMAN",
            Style::new()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )));
        lines.push(Line::from(Span::styled(
            format!("v{}", self.version),
            Style::new().fg(Color::DarkGray),
        )));
        lines.push(Line::from(Span::raw("")));

        let browser_mode = if self.headless {
            "headless"
        } else {
            "headed + vision"
        };
        lines.push(Line::from(Span::styled(
            format!("Browser: {}", browser_mode),
            Style::new().fg(Color::Green),
        )));
        lines.push(Line::from(Span::raw("")));

        if self.skills.is_empty() {
            lines.push(Line::from(Span::styled(
                "No saved skills yet.",
                Style::new().fg(Color::DarkGray),
            )));
        } else {
            lines.push(Line::from(Span::styled(
                "Skills:",
                Style::new().fg(Color::Yellow),
            )));
            for (name, desc) in self.skills {
                let truncated = if desc.len() > 50 {
                    format!("{}...", &desc[..47])
                } else {
                    desc.to_string()
                };
                lines.push(Line::from(Span::styled(
                    format!("  {} — {}", name, truncated),
                    Style::new().fg(Color::DarkGray),
                )));
            }
        }
        lines.push(Line::from(Span::raw("")));
        lines.push(Line::from(Span::styled(
            "Type /help for commands, /exit to quit, or just type a task.",
            Style::new().fg(Color::DarkGray),
        )));

        let paragraph = Paragraph::new(lines).wrap(Wrap { trim: false });
        frame.render_widget(paragraph, area);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_banner_version() {
        let banner = Banner {
            version: "0.1.0",
            headless: false,
            skills: &[],
        };
        assert_eq!(banner.version, "0.1.0");
    }

    #[test]
    fn test_banner_headless_mode() {
        let banner = Banner {
            version: "0.1.0",
            headless: true,
            skills: &[],
        };
        assert!(banner.headless);
    }

    #[test]
    fn test_banner_headed_mode() {
        let banner = Banner {
            version: "0.1.0",
            headless: false,
            skills: &[],
        };
        assert!(!banner.headless);
    }

    #[test]
    fn test_banner_with_skills() {
        let skills = &[("skill-a", "Does something"), ("skill-b", "Does another thing")];
        let banner = Banner {
            version: "0.1.0",
            headless: false,
            skills,
        };
        assert_eq!(banner.skills.len(), 2);
        assert_eq!(banner.skills[0].0, "skill-a");
    }

    #[test]
    fn test_banner_no_skills() {
        let banner = Banner {
            version: "0.1.0",
            headless: false,
            skills: &[],
        };
        assert!(banner.skills.is_empty());
    }

    #[test]
    fn test_banner_long_description_truncation() {
        let long_desc = "a".repeat(100);
        let skills = &[("test", long_desc.as_str())];
        let banner = Banner {
            version: "0.1.0",
            headless: false,
            skills,
        };
        let desc = banner.skills[0].1;
        let truncated = if desc.len() > 50 {
            format!("{}...", &desc[..47])
        } else {
            desc.to_string()
        };
        assert_eq!(truncated.len(), 50);
        assert!(truncated.ends_with("..."));
    }
}
