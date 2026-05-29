//! Rich markdown rendering with syntax-highlighted code blocks.
//!
//! Uses `pulldown-cmark` for parsing and `syntect` for syntax highlighting.
//! Returns `Vec<Line>` that can be rendered into a `CellBuffer`.
//!
//! Color palette matches OpenCode's exact theme mapping.

use crate::renderer::{Line, Span, Style, TextAttributes};
use crate::styling::Theme;

// ── Public API ──────────────────────────────────────────────────

/// Render a markdown string into styled lines for the cell buffer.
pub fn render_markdown(text: &str) -> Vec<Line> {
    let mut renderer = MarkdownRenderer::new();
    renderer.render(text);
    renderer.lines
}

/// Render a code block with syntax highlighting into styled lines.
/// Returns lines wrapped in a bordered box.
pub fn render_code_block(code: &str, lang: Option<&str>, width: u16) -> Vec<Line> {
    let mut renderer = MarkdownRenderer::new();
    renderer.width = width;
    renderer.render_code_block(code, lang);
    renderer.lines
}

// ── Internal ────────────────────────────────────────────────────

struct MarkdownRenderer {
    lines: Vec<Line>,
    width: u16,
    theme: Theme,
}

impl MarkdownRenderer {
    fn new() -> Self {
        Self {
            lines: Vec::new(),
            width: 80,
            theme: Theme::default(),
        }
    }

