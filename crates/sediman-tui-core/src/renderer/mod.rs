pub mod color;
pub mod style;
pub mod cell;
pub mod buffer;
pub mod diff;
pub mod ansi;
#[cfg(feature = "gpu")]
pub mod gpu;

pub use color::{Color, Rgba};
pub use style::{Style, TextAttributes};
pub use cell::Cell;
pub use buffer::{CellBuffer, Rect};
pub use diff::{DiffEngine, Change};
pub use ansi::AnsiWriter;

pub fn display_width(s: &str) -> u16 {
    unicode_width::UnicodeWidthStr::width(s) as u16
}

pub fn truncate_str(s: &str, max_chars: usize) -> &str {
    match s.char_indices().nth(max_chars) {
        Some((idx, _)) => &s[..idx],
        None => s,
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Span {
    pub text: String,
    pub style: Style,
}

impl Span {
    pub fn raw(text: impl Into<String>) -> Self {
        Self { text: text.into(), style: Style::new() }
    }

    pub fn styled(text: impl Into<String>, style: Style) -> Self {
        Self { text: text.into(), style }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Line {
    pub spans: Vec<Span>,
}

impl Line {
    pub fn new() -> Self {
        Self { spans: Vec::new() }
    }

    pub fn from_raw(text: impl Into<String>) -> Self {
        Self { spans: vec![Span::raw(text)] }
    }

    pub fn from_spans(spans: Vec<Span>) -> Self {
        Self { spans }
    }

    pub fn from_styled(text: impl Into<String>, style: Style) -> Self {
        Self { spans: vec![Span::styled(text, style)] }
    }

    pub fn render(&self, buf: &mut CellBuffer, mut x: u16, y: u16) -> u16 {
        for span in &self.spans {
            for ch in span.text.chars() {
                let w = unicode_width::UnicodeWidthChar::width(ch).unwrap_or(0) as u16;
                if w == 0 { continue; }
                buf.put_char(x, y, ch, span.style);
                x += 1;
                for _ in 1..w {
                    if let Some(c) = buf.get_mut(x, y) {
                        c.skip = true;
                    }
                    x += 1;
                }
            }
        }
        x
    }
}

impl From<&str> for Line {
    fn from(s: &str) -> Self {
        Self::from_raw(s)
    }
}

impl From<String> for Line {
    fn from(s: String) -> Self {
        Self::from_raw(s)
    }
}

impl From<Span> for Line {
    fn from(span: Span) -> Self {
        Self { spans: vec![span] }
    }
}

impl From<Vec<Span>> for Line {
    fn from(spans: Vec<Span>) -> Self {
        Self { spans }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_span_raw() {
        let s = Span::raw("hello");
        assert_eq!(s.text, "hello");
        assert_eq!(s.style, Style::new());
    }

    #[test]
    fn test_span_styled() {
        let s = Span::styled("hi", Style::new().fg(Color::RED));
        assert_eq!(s.text, "hi");
        assert_eq!(s.style.fg, Some(Color::RED));
    }

    #[test]
    fn test_line_new() {
        let l = Line::new();
        assert!(l.spans.is_empty());
    }

    #[test]
    fn test_line_from_raw() {
        let l = Line::from_raw("test");
        assert_eq!(l.spans.len(), 1);
        assert_eq!(l.spans[0].text, "test");
    }

    #[test]
    fn test_line_from_styled() {
        let l = Line::from_styled("text", Style::new().fg(Color::BLUE));
        assert_eq!(l.spans.len(), 1);
        assert_eq!(l.spans[0].style.fg, Some(Color::BLUE));
    }

    #[test]
    fn test_line_from_spans() {
        let spans = vec![Span::raw("a"), Span::raw("b")];
        let l = Line::from_spans(spans);
        assert_eq!(l.spans.len(), 2);
    }

    #[test]
    fn test_line_from_str() {
        let l: Line = "hello".into();
        assert_eq!(l.spans[0].text, "hello");
    }

    #[test]
    fn test_line_from_string() {
        let l: Line = "world".to_string().into();
        assert_eq!(l.spans[0].text, "world");
    }

    #[test]
    fn test_line_from_span() {
        let l: Line = Span::raw("x").into();
        assert_eq!(l.spans.len(), 1);
    }

    #[test]
    fn test_line_from_span_vec() {
        let l: Line = vec![Span::raw("a"), Span::raw("b")].into();
        assert_eq!(l.spans.len(), 2);
    }

    #[test]
    fn test_line_render() {
        let mut buf = CellBuffer::new(20, 1);
        let l = Line::from_raw("abc");
        let next_x = l.render(&mut buf, 0, 0);
        assert_eq!(next_x, 3);
        assert_eq!(buf.get(0, 0).unwrap().ch, 'a');
        assert_eq!(buf.get(1, 0).unwrap().ch, 'b');
        assert_eq!(buf.get(2, 0).unwrap().ch, 'c');
    }

    #[test]
    fn test_line_render_with_offset() {
        let mut buf = CellBuffer::new(20, 1);
        let l = Line::from_raw("hi");
        let next_x = l.render(&mut buf, 5, 0);
        assert_eq!(next_x, 7);
        assert_eq!(buf.get(5, 0).unwrap().ch, 'h');
        assert_eq!(buf.get(6, 0).unwrap().ch, 'i');
    }

    #[test]
    fn test_line_render_multi_span() {
        let mut buf = CellBuffer::new(20, 1);
        let l = Line::from_spans(vec![
            Span::styled("ab", Style::new().fg(Color::RED)),
            Span::styled("cd", Style::new().fg(Color::BLUE)),
        ]);
        let next_x = l.render(&mut buf, 0, 0);
        assert_eq!(next_x, 4);
        assert_eq!(buf.get(0, 0).unwrap().style.fg, Some(Color::RED));
        assert_eq!(buf.get(2, 0).unwrap().style.fg, Some(Color::BLUE));
    }

    #[test]
    fn test_line_render_clips_at_boundary() {
        let mut buf = CellBuffer::new(3, 1);
        let l = Line::from_raw("abcdef");
        let next_x = l.render(&mut buf, 0, 0);
        assert_eq!(next_x, 6);
        assert_eq!(buf.get(0, 0).unwrap().ch, 'a');
        assert!(buf.get(3, 0).is_none());
    }

    #[test]
    fn test_line_equality() {
        let a = Line::from_raw("test");
        let b = Line::from_raw("test");
        assert_eq!(a, b);
    }

    #[test]
    fn test_span_equality() {
        let a = Span::raw("x");
        let b = Span::raw("x");
        assert_eq!(a, b);
    }

    #[test]
    fn test_display_width_ascii() {
        assert_eq!(display_width("hello"), 5);
        assert_eq!(display_width(""), 0);
    }

    #[test]
    fn test_display_width_unicode() {
        assert_eq!(display_width("\u{25c6}"), 1);
        assert_eq!(display_width("\u{25cf} sediman"), 9);
        assert_eq!(display_width("\u{25b8} Skills"), 8);
    }

    #[test]
    fn test_truncate_str_short() {
        assert_eq!(truncate_str("hi", 10), "hi");
    }

    #[test]
    fn test_truncate_str_exact() {
        assert_eq!(truncate_str("hello", 5), "hello");
    }

    #[test]
    fn test_truncate_str_truncates() {
        assert_eq!(truncate_str("hello world", 5), "hello");
    }

    #[test]
    fn test_truncate_str_unicode() {
        assert_eq!(truncate_str("\u{25c6}\u{25c7}\u{25c8}", 2), "\u{25c6}\u{25c7}");
    }

    #[test]
    fn test_truncate_str_empty() {
        assert_eq!(truncate_str("", 5), "");
    }

    #[test]
    fn test_display_width_empty() {
        assert_eq!(display_width(""), 0);
    }

    #[test]
    fn test_display_width_control_chars() {
        assert_eq!(display_width("\x00\x01\x02"), 3);
    }

    #[test]
    fn test_display_width_long_string() {
        let s: String = "a".repeat(1000);
        assert_eq!(display_width(&s), 1000);
    }

    #[test]
    fn test_truncate_str_zero() {
        assert_eq!(truncate_str("hello", 0), "");
    }

    #[test]
    fn test_truncate_str_multi_byte_boundary() {
        let s = "a\u{00e9}b\u{00e9}c"; // "aébéc"
        assert_eq!(truncate_str(s, 3), "a\u{00e9}b");
    }
}
