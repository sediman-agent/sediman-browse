use crate::renderer::{Color, Style};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ThemeColors {
    pub primary: String,
    pub secondary: String,
    pub accent: String,
    pub error: String,
    pub warning: String,
    pub success: String,
    pub info: String,
    pub text: String,
    pub text_muted: String,
    pub text_emphasized: String,
    pub background: String,
    pub background_panel: String,
    pub background_darker: String,
}

impl Default for ThemeColors {
    fn default() -> Self {
        Self {
            primary: "#fab283".into(),
            secondary: "#5c9cf5".into(),
            accent: "#9d7cd8".into(),
            error: "#e06c75".into(),
            warning: "#f5a742".into(),
            success: "#7fd88f".into(),
            info: "#56b6c2".into(),
            text: "#e0e0e0".into(),
            text_muted: "#6a6a6a".into(),
            text_emphasized: "#e5c07b".into(),
            background: "#212121".into(),
            background_panel: "#252525".into(),
            background_darker: "#121212".into(),
        }
    }
}

impl ThemeColors {
    pub fn to_theme(&self) -> Theme {
        let resolve = |hex: &str| parse_hex(hex).unwrap_or_else(|| Color::from_rgb(0xff, 0xff, 0xff));

        let primary = resolve(&self.primary);
        let secondary = resolve(&self.secondary);
        let accent = resolve(&self.accent);
        let error = resolve(&self.error);
        let warning = resolve(&self.warning);
        let success = resolve(&self.success);
        let info = resolve(&self.info);
        let text = resolve(&self.text);
        let text_muted = resolve(&self.text_muted);
        let text_emphasized = resolve(&self.text_emphasized);
        let background = resolve(&self.background);
        let bg_panel = resolve(&self.background_panel);
        let bg_darker = resolve(&self.background_darker);

        let (br, bg_, bb) = background.to_rgb();
        let border = Color::from_rgb(
            br.saturating_add(40),
            bg_.saturating_add(40),
            bb.saturating_add(40),
        );
        let border_dim = Color::from_rgb(
            br.saturating_add(15),
            bg_.saturating_add(15),
            bb.saturating_add(15),
        );

        Theme {
            primary,
            secondary,
            accent,
            error,
            warning,
            success,
            info,
            text,
            text_muted,
            text_emphasized,
            background,
            background_panel: bg_panel,
            background_darker: bg_darker,
            border,
            border_focused: primary,
            border_dim,
            user_message: secondary,
            agent_message: primary,
            md_text: text,
            md_heading: secondary,
            md_link: primary,
            md_link_text: info,
            md_code: success,
            md_blockquote: text_emphasized,
            md_emph: text_emphasized,
            md_strong: accent,
            md_horizontal_rule: text_muted,
            md_list_item: primary,
            md_list_enum: info,
            md_code_block: text,
            syntax_comment: text_muted,
            syntax_keyword: secondary,
            syntax_function: primary,
            syntax_variable: error,
            syntax_string: success,
            syntax_number: accent,
            syntax_type: text_emphasized,
            syntax_operator: info,
            syntax_punctuation: text,
        }
    }

    pub fn from_theme(theme: &Theme) -> Self {
        fn hex(c: Color) -> String {
            let (r, g, b) = c.to_rgb();
            format!("#{:02x}{:02x}{:02x}", r, g, b)
        }
        Self {
            primary: hex(theme.primary),
            secondary: hex(theme.secondary),
            accent: hex(theme.accent),
            error: hex(theme.error),
            warning: hex(theme.warning),
            success: hex(theme.success),
            info: hex(theme.info),
            text: hex(theme.text),
            text_muted: hex(theme.text_muted),
            text_emphasized: hex(theme.text_emphasized),
            background: hex(theme.background),
            background_panel: hex(theme.background_panel),
            background_darker: hex(theme.background_darker),
        }
    }
}

pub fn parse_hex(s: &str) -> Option<Color> {
    let s = s.trim().trim_start_matches('#');
    if s.len() != 6 { return None; }
    let r = u8::from_str_radix(&s[0..2], 16).ok()?;
    let g = u8::from_str_radix(&s[2..4], 16).ok()?;
    let b = u8::from_str_radix(&s[4..6], 16).ok()?;
    Some(Color::from_rgb(r, g, b))
}