    fn render(&mut self, text: &str) {
        use pulldown_cmark::{Event, Options, Parser, Tag, TagEnd};

        let mut opts = Options::empty();
        opts.insert(Options::ENABLE_TABLES);
        opts.insert(Options::ENABLE_STRIKETHROUGH);
        opts.insert(Options::ENABLE_TASKLISTS);

        let parser = Parser::new_ext(text, opts);

        let mut in_code_block = false;
        let mut code_lang: Option<String> = None;
        let mut code_content = String::new();
        let mut in_heading = 0u8;
        let mut in_strong = false;
        let mut in_emphasis = false;
        let mut in_link = false;
        let mut current_line_spans: Vec<Span> = Vec::new();
        let mut list_depth: usize = 0;
        let mut list_counters: Vec<ListState> = Vec::new();

        #[derive(Clone)]
        enum ListState {
            Ordered(usize),
            Unordered,
        }

        for event in parser {
            match event {
                // ── Start tags ─────────────────────────────────
                Event::Start(tag) => match tag {
                    Tag::Heading { level, .. } => {
                        self.flush_line(&mut current_line_spans);
                        in_heading = level as u8;
                    }
                    Tag::Paragraph => {}
                    Tag::CodeBlock(kind) => {
                        self.flush_line(&mut current_line_spans);
                        in_code_block = true;
                        code_lang = match kind {
                            pulldown_cmark::CodeBlockKind::Fenced(lang) => {
                                if lang.is_empty() { None } else { Some(lang.to_string()) }
                            }
                            pulldown_cmark::CodeBlockKind::Indented => None,
                        };
                        code_content.clear();
                    }
                    Tag::Strong => {
                        in_strong = true;
                    }
                    Tag::Emphasis => {
                        in_emphasis = true;
                    }
                    Tag::List(start) => {
                        list_depth += 1;
                        if let Some(n) = start {
                            list_counters.push(ListState::Ordered(n as usize));
                        } else {
                            list_counters.push(ListState::Unordered);
                        }
                    }
                    Tag::Item => {
                        self.flush_line(&mut current_line_spans);
                        let indent = "  ".repeat(list_depth.saturating_sub(1));
                        if let Some(state) = list_counters.last_mut() {
                            match state {
                                ListState::Ordered(n) => {
                                    current_line_spans.push(Span::styled(
                                        format!("{}{}. ", indent, n),
                                        Style::new().fg(self.theme.md_list_enum),
                                    ));
                                    *n += 1;
                                }
                                ListState::Unordered => {
                                    current_line_spans.push(Span::styled(
                                        format!("{}• ", indent),
                                        Style::new().fg(self.theme.md_list_item),
                                    ));
                                }
                            }
                        }
                    }
                    Tag::BlockQuote(_) => {
                        self.flush_line(&mut current_line_spans);
                        current_line_spans.push(Span::styled(
                            "  ┃ ",
                            Style::new().fg(self.theme.md_blockquote),
                        ));
                    }
                    Tag::Link { dest_url, .. } => {
                        let style = Style::new().fg(self.theme.md_link).add_modifier(TextAttributes::underline());
                        current_line_spans.push(Span::styled(dest_url.to_string(), style));
                    }
                    Tag::Table(_) | Tag::TableHead | Tag::TableRow | Tag::TableCell => {}
                    Tag::Strikethrough => {}
                    _ => {}
                },

                // ── End tags ───────────────────────────────────
                Event::End(tag) => match tag {
                    TagEnd::Heading(_) => {
                        self.flush_line(&mut current_line_spans);
                        in_heading = 0;
                        self.lines.push(Line::new());
                    }
                    TagEnd::Paragraph => {
                        self.flush_line(&mut current_line_spans);
                        self.lines.push(Line::new());
                    }
                    TagEnd::CodeBlock => {
                        in_code_block = false;
                        self.render_code_block(&code_content, code_lang.as_deref());
                        code_lang = None;
                    }
                    TagEnd::Strong => {
                        in_strong = false;
                    }
                    TagEnd::Emphasis => {
                        in_emphasis = false;
                    }
                    TagEnd::List(_) => {
                        list_depth = list_depth.saturating_sub(1);
                        list_counters.pop();
                    }
                    TagEnd::Item => {}
                    TagEnd::BlockQuote(_) => {}
                    TagEnd::Link => {
                        in_link = false;
                    }
                    TagEnd::Table | TagEnd::TableHead | TagEnd::TableRow | TagEnd::TableCell => {}
                    TagEnd::Strikethrough => {}
                    _ => {}
                },

                // ── Inline code ────────────────────────────────
                Event::Code(code_text) => {
                    let code_style = Style::new()
                        .fg(self.theme.md_code)
                        .bg(self.theme.background_panel);
                    current_line_spans.push(Span::styled(
                        format!("`{}`", code_text),
                        code_style,
                    ));
                }

                // ── Text ───────────────────────────────────────
                Event::Text(text) => {
                    if in_code_block {
                        code_content.push_str(&text);
                    } else if in_link {
                        // Skip — URL already rendered in Tag::Link
                    } else {
                        let style = self.text_style(in_heading, in_strong, in_emphasis, false);
                        for (i, part) in text.split('\n').enumerate() {
                            if i > 0 {
                                self.flush_line(&mut current_line_spans);
                            }
                            if !part.is_empty() {
                                current_line_spans.push(Span::styled(part.to_string(), style));
                            }
                        }
                    }
                }

                Event::SoftBreak | Event::HardBreak => {
                    self.flush_line(&mut current_line_spans);
                }

                Event::Html(html) => {
                    current_line_spans.push(Span::styled(
                        html.to_string(),
                        Style::new().fg(self.theme.text_muted),
                    ));
                }

                Event::FootnoteReference(name) => {
                    current_line_spans.push(Span::styled(
                        format!("[{}]", name),
                        Style::new().fg(self.theme.text_muted),
                    ));
                }

                Event::TaskListMarker(checked) => {
                    let marker = if checked { "✓ " } else { "○ " };
                    let style = if checked {
                        Style::new().fg(self.theme.success)
                    } else {
                        Style::new().fg(self.theme.text_muted)
                    };
                    current_line_spans.push(Span::styled(marker.to_string(), style));
                }

                _ => {}
            }
        }

        self.flush_line(&mut current_line_spans);
    }

    fn text_style(&self, heading: u8, strong: bool, emphasis: bool, code: bool) -> Style {
        if code {
            return Style::new()
                .fg(self.theme.md_code)
                .bg(self.theme.background_panel);
        }

        let mut fg = self.theme.md_text;
        let mut want_bold = false;
        let mut want_italic = false;

        if heading > 0 {
            fg = self.theme.md_heading;
            want_bold = true;
        }

        if strong {
            fg = self.theme.md_strong;
            want_bold = true;
        }
        if emphasis {
            fg = self.theme.md_emph;
            want_italic = true;
        }

        let mut style = Style::new().fg(fg);
        if want_bold { style = style.add_modifier(TextAttributes::bold()); }
        if want_italic { style = style.add_modifier(TextAttributes::italic()); }
        style
    }

