use crossterm::event::{KeyCode, KeyEvent};
use ratatui::{
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

pub struct TextEditor {
    buffer: String,
    cursor: usize,
    history: Vec<String>,
    history_pos: Option<usize>,
    prompt: String,
}

impl TextEditor {
    pub fn new() -> Self {
        Self {
            buffer: String::new(),
            cursor: 0,
            history: Vec::new(),
            history_pos: None,
            prompt: String::new(),
        }
    }

    pub fn set_prompt(&mut self, prompt: &str) {
        self.prompt = prompt.to_string();
    }

    pub fn lines(&self) -> Vec<String> {
        self.buffer.lines().map(|s| s.to_string()).collect()
    }

    pub fn input(&mut self, key: KeyEvent) -> bool {
        match key.code {
            KeyCode::Char(c) => {
                self.buffer.insert(self.cursor, c);
                self.cursor += 1;
                true
            }
            KeyCode::Backspace => {
                if self.cursor > 0 {
                    self.cursor -= 1;
                    self.buffer.remove(self.cursor);
                }
                true
            }
            KeyCode::Delete => {
                if self.cursor < self.buffer.len() {
                    self.buffer.remove(self.cursor);
                }
                true
            }
            KeyCode::Left => {
                if self.cursor > 0 {
                    self.cursor -= 1;
                }
                true
            }
            KeyCode::Right => {
                if self.cursor < self.buffer.len() {
                    self.cursor += 1;
                }
                true
            }
            KeyCode::Home => {
                self.cursor = 0;
                true
            }
            KeyCode::End => {
                self.cursor = self.buffer.len();
                true
            }
            KeyCode::Enter => {
                self.buffer.insert(self.cursor, '\n');
                self.cursor += 1;
                true
            }
            KeyCode::Tab | KeyCode::BackTab => {
                // insert 2 spaces for tab
                for _ in 0..2 {
                    self.buffer.insert(self.cursor, ' ');
                    self.cursor += 1;
                }
                true
            }
            KeyCode::Esc => true,   // handled by event loop
            KeyCode::F(_) => true,  // function keys: ignore silently
            KeyCode::Up | KeyCode::Down => true, // handled by event loop
            KeyCode::Insert | KeyCode::PageUp | KeyCode::PageDown => true,
            KeyCode::Null => true,
            KeyCode::CapsLock | KeyCode::ScrollLock | KeyCode::NumLock => true,
            KeyCode::PrintScreen | KeyCode::Pause | KeyCode::Menu => true,
            _ => {
                true
            }
        }
    }

    pub fn submit(&mut self) -> String {
        let input = self.buffer.trim().to_string();
        if !input.is_empty() {
            self.history.push(input.clone());
        }
        self.buffer.clear();
        self.cursor = 0;
        self.history_pos = None;
        input
    }

    pub fn history_up(&mut self) {
        if self.history.is_empty() {
            return;
        }
        let pos = self.history_pos.unwrap_or(self.history.len());
        if pos > 0 {
            let new_pos = pos - 1;
            self.history_pos = Some(new_pos);
            self.buffer = self.history[new_pos].clone();
            self.cursor = self.buffer.len();
        }
    }

    pub fn history_down(&mut self) {
        match self.history_pos {
            Some(p) if p < self.history.len() - 1 => {
                let new_pos = p + 1;
                self.history_pos = Some(new_pos);
                self.buffer = self.history[new_pos].clone();
                self.cursor = self.buffer.len();
            }
            _ => {
                self.history_pos = None;
                self.buffer.clear();
                self.cursor = 0;
            }
        }
    }

    pub fn delete_line_by_head(&mut self) {
        self.buffer.clear();
        self.cursor = 0;
    }

    pub fn insert_str(&mut self, s: &str) {
        self.buffer.insert_str(self.cursor, s);
        self.cursor += s.len();
    }

    pub fn render(&self, frame: &mut Frame, area: Rect) {
        let prompt_span = Span::styled(
            self.prompt.as_str(),
            Style::new().fg(Color::Cyan),
        );
        let text_spans: Vec<Span> = self
            .buffer
            .chars()
            .enumerate()
            .map(|(i, c)| {
                if i == self.cursor {
                    Span::styled(
                        c.to_string(),
                        Style::new().fg(Color::White).bg(Color::DarkGray),
                    )
                } else {
                    Span::raw(c.to_string())
                }
            })
            .collect();

        let mut line = vec![prompt_span];
        line.extend(text_spans);

        if self.cursor >= self.buffer.len() {
            line.push(Span::styled(" ", Style::new().bg(Color::DarkGray)));
        }

        let paragraph = Paragraph::new(Text::from(Line::from(line)))
            .block(
                Block::default()
                    .borders(Borders::TOP)
                    .border_style(Style::new().fg(Color::DarkGray)),
            );
        frame.render_widget(paragraph, area);
    }
}

impl Default for TextEditor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    fn char_key(c: char) -> KeyEvent {
        key(KeyCode::Char(c))
    }

    #[test]
    fn test_new_editor_empty() {
        let ed = TextEditor::new();
        assert_eq!(ed.buffer, "");
        assert_eq!(ed.cursor, 0);
        assert!(ed.lines().is_empty());
    }

    #[test]
    fn test_insert_char() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        assert_eq!(ed.buffer, "a");
        assert_eq!(ed.cursor, 1);
    }

    #[test]
    fn test_insert_multiple_chars() {
        let mut ed = TextEditor::new();
        ed.input(char_key('h'));
        ed.input(char_key('e'));
        ed.input(char_key('l'));
        ed.input(char_key('l'));
        ed.input(char_key('o'));
        assert_eq!(ed.buffer, "hello");
        assert_eq!(ed.cursor, 5);
    }

    #[test]
    fn test_insert_in_middle() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.input(char_key('c'));
        ed.input(key(KeyCode::Left));
        ed.input(char_key('b'));
        assert_eq!(ed.buffer, "abc");
        assert_eq!(ed.cursor, 2);
    }

    #[test]
    fn test_backspace() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.input(char_key('b'));
        ed.input(char_key('c'));
        ed.input(key(KeyCode::Backspace));
        assert_eq!(ed.buffer, "ab");
        assert_eq!(ed.cursor, 2);
    }

    #[test]
    fn test_backspace_at_start() {
        let mut ed = TextEditor::new();
        ed.input(key(KeyCode::Backspace));
        assert_eq!(ed.buffer, "");
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_delete() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.input(char_key('b'));
        ed.input(char_key('c'));
        ed.input(key(KeyCode::Left));
        ed.input(key(KeyCode::Left));
        ed.input(key(KeyCode::Delete));
        assert_eq!(ed.buffer, "ac");
    }

    #[test]
    fn test_cursor_movement() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.input(char_key('b'));
        ed.input(char_key('c'));
        ed.input(key(KeyCode::Left));
        assert_eq!(ed.cursor, 2);
        ed.input(key(KeyCode::Right));
        assert_eq!(ed.cursor, 3);
        ed.input(key(KeyCode::Home));
        assert_eq!(ed.cursor, 0);
        ed.input(key(KeyCode::End));
        assert_eq!(ed.cursor, 3);
    }

    #[test]
    fn test_cursor_bounds() {
        let mut ed = TextEditor::new();
        ed.input(key(KeyCode::Left));
        assert_eq!(ed.cursor, 0);
        ed.input(key(KeyCode::Right));
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_submit_empty() {
        let mut ed = TextEditor::new();
        assert_eq!(ed.submit(), "");
        assert!(ed.history.is_empty());
    }

    #[test]
    fn test_submit_returns_and_clears() {
        let mut ed = TextEditor::new();
        ed.input(char_key('t'));
        ed.input(char_key('e'));
        ed.input(char_key('s'));
        ed.input(char_key('t'));
        assert_eq!(ed.submit(), "test");
        assert_eq!(ed.buffer, "");
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_submit_adds_to_history() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.submit();
        assert_eq!(ed.history.len(), 1);
        assert_eq!(ed.history[0], "a");
    }

    #[test]
    fn test_history_up_down() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.submit();
        ed.input(char_key('b'));
        ed.submit();

        ed.history_up();
        assert_eq!(ed.buffer, "b");
        ed.history_up();
        assert_eq!(ed.buffer, "a");
        ed.history_down();
        assert_eq!(ed.buffer, "b");
        ed.history_down();
        assert_eq!(ed.buffer, "");
    }

    #[test]
    fn test_history_up_empty() {
        let mut ed = TextEditor::new();
        ed.history_up();
        assert_eq!(ed.buffer, "");
    }

    #[test]
    fn test_history_down_from_start() {
        let mut ed = TextEditor::new();
        ed.history_down();
        assert_eq!(ed.buffer, "");
    }

    #[test]
    fn test_delete_line_by_head() {
        let mut ed = TextEditor::new();
        ed.input(char_key('a'));
        ed.input(char_key('b'));
        ed.delete_line_by_head();
        assert_eq!(ed.buffer, "");
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_insert_str() {
        let mut ed = TextEditor::new();
        ed.insert_str("hello");
        assert_eq!(ed.buffer, "hello");
        assert_eq!(ed.cursor, 5);
    }

    #[test]
    fn test_insert_str_at_middle() {
        let mut ed = TextEditor::new();
        ed.insert_str("ac");
        ed.input(key(KeyCode::Left));
        ed.insert_str("b");
        assert_eq!(ed.buffer, "abc");
    }

    #[test]
    fn test_set_prompt() {
        let mut ed = TextEditor::new();
        ed.set_prompt(" [1] > ");
        assert_eq!(ed.prompt, " [1] > ");
    }

    #[test]
    fn test_lines() {
        let mut ed = TextEditor::new();
        ed.insert_str("hello\nworld");
        let lines = ed.lines();
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0], "hello");
        assert_eq!(lines[1], "world");
    }

    #[test]
    fn test_submit_trims() {
        let mut ed = TextEditor::new();
        ed.insert_str("  hello  ");
        assert_eq!(ed.submit(), "hello");
    }

    #[test]
    fn test_unknown_key_handled_silently() {
        let mut ed = TextEditor::new();
        // All keys should be absorbed without error
        assert!(ed.input(key(KeyCode::F(1))));
        assert!(ed.input(key(KeyCode::F(24))));
    }

    // ── Edge case tests ──

    #[test]
    fn test_empty_submit_does_not_add_to_history() {
        let mut ed = TextEditor::new();
        ed.submit();
        assert!(ed.history.is_empty());
    }

    #[test]
    fn test_whitespace_only_submit() {
        let mut ed = TextEditor::new();
        ed.insert_str("   ");
        assert_eq!(ed.submit(), "");
        assert!(ed.history.is_empty());
    }

    #[test]
    fn test_cursor_at_start_after_submit() {
        let mut ed = TextEditor::new();
        ed.insert_str("hello");
        ed.input(key(KeyCode::Left));
        ed.submit();
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_history_preserves_order() {
        let mut ed = TextEditor::new();
        ed.insert_str("first"); ed.submit();
        ed.insert_str("second"); ed.submit();
        ed.insert_str("third"); ed.submit();
        ed.history_up();
        assert_eq!(ed.buffer, "third");
        ed.history_up();
        assert_eq!(ed.buffer, "second");
        ed.history_up();
        assert_eq!(ed.buffer, "first");
    }

    #[test]
    fn test_cursor_out_of_bounds_on_empty() {
        let mut ed = TextEditor::new();
        ed.input(key(KeyCode::Left));
        assert_eq!(ed.cursor, 0);
        ed.input(key(KeyCode::Right));
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_backspace_at_cursor_zero() {
        let mut ed = TextEditor::new();
        ed.insert_str("ab");
        ed.input(key(KeyCode::Left));
        ed.input(key(KeyCode::Left));
        ed.input(key(KeyCode::Backspace));
        assert_eq!(ed.buffer, "ab");
    }

    #[test]
    fn test_delete_at_buffer_end() {
        let mut ed = TextEditor::new();
        ed.insert_str("abc");
        ed.input(key(KeyCode::Delete));
        assert_eq!(ed.buffer, "abc");
    }

    #[test]
    fn test_insert_in_middle_with_cursor() {
        let mut ed = TextEditor::new();
        ed.insert_str("ac");
        ed.input(key(KeyCode::Left));
        ed.input(char_key('b'));
        assert_eq!(ed.buffer, "abc");
        assert_eq!(ed.cursor, 2);
    }

    #[test]
    fn test_history_up_on_empty_history() {
        let mut ed = TextEditor::new();
        ed.history_up();
        assert_eq!(ed.buffer, "");
    }

    #[test]
    fn test_history_down_on_empty_history() {
        let mut ed = TextEditor::new();
        ed.history_down();
        assert_eq!(ed.buffer, "");
    }

    #[test]
    fn test_rapid_submit_accumulates_history() {
        let mut ed = TextEditor::new();
        for i in 0..10 {
            ed.insert_str(&i.to_string());
            ed.submit();
        }
        assert_eq!(ed.history.len(), 10);
        assert_eq!(ed.history[9], "9");
    }

    #[test]
    fn test_untrimmed_submit() {
        let mut ed = TextEditor::new();
        ed.insert_str("hello ");
        assert_eq!(ed.submit(), "hello");
        assert_eq!(ed.history[0], "hello");
    }

    #[test]
    fn test_cursor_does_not_go_below_zero() {
        let mut ed = TextEditor::new();
        for _ in 0..5 {
            ed.input(key(KeyCode::Left));
        }
        assert_eq!(ed.cursor, 0);
    }

    #[test]
    fn test_cursor_does_not_exceed_buffer() {
        let mut ed = TextEditor::new();
        ed.insert_str("hi");
        for _ in 0..5 {
            ed.input(key(KeyCode::Right));
        }
        assert_eq!(ed.cursor, 2);
    }
}