#[derive(Clone, Debug)]
pub struct Theme {
    pub primary: Color,
    pub secondary: Color,
    pub accent: Color,
    pub error: Color,
    pub warning: Color,
    pub success: Color,
    pub info: Color,
    pub text: Color,
    pub text_muted: Color,
    pub text_emphasized: Color,
    pub background: Color,
    pub background_panel: Color,
    pub background_darker: Color,
    pub border: Color,
    pub border_focused: Color,
    pub border_dim: Color,
    pub user_message: Color,
    pub agent_message: Color,
    pub md_text: Color,
    pub md_heading: Color,
    pub md_link: Color,
    pub md_link_text: Color,
    pub md_code: Color,
    pub md_blockquote: Color,
    pub md_emph: Color,
    pub md_strong: Color,
    pub md_horizontal_rule: Color,
    pub md_list_item: Color,
    pub md_list_enum: Color,
    pub md_code_block: Color,
    pub syntax_comment: Color,
    pub syntax_keyword: Color,
    pub syntax_function: Color,
    pub syntax_variable: Color,
    pub syntax_string: Color,
    pub syntax_number: Color,
    pub syntax_type: Color,
    pub syntax_operator: Color,
    pub syntax_punctuation: Color,
}

impl Default for Theme {
    fn default() -> Self {
        ThemeColors::default().to_theme()
    }
}

impl Theme {
    pub fn from_colors(colors: &ThemeColors) -> Self { colors.to_theme() }
    pub fn to_colors(&self) -> ThemeColors { ThemeColors::from_theme(self) }
    pub fn swatch_colors(&self) -> [Color; 5] {
        [self.primary, self.secondary, self.accent, self.success, self.warning]
    }

    pub fn primary_style(&self) -> Style { Style::new().fg(self.primary) }
    pub fn secondary_style(&self) -> Style { Style::new().fg(self.secondary) }
    pub fn success_style(&self) -> Style { Style::new().fg(self.success) }
    pub fn error_style(&self) -> Style { Style::new().fg(self.error) }
    pub fn muted_style(&self) -> Style { Style::new().fg(self.text_muted) }
    pub fn warning_style(&self) -> Style { Style::new().fg(self.warning) }
    pub fn info_style(&self) -> Style { Style::new().fg(self.info) }
    pub fn accent_style(&self) -> Style { Style::new().fg(self.accent) }
    pub fn text_style(&self) -> Style { Style::new().fg(self.text) }
    pub fn text_muted_style(&self) -> Style { Style::new().fg(self.text_muted) }
    pub fn border_style(&self) -> Style { Style::new().fg(self.border) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_theme() {
        let t = Theme::default();
        assert_eq!(t.primary, Color::from_rgb(0xfa, 0xb2, 0x83));
        assert_eq!(t.secondary, Color::from_rgb(0x5c, 0x9c, 0xf5));
        assert_eq!(t.background, Color::from_rgb(0x21, 0x21, 0x21));
    }

    #[test]
    fn test_colors_roundtrip() {
        let c = ThemeColors::default();
        let t = c.to_theme();
        let c2 = ThemeColors::from_theme(&t);
        assert_eq!(c.primary, c2.primary);
        assert_eq!(c.background, c2.background);
    }

    #[test]
    fn test_colors_serialize() {
        let c = ThemeColors::default();
        let json = serde_json::to_string(&c).unwrap();
        let c2: ThemeColors = serde_json::from_str(&json).unwrap();
        assert_eq!(c.primary, c2.primary);
    }

    #[test]
    fn test_from_colors() {
        let c = ThemeColors { primary: "#ff0000".into(), ..Default::default() };
        let t = Theme::from_colors(&c);
        assert_eq!(t.primary, Color::from_rgb(255, 0, 0));
        assert_eq!(t.md_link, t.primary);
        assert_eq!(t.md_heading, t.secondary);
    }

    #[test]
    fn test_parse_hex() {
        assert_eq!(parse_hex("#fab283"), Some(Color::from_rgb(0xfa, 0xb2, 0x83)));
        assert_eq!(parse_hex("fab283"), Some(Color::from_rgb(0xfa, 0xb2, 0x83)));
        assert_eq!(parse_hex(""), None);
        assert_eq!(parse_hex("#fff"), None);
    }

    #[test]
    fn test_derived_colors() {
        let t = Theme::default();
        assert_eq!(t.md_heading, t.secondary);
        assert_eq!(t.md_link, t.primary);
        assert_eq!(t.syntax_comment, t.text_muted);
        assert_eq!(t.syntax_keyword, t.secondary);
        assert_eq!(t.user_message, t.secondary);
        assert_eq!(t.agent_message, t.primary);
    }

    #[test]
    fn test_style_helpers() {
        let t = Theme::default();
        assert_eq!(t.primary_style().fg, Some(t.primary));
        assert_eq!(t.error_style().fg, Some(t.error));
        assert_eq!(t.border_style().fg, Some(t.border));
    }

    #[test]
    fn test_swatch_colors() {
        let t = Theme::default();
        assert_eq!(t.swatch_colors().len(), 5);
    }
}