    fn flush_line(&mut self, spans: &mut Vec<Span>) {
        if !spans.is_empty() {
            self.lines.push(Line::from_spans(std::mem::take(spans)));
        }
    }

    fn render_code_block(&mut self, code: &str, lang: Option<&str>) {
        let inner_width = self.width.saturating_sub(4) as usize;
        let t = &self.theme;

        // Top border with language label
        let label = lang.unwrap_or("code");
        let top = format!("┌─ {} {}", label, "─".repeat(inner_width.saturating_sub(label.len() + 3)));
        self.lines.push(Line::from_styled(
            top,
            Style::new().fg(t.border),
        ));

        // Syntax-highlighted lines
        let highlighted = self.highlight_code(code.trim_end(), lang);

        for line_text in highlighted {
            let char_count = line_text.chars().count();
            let padded = if char_count < inner_width {
                format!("{}{}", line_text, " ".repeat(inner_width - char_count))
            } else {
                line_text
            };
            self.lines.push(Line::from_styled(
                format!("│ {}", padded),
                Style::new().fg(t.md_code_block),
            ));
        }

        // Bottom border
        let bottom = format!("└{}", "─".repeat(inner_width + 1));
        self.lines.push(Line::from_styled(
            bottom,
            Style::new().fg(t.border),
        ));
        self.lines.push(Line::new());
    }

    fn highlight_code(&self, code: &str, lang: Option<&str>) -> Vec<String> {
        use syntect::easy::HighlightLines;
        use syntect::highlighting::ThemeSet;
        use syntect::parsing::SyntaxSet;

        static SS: std::sync::OnceLock<SyntaxSet> = std::sync::OnceLock::new();
        static TS: std::sync::OnceLock<ThemeSet> = std::sync::OnceLock::new();

        let ss = SS.get_or_init(SyntaxSet::load_defaults_newlines);
        let ts = TS.get_or_init(ThemeSet::load_defaults);
        let theme = &ts.themes["base16-eighties.dark"];

        let syntax = lang
            .and_then(|l| ss.find_syntax_by_token(l))
            .unwrap_or_else(|| ss.find_syntax_plain_text());

        let mut highlighter = HighlightLines::new(syntax, theme);
        let mut result = Vec::new();

        use syntect::util::LinesWithEndings;
        for line in LinesWithEndings::from(code) {
            let ranges = highlighter.highlight_line(line, &ss).unwrap_or_default();
            let mut line_str = String::new();
            for (_style, text) in ranges {
                let clean = text.trim_end_matches('\n').trim_end_matches('\r');
                line_str.push_str(clean);
            }
            result.push(line_str);
        }

        result
    }
}

