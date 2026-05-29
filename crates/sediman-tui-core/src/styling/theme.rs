//! OpenCode-inspired theme with exact color palette from opencode.go.
//!
//! Uses truecolor (24-bit RGB) for precise color matching.
//! Terminals must support COLORTERM=truecolor for full fidelity.

use crate::renderer::{Color, Style};

#[derive(Clone, Debug)]
pub struct Theme {
    // Base colors
    pub primary: Color,
    pub secondary: Color,
    pub accent: Color,

    // Status colors
    pub error: Color,
    pub warning: Color,
    pub success: Color,
    pub info: Color,

    // Text colors
    pub text: Color,
    pub text_muted: Color,
    pub text_emphasized: Color,

    // Background colors
    pub background: Color,
    pub background_panel: Color,
    pub background_darker: Color,

    // Border colors
    pub border: Color,
    pub border_focused: Color,
    pub border_dim: Color,

    // Message-specific colors
    pub user_message: Color,
    pub agent_message: Color,

    // Markdown colors (OpenCode's exact mapping)
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

    // Syntax highlighting colors
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
        // ─── OpenCode's exact "opencode" theme palette (dark mode) ───
        // Source: github.com/opencode-ai/opencode/internal/tui/theme/opencode.go
        //
        // Core palette:
        //   Background:  #212121    Primary:    #fab283 (warm orange/gold)
        //   Foreground:  #e0e0e0    Secondary:  #5c9cf5 (soft blue)
        //   Comment:     #6a6a6a    Accent:     #9d7cd8 (purple)
        //   Border:      #4b4c5c    Red:        #e06c75
        //   Green:       #7fd88f    Cyan:       #56b6c2
        //   Orange:      #f5a742    Yellow:     #e5c07b

        let primary       = Color::from_rgb(0xfa, 0xb2, 0x83); // warm orange/gold
        let secondary     = Color::from_rgb(0x5c, 0x9c, 0xf5); // soft blue
        let accent        = Color::from_rgb(0x9d, 0x7c, 0xd8); // purple
        let error         = Color::from_rgb(0xe0, 0x6c, 0x75); // soft red
        let warning       = Color::from_rgb(0xf5, 0xa7, 0x42); // orange
        let success       = Color::from_rgb(0x7f, 0xd8, 0x8f); // soft green
        let info          = Color::from_rgb(0x56, 0xb6, 0xc2); // teal/cyan
        let text          = Color::from_rgb(0xe0, 0xe0, 0xe0); // light gray
        let text_muted    = Color::from_rgb(0x6a, 0x6a, 0x6a); // mid gray (comment)
        let text_emph     = Color::from_rgb(0xe5, 0xc0, 0x7b); // yellow
        let background    = Color::from_rgb(0x21, 0x21, 0x21); // OpenCode's exact bg
        let bg_panel      = Color::from_rgb(0x25, 0x25, 0x25); // current line
        let bg_darker     = Color::from_rgb(0x12, 0x12, 0x12); // darker than bg
        let border        = Color::from_rgb(0x4b, 0x4c, 0x5c); // OpenCode's exact border
        let border_focus  = primary;                              // focused = primary
        let border_dim    = Color::from_rgb(0x30, 0x30, 0x30); // selection

        Self {
            // Base
            primary,
            secondary,
            accent,
            // Status
            error,
            warning,
            success,
            info,
            // Text
            text,
            text_muted,
            text_emphasized: text_emph,
            // Background
            background,
            background_panel: bg_panel,
            background_darker: bg_darker,
            // Border
            border,
            border_focused: border_focus,
            border_dim,
            // Messages
            user_message: secondary,
            agent_message: primary,
            // Markdown — matches OpenCode's markdown color mapping
            md_text: text,
            md_heading: secondary,       // headings = secondary (blue)
            md_link: primary,            // links = primary (orange)
            md_link_text: info,          // link text = cyan
            md_code: success,            // inline code = green
            md_blockquote: text_emph,    // blockquotes = yellow
            md_emph: text_emph,          // emphasis = yellow
            md_strong: accent,           // strong = purple
            md_horizontal_rule: text_muted,
            md_list_item: primary,       // list items = primary (orange)
            md_list_enum: info,          // enum items = cyan
            md_code_block: text,         // code block text = foreground
            // Syntax highlighting — matches OpenCode's Chroma mapping
            syntax_comment: text_muted,  // comments = gray
            syntax_keyword: secondary,   // keywords = blue
            syntax_function: primary,    // functions = orange
            syntax_variable: error,      // variables = red
            syntax_string: success,      // strings = green
            syntax_number: accent,       // numbers = purple
            syntax_type: text_emph,      // types = yellow
            syntax_operator: info,       // operators = cyan
            syntax_punctuation: text,    // punctuation = foreground
        }
    }
}

