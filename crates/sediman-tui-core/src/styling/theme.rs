use ratatui::style::{Color, Modifier, Style};

pub struct Theme {
    pub primary: Color,
    pub secondary: Color,
    pub success: Color,
    pub error: Color,
    pub warning: Color,
    pub info: Color,
    pub muted: Color,
    pub accent: Color,
}

impl Default for Theme {
    fn default() -> Self {
        Self {
            primary: Color::Blue,
            secondary: Color::Cyan,
            success: Color::Green,
            error: Color::Red,
            warning: Color::Yellow,
            info: Color::Magenta,
            muted: Color::DarkGray,
            accent: Color::LightBlue,
        }
    }
}

impl Theme {

    pub fn primary_style(&self) -> Style {
        Style::new().fg(self.primary).add_modifier(Modifier::BOLD)
    }

    pub fn success_style(&self) -> Style {
        Style::new().fg(self.success)
    }

    pub fn error_style(&self) -> Style {
        Style::new().fg(self.error)
    }

    pub fn muted_style(&self) -> Style {
        Style::new().fg(self.muted)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_theme_colors() {
        let theme = Theme::default();
        assert_eq!(theme.primary, Color::Blue);
        assert_eq!(theme.secondary, Color::Cyan);
        assert_eq!(theme.success, Color::Green);
        assert_eq!(theme.error, Color::Red);
        assert_eq!(theme.warning, Color::Yellow);
        assert_eq!(theme.info, Color::Magenta);
        assert_eq!(theme.muted, Color::DarkGray);
        assert_eq!(theme.accent, Color::LightBlue);
    }

    #[test]
    fn test_primary_style() {
        let theme = Theme::default();
        let style = theme.primary_style();
        assert_eq!(style.fg, Some(Color::Blue));
        assert!(style.add_modifier.contains(Modifier::BOLD));
    }

    #[test]
    fn test_success_style() {
        let theme = Theme::default();
        let style = theme.success_style();
        assert_eq!(style.fg, Some(Color::Green));
    }

    #[test]
    fn test_error_style() {
        let theme = Theme::default();
        let style = theme.error_style();
        assert_eq!(style.fg, Some(Color::Red));
    }

    #[test]
    fn test_muted_style() {
        let theme = Theme::default();
        let style = theme.muted_style();
        assert_eq!(style.fg, Some(Color::DarkGray));
    }
}