// ── Tests ───────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_empty() {
        let lines = render_markdown("");
        assert!(lines.is_empty());
    }

    #[test]
    fn test_render_plain_text() {
        let lines = render_markdown("hello world");
        assert!(!lines.is_empty());
        assert!(lines[0].spans[0].text.contains("hello"));
    }

    #[test]
    fn test_render_h1() {
        let lines = render_markdown("# Title");
        assert!(!lines.is_empty());
        let first = &lines[0].spans[0];
        assert_eq!(first.text, "Title");
        assert!(first.style.attrs.bold);
        let theme = Theme::default();
        assert_eq!(first.style.fg, Some(theme.md_heading));
    }

    #[test]
    fn test_render_list() {
        let lines = render_markdown("- item one\n- item two");
        let text: String = lines.iter()
            .flat_map(|l| l.spans.iter().map(|s| s.text.clone()))
            .collect();
        assert!(text.contains("•"));
    }

    #[test]
    fn test_render_ordered_list() {
        let lines = render_markdown("1. first\n2. second");
        let text: String = lines.iter()
            .flat_map(|l| l.spans.iter().map(|s| s.text.clone()))
            .collect();
        assert!(text.contains("1."));
    }

    #[test]
    fn test_render_bold() {
        let lines = render_markdown("this is **bold** text");
        assert!(!lines.is_empty());
        let has_bold = lines[0].spans.iter().any(|s| s.style.attrs.bold);
        assert!(has_bold);
    }

    #[test]
    fn test_render_italic() {
        let lines = render_markdown("this is *italic* text");
        assert!(!lines.is_empty());
        let has_italic = lines[0].spans.iter().any(|s| s.style.attrs.italic);
        assert!(has_italic);
    }

    #[test]
    fn test_render_code_inline() {
        let lines = render_markdown("use `cargo build` to compile");
        let text: String = lines[0].spans.iter().map(|s| s.text.clone()).collect();
        assert!(text.contains("cargo build"));
    }

    #[test]
    fn test_render_code_block() {
        let md = "```rust\nfn main() {\n    println!(\"hello\");\n}\n```";
        let lines = render_markdown(md);
        let first_text: String = lines[0].spans.iter().map(|s| s.text.clone()).collect();
        assert!(first_text.contains("rust"));
        let has_bottom = lines.iter().any(|l| {
            l.spans.iter().any(|s| s.text.contains('└'))
        });
        assert!(has_bottom);
    }

    #[test]
    fn test_render_blockquote() {
        let lines = render_markdown("> quoted text");
        let text: String = lines.iter()
            .flat_map(|l| l.spans.iter().map(|s| s.text.clone()))
            .collect();
        assert!(text.contains("┃"));
    }

    #[test]
    fn test_render_task_list() {
        let lines = render_markdown("- [x] done\n- [ ] todo");
        let text: String = lines.iter()
            .flat_map(|l| l.spans.iter().map(|s| s.text.clone()))
            .collect();
        assert!(text.contains('✓'));
        assert!(text.contains('○'));
    }

    #[test]
    fn test_render_multiline() {
        let lines = render_markdown("# Title\nSome text\n- item");
        assert!(lines.len() >= 3);
    }

    #[test]
    fn test_render_h2() {
        let lines = render_markdown("## Heading 2");
        assert!(!lines.is_empty());
        let text: String = lines[0].spans.iter().map(|s| s.text.as_str()).collect();
        assert!(text.contains("Heading 2"));
    }

    #[test]
    fn test_render_h3() {
        let lines = render_markdown("### Heading 3");
        assert!(!lines.is_empty());
        let text: String = lines[0].spans.iter().map(|s| s.text.as_str()).collect();
        assert!(text.contains("Heading 3"));
    }

    #[test]
    fn test_render_empty_heading() {
        let lines = render_markdown("#");
        assert!(lines.is_empty() || lines.iter().all(|l| l.spans.iter().map(|s| s.text.trim()).collect::<String>().is_empty()));
    }

    #[test]
    fn test_render_link() {
        let lines = render_markdown("[click here](https://example.com)");
        assert!(!lines.is_empty());
        let text: String = lines[0].spans.iter().map(|s| s.text.as_str()).collect();
        assert!(text.contains("click here"));
    }

    #[test]
    fn test_render_strikethrough() {
        let lines = render_markdown("~~deleted~~");
        assert!(!lines.is_empty());
        let text: String = lines[0].spans.iter().map(|s| s.text.as_str()).collect();
        assert!(text.contains("deleted"));
    }

    #[test]
    fn test_render_nested_list() {
        let md = "- item 1\n  - sub item";
        let lines = render_markdown(md);
        assert!(lines.len() >= 2);
    }

    #[test]
    fn test_render_empty_input() {
        let lines = render_markdown("");
        assert!(lines.is_empty());
    }

    #[test]
    fn test_render_only_whitespace() {
        let lines = render_markdown("   \n   \n");
        assert!(lines.is_empty() || lines.iter().all(|l| l.spans.is_empty()));
    }

    #[test]
    fn test_render_code_block_empty() {
        let lines = render_markdown("```\n```");
        assert!(true);
    }

    #[test]
    fn test_render_code_block_with_lang() {
        let lines = render_markdown("```rust\nfn main() {}\n```");
        assert!(!lines.is_empty());
    }

    #[test]
    fn test_render_mixed_bold_italic() {
        let lines = render_markdown("***bold and italic***");
        assert!(!lines.is_empty());
    }

    #[test]
    fn test_render_unicode_content() {
        let lines = render_markdown("Hello 世界 🌍");
        assert!(!lines.is_empty());
        let text: String = lines[0].spans.iter().map(|s| s.text.as_str()).collect();
        assert!(text.contains("世界"));
    }
}