impl Theme {
    pub fn primary_style(&self) -> Style {
        Style::new().fg(self.primary)
    }

    pub fn secondary_style(&self) -> Style {
        Style::new().fg(self.secondary)
    }

    pub fn success_style(&self) -> Style {
        Style::new().fg(self.success)
    }

    pub fn error_style(&self) -> Style {
        Style::new().fg(self.error)
    }

    pub fn muted_style(&self) -> Style {
        Style::new().fg(self.text_muted)
    }

    pub fn warning_style(&self) -> Style {
        Style::new().fg(self.warning)
    }

    pub fn info_style(&self) -> Style {
        Style::new().fg(self.info)
    }

    pub fn accent_style(&self) -> Style {
        Style::new().fg(self.accent)
    }

    pub fn text_style(&self) -> Style {
        Style::new().fg(self.text)
    }

    pub fn text_muted_style(&self) -> Style {
        Style::new().fg(self.text_muted)
    }

    pub fn border_style(&self) -> Style {
        Style::new().fg(self.border)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_theme_matches_opencode() {
        let theme = Theme::default();
        // OpenCode's exact colors
        assert_eq!(theme.primary, Color::from_rgb(0xfa, 0xb2, 0x83));
        assert_eq!(theme.secondary, Color::from_rgb(0x5c, 0x9c, 0xf5));
        assert_eq!(theme.accent, Color::from_rgb(0x9d, 0x7c, 0xd8));
        assert_eq!(theme.text, Color::from_rgb(0xe0, 0xe0, 0xe0));
        assert_eq!(theme.background, Color::from_rgb(0x21, 0x21, 0x21));
        assert_eq!(theme.border, Color::from_rgb(0x4b, 0x4c, 0x5c));
        assert_eq!(theme.text_muted, Color::from_rgb(0x6a, 0x6a, 0x6a));
    }

    #[test]
    fn test_primary_style() {
        let theme = Theme::default();
        let style = theme.primary_style();
        assert_eq!(style.fg, Some(theme.primary));
    }

    #[test]
    fn test_markdown_colors_use_theme_palette() {
        let theme = Theme::default();
        // Headings should be secondary (blue)
        assert_eq!(theme.md_heading, theme.secondary);
        // List items should be primary (orange)
        assert_eq!(theme.md_list_item, theme.primary);
    }

    #[test]
    fn test_secondary_style() {
        let t = Theme::default();
        let s = t.secondary_style();
        assert_eq!(s.fg, Some(t.secondary));
    }

    #[test]
    fn test_success_style() {
        let t = Theme::default();
        let s = t.success_style();
        assert_eq!(s.fg, Some(t.success));
    }

    #[test]
    fn test_error_style() {
        let t = Theme::default();
        let s = t.error_style();
        assert_eq!(s.fg, Some(t.error));
    }

    #[test]
    fn test_muted_style() {
        let t = Theme::default();
        let s = t.muted_style();
        assert_eq!(s.fg, Some(t.text_muted));
    }

    #[test]
    fn test_warning_style() {
        let t = Theme::default();
        let s = t.warning_style();
        assert_eq!(s.fg, Some(t.warning));
    }

    #[test]
    fn test_info_style() {
        let t = Theme::default();
        let s = t.info_style();
        assert_eq!(s.fg, Some(t.info));
    }

    #[test]
    fn test_accent_style() {
        let t = Theme::default();
        let s = t.accent_style();
        assert_eq!(s.fg, Some(t.accent));
    }

    #[test]
    fn test_text_style() {
        let t = Theme::default();
        let s = t.text_style();
        assert_eq!(s.fg, Some(t.text));
    }

    #[test]
    fn test_text_muted_style() {
        let t = Theme::default();
        let s = t.text_muted_style();
        assert_eq!(s.fg, Some(t.text_muted));
    }

    #[test]
    fn test_border_style() {
        let t = Theme::default();
        let s = t.border_style();
        assert_eq!(s.fg, Some(t.border));
    }

    #[test]
    fn test_theme_readability() {
        let t = Theme::default();
        assert_ne!(t.background, t.text);
        assert_ne!(t.background_darker, t.text);
    }
}
