use ratatui::{
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

pub struct ResultPanel<'a> {
    pub text: &'a str,
    pub success: bool,
    pub elapsed_secs: u64,
    pub skill_created: bool,
    pub scheduled_job: Option<&'a str>,
}

impl<'a> ResultPanel<'a> {
    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let (symbol, border_color) = if self.success {
            ("✓", Color::Green)
        } else {
            ("✗", Color::Red)
        };

        let title = format!("{} Sediman ({}s)", symbol, self.elapsed_secs);

        let mut lines = vec![Line::from(Span::raw(self.text))];

        if self.skill_created {
            lines.push(Line::from(Span::styled(
                "  ◆ Skill created from this task",
                Style::new().fg(Color::Magenta),
            )));
        }
        if let Some(job_id) = self.scheduled_job {
            lines.push(Line::from(Span::styled(
                format!("  ◇ Scheduled job: {}", job_id),
                Style::new().fg(Color::Cyan),
            )));
        }

        let paragraph = Paragraph::new(lines)
            .block(
                Block::default()
                    .title(title)
                    .borders(Borders::ALL)
                    .border_style(Style::new().fg(border_color)),
            )
            .wrap(Wrap { trim: false });

        frame.render_widget(paragraph, area);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_result_panel_success() {
        let panel = ResultPanel {
            text: "Task completed successfully",
            success: true,
            elapsed_secs: 42,
            skill_created: true,
            scheduled_job: Some("job-123"),
        };
        assert!(panel.success);
        assert_eq!(panel.elapsed_secs, 42);
        assert_eq!(panel.text, "Task completed successfully");
    }

    #[test]
    fn test_result_panel_failure() {
        let panel = ResultPanel {
            text: "Something went wrong",
            success: false,
            elapsed_secs: 10,
            skill_created: false,
            scheduled_job: None,
        };
        assert!(!panel.success);
        assert!(panel.scheduled_job.is_none());
    }

    #[test]
    fn test_result_panel_with_job() {
        let panel = ResultPanel {
            text: "ok",
            success: true,
            elapsed_secs: 5,
            skill_created: false,
            scheduled_job: Some("scheduled-999"),
        };
        assert_eq!(panel.scheduled_job.unwrap(), "scheduled-999");
    }

    #[test]
    fn test_result_panel_elapsed_format() {
        let panel = ResultPanel {
            text: "",
            success: true,
            elapsed_secs: 3600,
            skill_created: false,
            scheduled_job: None,
        };
        assert_eq!(panel.elapsed_secs, 3600);
    }
}
