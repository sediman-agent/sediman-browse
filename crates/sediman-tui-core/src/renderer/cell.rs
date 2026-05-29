use super::Style;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Cell {
    pub ch: char,
    pub style: Style,
    pub skip: bool,
    pub link: Option<u8>,
}

impl Cell {
    pub const EMPTY: Self = Self {
        ch: ' ',
        style: Style::new(),
        skip: false,
        link: None,
    };

    pub fn new(ch: char, style: Style) -> Self {
        Self { ch, style, skip: false, link: None }
    }

    pub fn is_empty(self) -> bool {
        self.ch == ' '
            && self.style == Style::new()
            && !self.skip
            && self.link.is_none()
    }

    pub fn blend_style(mut self, overlay: Style) -> Self {
        if let Some(fg) = overlay.fg {
            self.style.fg = Some(fg);
        }
        if let Some(bg) = overlay.bg {
            self.style.bg = Some(bg);
        }
        self.style.attrs = self.style.attrs.merge(overlay.attrs);
        self
    }

    pub fn clear(&mut self) {
        *self = Self::EMPTY;
    }
}

impl Default for Cell {
    fn default() -> Self {
        Self::EMPTY
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::renderer::{Color, TextAttributes};

    #[test]
    fn test_cell_default_is_empty() {
        let c = Cell::default();
        assert!(c.is_empty());
        assert_eq!(c.ch, ' ');
        assert_eq!(c.style, Style::new());
        assert!(!c.skip);
        assert!(c.link.is_none());
    }

    #[test]
    fn test_cell_empty_const() {
        assert!(Cell::EMPTY.is_empty());
        assert_eq!(Cell::EMPTY.ch, ' ');
    }

    #[test]
    fn test_cell_new_not_empty() {
        let c = Cell::new('a', Style::new().fg(Color::RED));
        assert!(!c.is_empty());
        assert_eq!(c.ch, 'a');
        assert_eq!(c.style.fg, Some(Color::RED));
    }

    #[test]
    fn test_cell_new_preserves_char() {
        let c = Cell::new('Z', Style::new());
        assert_eq!(c.ch, 'Z');
        assert!(!c.is_empty());
    }

    #[test]
    fn test_cell_space_with_default_style_is_empty() {
        let c = Cell::new(' ', Style::new());
        assert!(c.is_empty());
    }

    #[test]
    fn test_cell_space_with_fg_is_not_empty() {
        let c = Cell::new(' ', Style::new().fg(Color::WHITE));
        assert!(!c.is_empty());
    }

    #[test]
    fn test_cell_skip_is_not_empty() {
        let mut c = Cell::default();
        c.skip = true;
        assert!(!c.is_empty());
    }

    #[test]
    fn test_cell_link_is_not_empty() {
        let mut c = Cell::default();
        c.link = Some(1);
        assert!(!c.is_empty());
    }

    #[test]
    fn test_cell_clear() {
        let mut c = Cell::new('x', Style::new().fg(Color::RED));
        c.clear();
        assert!(c.is_empty());
        assert_eq!(c.ch, ' ');
    }

    #[test]
    fn test_cell_blend_style_fg() {
        let c = Cell::new('x', Style::new().fg(Color::WHITE));
        let blended = c.blend_style(Style::new().fg(Color::RED));
        assert_eq!(blended.style.fg, Some(Color::RED));
    }

    #[test]
    fn test_cell_blend_style_bg() {
        let c = Cell::new('x', Style::new());
        let blended = c.blend_style(Style::new().bg(Color::BLUE));
        assert_eq!(blended.style.bg, Some(Color::BLUE));
    }

    #[test]
    fn test_cell_blend_style_merges_attrs() {
        let c = Cell::new('x', Style::new().add_modifier(TextAttributes::bold()));
        let blended = c.blend_style(Style::new().add_modifier(TextAttributes::italic()));
        assert!(blended.style.attrs.bold);
        assert!(blended.style.attrs.italic);
    }

    #[test]
    fn test_cell_blend_style_no_overwrite_none() {
        let c = Cell::new('x', Style::new().fg(Color::RED));
        let blended = c.blend_style(Style::new());
        assert_eq!(blended.style.fg, Some(Color::RED));
    }

    #[test]
    fn test_cell_equality() {
        let a = Cell::new('a', Style::new().fg(Color::RED));
        let b = Cell::new('a', Style::new().fg(Color::RED));
        assert_eq!(a, b);
    }

    #[test]
    fn test_cell_inequality_char() {
        let a = Cell::new('a', Style::new());
        let b = Cell::new('b', Style::new());
        assert_ne!(a, b);
    }

    #[test]
    fn test_cell_inequality_style() {
        let a = Cell::new('a', Style::new().fg(Color::RED));
        let b = Cell::new('a', Style::new().fg(Color::BLUE));
        assert_ne!(a, b);
    }

    #[test]
    fn test_cell_copy() {
        let a = Cell::new('x', Style::new().fg(Color::GREEN));
        let b = a;
        assert_eq!(a, b);
    }

    #[test]
    fn test_cell_clone() {
        let a = Cell::new('x', Style::new().fg(Color::GREEN));
        let b = a.clone();
        assert_eq!(a, b);
    }

    #[test]
    fn test_cell_null_char_not_empty() {
        let c = Cell::new('\0', Style::new());
        assert!(!c.is_empty());
    }

    #[test]
    fn test_cell_blend_style_both() {
        let c = Cell::new('x', Style::new().fg(Color::WHITE));
        let blended = c.blend_style(Style::new().bg(Color::BLUE).add_modifier(TextAttributes::bold()));
        assert_eq!(blended.style.fg, Some(Color::WHITE));
        assert_eq!(blended.style.bg, Some(Color::BLUE));
        assert!(blended.style.attrs.bold);
    }

    #[test]
    fn test_cell_equality_different_skip() {
        let mut a = Cell::new('x', Style::new());
        let mut b = Cell::new('x', Style::new());
        a.skip = true;
        b.skip = false;
        assert_ne!(a, b);
    }
}
