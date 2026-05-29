use super::color::Color;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct TextAttributes {
    pub bold: bool,
    pub italic: bool,
    pub underline: bool,
    pub dim: bool,
    pub reverse: bool,
    pub strikethrough: bool,
}

impl TextAttributes {
    pub fn bold() -> Self {
        Self { bold: true, ..Default::default() }
    }

    pub fn italic() -> Self {
        Self { italic: true, ..Default::default() }
    }

    pub fn underline() -> Self {
        Self { underline: true, ..Default::default() }
    }

    pub fn dim() -> Self {
        Self { dim: true, ..Default::default() }
    }

    pub fn reverse() -> Self {
        Self { reverse: true, ..Default::default() }
    }

    pub fn strikethrough() -> Self {
        Self { strikethrough: true, ..Default::default() }
    }

    pub fn merge(self, other: Self) -> Self {
        Self {
            bold: other.bold || self.bold,
            italic: other.italic || self.italic,
            underline: other.underline || self.underline,
            dim: other.dim || self.dim,
            reverse: other.reverse || self.reverse,
            strikethrough: other.strikethrough || self.strikethrough,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Style {
    pub fg: Option<Color>,
    pub bg: Option<Color>,
    pub attrs: TextAttributes,
}

impl Style {
    pub const fn new() -> Self {
        Self { fg: None, bg: None, attrs: TextAttributes {
            bold: false,
            italic: false,
            underline: false,
            dim: false,
            reverse: false,
            strikethrough: false,
        }}
    }

    pub fn fg(mut self, color: Color) -> Self {
        self.fg = Some(color);
        self
    }

    pub fn bg(mut self, color: Color) -> Self {
        self.bg = Some(color);
        self
    }

    pub fn add_modifier(mut self, attr: TextAttributes) -> Self {
        self.attrs = self.attrs.merge(attr);
        self
    }

    pub fn remove_modifier(mut self, attr: TextAttributes) -> Self {
        let mut a = self.attrs;
        if attr.bold { a.bold = false; }
        if attr.italic { a.italic = false; }
        if attr.underline { a.underline = false; }
        if attr.dim { a.dim = false; }
        if attr.reverse { a.reverse = false; }
        if attr.strikethrough { a.strikethrough = false; }
        self.attrs = a;
        self
    }
}

impl Default for Style {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_style_new_has_no_colors() {
        let s = Style::new();
        assert!(s.fg.is_none());
        assert!(s.bg.is_none());
        assert!(!s.attrs.bold);
        assert!(!s.attrs.italic);
        assert!(!s.attrs.underline);
        assert!(!s.attrs.dim);
        assert!(!s.attrs.reverse);
        assert!(!s.attrs.strikethrough);
    }

    #[test]
    fn test_style_default_equals_new() {
        assert_eq!(Style::new(), Style::default());
    }

    #[test]
    fn test_style_fg() {
        let s = Style::new().fg(Color::RED);
        assert_eq!(s.fg, Some(Color::RED));
        assert!(s.bg.is_none());
    }

    #[test]
    fn test_style_bg() {
        let s = Style::new().bg(Color::BLUE);
        assert!(s.fg.is_none());
        assert_eq!(s.bg, Some(Color::BLUE));
    }

    #[test]
    fn test_style_fg_and_bg() {
        let s = Style::new().fg(Color::WHITE).bg(Color::BLACK);
        assert_eq!(s.fg, Some(Color::WHITE));
        assert_eq!(s.bg, Some(Color::BLACK));
    }

    #[test]
    fn test_style_add_modifier_bold() {
        let s = Style::new().add_modifier(TextAttributes::bold());
        assert!(s.attrs.bold);
        assert!(!s.attrs.italic);
    }

    #[test]
    fn test_style_add_multiple_modifiers() {
        let s = Style::new()
            .add_modifier(TextAttributes::bold())
            .add_modifier(TextAttributes::italic())
            .add_modifier(TextAttributes::underline());
        assert!(s.attrs.bold);
        assert!(s.attrs.italic);
        assert!(s.attrs.underline);
        assert!(!s.attrs.dim);
    }

    #[test]
    fn test_style_remove_modifier() {
        let s = Style::new()
            .add_modifier(TextAttributes::bold())
            .add_modifier(TextAttributes::italic())
            .remove_modifier(TextAttributes::bold());
        assert!(!s.attrs.bold);
        assert!(s.attrs.italic);
    }

    #[test]
    fn test_style_chaining() {
        let s = Style::new()
            .fg(Color::from_rgb(255, 0, 0))
            .bg(Color::from_rgb(0, 0, 255))
            .add_modifier(TextAttributes::bold());
        assert_eq!(s.fg, Some(Color::from_rgb(255, 0, 0)));
        assert_eq!(s.bg, Some(Color::from_rgb(0, 0, 255)));
        assert!(s.attrs.bold);
    }

    #[test]
    fn test_text_attributes_merge_cumulative() {
        let a = TextAttributes::bold();
        let b = TextAttributes::italic();
        let merged = a.merge(b);
        assert!(merged.bold);
        assert!(merged.italic);
        assert!(!merged.underline);
    }

    #[test]
    fn test_text_attributes_merge_no_overlap() {
        let a = TextAttributes::bold();
        let b = TextAttributes::underline();
        let merged = a.merge(b);
        assert!(merged.bold);
        assert!(merged.underline);
        assert!(!merged.italic);
    }

    #[test]
    fn test_text_attributes_merge_same() {
        let a = TextAttributes::bold();
        let b = TextAttributes::bold();
        let merged = a.merge(b);
        assert!(merged.bold);
        assert!(!merged.italic);
    }

    #[test]
    fn test_text_attributes_default() {
        let a = TextAttributes::default();
        assert!(!a.bold);
        assert!(!a.italic);
        assert!(!a.underline);
        assert!(!a.dim);
        assert!(!a.reverse);
        assert!(!a.strikethrough);
    }

    #[test]
    fn test_text_attributes_all_constructors() {
        assert!(TextAttributes::bold().bold);
        assert!(TextAttributes::italic().italic);
        assert!(TextAttributes::underline().underline);
        assert!(TextAttributes::dim().dim);
        assert!(TextAttributes::reverse().reverse);
        assert!(TextAttributes::strikethrough().strikethrough);
    }

    #[test]
    fn test_style_equality() {
        let a = Style::new().fg(Color::RED).bg(Color::BLUE);
        let b = Style::new().fg(Color::RED).bg(Color::BLUE);
        assert_eq!(a, b);
    }

    #[test]
    fn test_style_inequality() {
        let a = Style::new().fg(Color::RED);
        let b = Style::new().fg(Color::BLUE);
        assert_ne!(a, b);
    }

    #[test]
    fn test_remove_modifier_never_set() {
        let s = Style::new().fg(Color::RED);
        let s2 = s.remove_modifier(TextAttributes::bold());
        assert_eq!(s2.fg, Some(Color::RED));
        assert!(!s2.attrs.bold);
    }

    #[test]
    fn test_remove_all_modifiers() {
        let s = Style::new()
            .add_modifier(TextAttributes::bold())
            .add_modifier(TextAttributes::italic())
            .add_modifier(TextAttributes::underline());
        let s2 = s.remove_modifier(TextAttributes::bold())
                  .remove_modifier(TextAttributes::italic())
                  .remove_modifier(TextAttributes::underline());
        assert!(!s2.attrs.bold);
        assert!(!s2.attrs.italic);
        assert!(!s2.attrs.underline);
    }

    #[test]
    fn test_merge_same_attribute() {
        let a = TextAttributes::bold();
        let b = TextAttributes::bold();
        let merged = a.merge(b);
        assert!(merged.bold);
    }
}
