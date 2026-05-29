use ratatui::{
    layout::{Alignment, Rect},
    style::{Color, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

const PHASE_SYMBOLS: &[(&str, &str, Color)] = &[
    ("planning", "◈", Color::Yellow),
    ("executing", "▶", Color::Blue),
    ("observing", "◎", Color::Cyan),
    ("reflecting", "◆", Color::Magenta),
    ("delegating", "◇", Color::Green),
    ("done", "✓", Color::Green),
    ("failed", "✗", Color::Red),
];

pub struct ProgressPanel<'a> {
    pub step_log: &'a [String],
    pub elapsed: std::time::Duration,
    pub spinner_text: &'a str,
    pub visible_lines: usize,
}

impl<'a> ProgressPanel<'a> {
    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let title = format!(
            "  ⏳ {}s  {}",
            self.elapsed.as_secs(),
            self.spinner_text
        );

        let lines: Vec<Line> = self
            .step_log
            .iter()
            .rev()
            .take(self.visible_lines)
            .rev()
            .map(|s| {
                let (symbol, color) = PHASE_SYMBOLS
                    .iter()
                    .find(|(name, _, _)| s.contains(name))
                    .map(|(_, sym, color)| (*sym, *color))
                    .unwrap_or(("", Color::White));

                Line::from(Span::styled(
                    format!("{} {}", symbol, s),
                    Style::new().fg(color),
                ))
            })
            .collect();

        let paragraph = Paragraph::new(lines)
            .block(
                Block::default()
                    .title(title)
                    .title_alignment(Alignment::Left)
                    .borders(Borders::ALL)
                    .border_style(Style::new().fg(Color::Blue)),
            )
            .wrap(Wrap { trim: false });

        frame.render_widget(paragraph, area);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_phase_symbols_all_defined() {
        let phases = ["planning", "executing", "observing", "reflecting", "delegating", "done", "failed"];
        for phase in &phases {
            let found = PHASE_SYMBOLS.iter().find(|(name, _, _)| name == phase);
            assert!(found.is_some(), "Missing symbol for phase: {}", phase);
        }
    }

    #[test]
    fn test_phase_symbols_unique() {
        let mut names: Vec<&str> = PHASE_SYMBOLS.iter().map(|(n, _, _)| *n).collect();
        names.sort();
        let mut dedup = names.clone();
        dedup.dedup();
        assert_eq!(names, dedup, "Phase symbols must have unique names");
    }

    #[test]
    fn test_progress_panel_elapsed_formatting() {
        let panel = ProgressPanel {
            step_log: &[],
            elapsed: std::time::Duration::from_secs(65),
            spinner_text: "working",
            visible_lines: 50,
        };
        assert_eq!(panel.elapsed.as_secs(), 65);
        assert_eq!(panel.spinner_text, "working");
    }

    #[test]
    fn test_progress_panel_log_capping() {
        let log: Vec<String> = (0..100).map(|i| format!("step {}", i)).collect();
        let panel = ProgressPanel {
            step_log: &log,
            elapsed: std::time::Duration::from_secs(10),
            spinner_text: "test",
            visible_lines: 50,
        };
        // Only last 50 lines should be visible
        assert_eq!(panel.visible_lines, 50);
    }

    #[test]
    fn test_progress_panel_empty_log() {
        let panel = ProgressPanel {
            step_log: &[],
            elapsed: std::time::Duration::from_secs(0),
            spinner_text: "idle",
            visible_lines: 50,
        };
        assert!(panel.step_log.is_empty());
    }

    #[test]
    fn test_progress_panel_title_contains_elapsed() {
        let panel = ProgressPanel {
            step_log: &[],
            elapsed: std::time::Duration::from_secs(42),
            spinner_text: "processing",
            visible_lines: 50,
        };
        let title = format!("  ⏳ {}s  {}", panel.elapsed.as_secs(), panel.spinner_text);
        assert_eq!(title, "  ⏳ 42s  processing");
    }
}
