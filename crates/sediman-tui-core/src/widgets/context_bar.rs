use ratatui::{
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub struct ContextBar {
    pub total_chars: usize,
    pub est_tokens: usize,
    pub max_tokens: usize,
}

impl ContextBar {
    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let pct = (self.est_tokens as f64 / self.max_tokens as f64).min(1.0);
        let bar_len = 10;
        let filled = (bar_len as f64 * pct).round() as usize;
        let bar: String = "▓".repeat(filled) + &"░".repeat(bar_len - filled);
        let text = format!("[{}] {}K", bar, self.est_tokens / 1000);

        let color = if pct > 0.8 {
            Color::Red
        } else if pct > 0.5 {
            Color::Yellow
        } else {
            Color::Green
        };

        let paragraph = Paragraph::new(Line::from(Span::styled(text, Style::new().fg(color))));
        frame.render_widget(paragraph, area);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_bar(est_tokens: usize, max_tokens: usize) -> ContextBar {
        ContextBar {
            total_chars: est_tokens * 4,
            est_tokens,
            max_tokens,
        }
    }

    #[test]
    fn test_zero_tokens() {
        let bar = make_bar(0, 128_000);
        let pct = bar.est_tokens as f64 / bar.max_tokens as f64;
        assert_eq!(pct, 0.0);
        let text = format!("[{}] {}K", "░".repeat(10), 0);
        assert_eq!(text, "[░░░░░░░░░░] 0K");
    }

    #[test]
    fn test_half_tokens() {
        let bar = make_bar(64_000, 128_000);
        let pct = bar.est_tokens as f64 / bar.max_tokens as f64;
        assert!((pct - 0.5).abs() < 1e-6);
        let filled = (10.0 * pct).round() as usize;
        assert_eq!(filled, 5);
        let bar_str = "▓".repeat(filled) + &"░".repeat(10 - filled);
        let text = format!("[{}] {}K", bar_str, 64);
        assert_eq!(text, "[▓▓▓▓▓░░░░░] 64K");
    }

    #[test]
    fn test_full_tokens() {
        let bar = make_bar(128_000, 128_000);
        let pct = bar.est_tokens as f64 / bar.max_tokens as f64;
        assert!((pct - 1.0).abs() < 1e-6);
        let filled = (10.0 * pct).round() as usize;
        assert_eq!(filled, 10);
        let bar_str: String = "▓".chars().cycle().take(filled).collect();
        assert_eq!(bar_str.chars().count(), 10);
    }

    #[test]
    fn test_over_max_capped() {
        let bar = make_bar(200_000, 128_000);
        let pct = (bar.est_tokens as f64 / bar.max_tokens as f64).min(1.0);
        assert!((pct - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_color_thresholds() {
        let low = make_bar(10_000, 128_000);
        let pct_low = low.est_tokens as f64 / low.max_tokens as f64;
        assert!(pct_low <= 0.5);

        let mid = make_bar(70_000, 128_000);
        let pct_mid = mid.est_tokens as f64 / mid.max_tokens as f64;
        assert!(pct_mid > 0.5 && pct_mid <= 0.8);

        let high = make_bar(110_000, 128_000);
        let pct_high = high.est_tokens as f64 / high.max_tokens as f64;
        assert!(pct_high > 0.8);
    }

    #[test]
    fn test_exact_boundaries() {
        // exactly at 50%
        let bar = make_bar(64_000, 128_000);
        let pct = bar.est_tokens as f64 / bar.max_tokens as f64;
        assert!((pct - 0.5).abs() < 1e-6);

        // exactly at 80%
        let bar = make_bar(102_400, 128_000);
        let pct = bar.est_tokens as f64 / bar.max_tokens as f64;
        assert!((pct - 0.8).abs() < 1e-6);
    }
}
