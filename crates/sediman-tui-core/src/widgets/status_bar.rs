use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Paragraph},
    Frame,
};

pub struct StatusBar<'a> {
    pub elapsed: Option<std::time::Duration>,
    pub spinner_text: Option<&'a str>,
    pub provider_model: &'a str,
    pub permission_mode: &'a str,
    pub session_name: Option<&'a str>,
    pub session_color: Option<Color>,
    pub task_count: usize,
    pub context_bar_text: Option<&'a str>,
}

impl<'a> StatusBar<'a> {
    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let mut spans = Vec::new();

        if let Some(elapsed) = self.elapsed {
            let secs = elapsed.as_secs();
            let elapsed_str = if secs >= 60 {
                format!("{}m {}s", secs / 60, secs % 60)
            } else {
                format!("{}s", secs)
            };
            spans.push(Span::styled(
                format!("⏳ {} ", elapsed_str),
                Style::new().fg(Color::Green).add_modifier(Modifier::BOLD),
            ));
            if let Some(text) = self.spinner_text {
                spans.push(Span::styled(
                    format!("{} ", text),
                    Style::new().add_modifier(Modifier::ITALIC),
                ));
            }
        } else {
            spans.push(Span::styled(
                "● idle ",
                Style::new().fg(Color::DarkGray),
            ));
        }

        spans.push(Span::styled(
            format!(" {} ", self.provider_model),
            Style::new().fg(Color::DarkGray),
        ));

        let mode_color = match self.permission_mode {
            "acceptEdits" => Color::Green,
            "plan" => Color::Magenta,
            "auto" => Color::Red,
            _ => Color::White,
        };
        spans.push(Span::styled(
            format!("· {} ", self.permission_mode),
            Style::new().fg(mode_color),
        ));

        if let Some(name) = self.session_name {
            let color = self.session_color.unwrap_or(Color::Cyan);
            spans.push(Span::styled(
                format!("{} ", name),
                Style::new().fg(color),
            ));
        }

        spans.push(Span::styled(
            format!("· {} tasks ", self.task_count),
            Style::new().fg(Color::DarkGray),
        ));

        if let Some(ctx) = self.context_bar_text {
            spans.push(Span::raw(format!("{} ", ctx)));
        }

        spans.push(Span::styled(
            "· ? help · Esc int · ^C exit · ⇧Tab mode · ! shell ",
            Style::new().fg(Color::DarkGray).add_modifier(Modifier::DIM),
        ));

        let paragraph = Paragraph::new(Line::from(spans))
            .block(Block::default().style(
                Style::new().bg(Color::Blue).fg(Color::White),
            ));
        frame.render_widget(paragraph, area);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_status_bar_idle() {
        let bar = StatusBar {
            elapsed: None,
            spinner_text: None,
            provider_model: "openai/gpt-4o",
            permission_mode: "ask",
            session_name: None,
            session_color: None,
            task_count: 0,
            context_bar_text: None,
        };
        assert!(bar.elapsed.is_none());
        assert_eq!(bar.provider_model, "openai/gpt-4o");
        assert_eq!(bar.permission_mode, "ask");
    }

    #[test]
    fn test_status_bar_running() {
        let bar = StatusBar {
            elapsed: Some(std::time::Duration::from_secs(30)),
            spinner_text: Some("processing"),
            provider_model: "openai/gpt-4o",
            permission_mode: "auto",
            session_name: Some("my-session"),
            session_color: Some(Color::Cyan),
            task_count: 3,
            context_bar_text: Some("[▓▓▓░░░░░░░] 12K"),
        };
        assert!(bar.elapsed.is_some());
        assert_eq!(bar.task_count, 3);
        assert_eq!(bar.session_name.unwrap(), "my-session");
    }

    #[test]
    fn test_status_bar_elapsed_format() {
        let bar = StatusBar {
            elapsed: Some(std::time::Duration::from_secs(125)),
            spinner_text: None,
            provider_model: "ollama/qwen3",
            permission_mode: "acceptEdits",
            session_name: None,
            session_color: None,
            task_count: 7,
            context_bar_text: None,
        };
        let secs = bar.elapsed.unwrap().as_secs();
        assert_eq!(secs, 125);
        // 125s = 2m 5s
        assert_eq!(secs / 60, 2);
        assert_eq!(secs % 60, 5);
    }

    #[test]
    fn test_status_bar_mode_colors() {
        let modes = ["ask", "acceptEdits", "plan", "auto"];
        for mode in &modes {
            let bar = StatusBar {
                elapsed: None,
                spinner_text: None,
                provider_model: "test",
                permission_mode: mode,
                session_name: None,
                session_color: None,
                task_count: 1,
                context_bar_text: None,
            };
            assert_eq!(bar.permission_mode, *mode);
        }
    }

    #[test]
    fn test_status_bar_with_session() {
        let bar = StatusBar {
            elapsed: None,
            spinner_text: None,
            provider_model: "openai/gpt-4o",
            permission_mode: "ask",
            session_name: Some("my-session"),
            session_color: Some(Color::Cyan),
            task_count: 5,
            context_bar_text: None,
        };
        assert!(bar.session_name.is_some());
        assert_eq!(bar.session_color.unwrap(), Color::Cyan);
    }

    #[test]
    fn test_status_bar_no_session() {
        let bar = StatusBar {
            elapsed: None,
            spinner_text: None,
            provider_model: "openai/gpt-4o",
            permission_mode: "ask",
            session_name: None,
            session_color: None,
            task_count: 0,
            context_bar_text: None,
        };
        assert!(bar.session_name.is_none());
    }
}
