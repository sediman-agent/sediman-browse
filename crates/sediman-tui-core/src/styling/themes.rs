use super::theme::Theme;
use crate::renderer::Color;

fn nord() -> Theme {
    Theme::default()
}

fn tokyo_night() -> Theme {
    let primary       = Color::from_rgb(122, 162, 247);
    let secondary     = Color::from_rgb(187, 154, 247);
    let success       = Color::from_rgb(158, 206, 106);
    let error         = Color::from_rgb(247, 118, 142);
    let warning       = Color::from_rgb(224, 175, 104);
    let info          = Color::from_rgb(125, 207, 255);
    let text_muted    = Color::from_rgb(86, 95, 137);
    let text          = Color::from_rgb(169, 177, 214);
    let accent        = info;
    let background    = Color::from_rgb(26, 27, 38);
    let bg_panel      = Color::from_rgb(36, 40, 59);
    let border        = Color::from_rgb(59, 66, 97);

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
        text_emphasized: warning,
        background,
        background_panel: bg_panel,
        background_darker: Color::from_rgb(20, 21, 32),
        border,
        border_focused: primary,
        border_dim: bg_panel,
        user_message: primary,
        agent_message: text,
        // Markdown
        md_text: text,
        md_heading: secondary,
        md_link: primary,
        md_link_text: info,
        md_code: success,
        md_blockquote: warning,
        md_emph: warning,
        md_strong: accent,
        md_horizontal_rule: text_muted,
        md_list_item: primary,
        md_list_enum: info,
        md_code_block: text,
        // Syntax
        syntax_comment: text_muted,
        syntax_keyword: secondary,
        syntax_function: primary,
        syntax_variable: error,
        syntax_string: success,
        syntax_number: accent,
        syntax_type: warning,
        syntax_operator: info,
        syntax_punctuation: text,
    }
}

fn catppuccin_mocha() -> Theme {
    let primary       = Color::from_rgb(137, 180, 250);
    let secondary     = Color::from_rgb(203, 166, 247);
    let success       = Color::from_rgb(166, 227, 161);
    let error         = Color::from_rgb(243, 139, 168);
    let warning       = Color::from_rgb(249, 226, 175);
    let info          = Color::from_rgb(148, 226, 213);
    let text_muted    = Color::from_rgb(88, 91, 112);
    let text          = Color::from_rgb(205, 214, 244);
    let accent        = info;
    let background    = Color::from_rgb(30, 30, 46);
    let bg_panel      = Color::from_rgb(49, 50, 68);
    let border        = Color::from_rgb(69, 71, 90);

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
        text_emphasized: warning,
        background,
        background_panel: bg_panel,
        background_darker: Color::from_rgb(22, 22, 36),
        border,
        border_focused: primary,
        border_dim: bg_panel,
        user_message: primary,
        agent_message: text,
        md_text: text,
        md_heading: secondary,
        md_link: primary,
        md_link_text: info,
        md_code: success,
        md_blockquote: warning,
        md_emph: warning,
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
        syntax_type: warning,
        syntax_operator: info,
        syntax_punctuation: text,
    }
}

fn dracula() -> Theme {
    let primary       = Color::from_rgb(189, 147, 249);
    let secondary     = Color::from_rgb(139, 233, 253);
    let success       = Color::from_rgb(80, 250, 123);
    let error         = Color::from_rgb(255, 85, 85);
    let warning       = Color::from_rgb(241, 250, 140);
    let info          = Color::from_rgb(98, 114, 164);
    let text_muted    = Color::from_rgb(98, 114, 164);
    let text          = Color::from_rgb(248, 248, 242);
    let accent        = Color::from_rgb(255, 121, 198);
    let background    = Color::from_rgb(40, 42, 54);
    let bg_panel      = Color::from_rgb(40, 42, 54);
    let border        = Color::from_rgb(68, 71, 90);

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
        text_emphasized: warning,
        background,
        background_panel: bg_panel,
        background_darker: Color::from_rgb(30, 32, 44),
        border,
        border_focused: primary,
        border_dim: bg_panel,
        user_message: primary,
        agent_message: text,
        md_text: text,
        md_heading: secondary,
        md_link: primary,
        md_link_text: secondary,
        md_code: success,
        md_blockquote: warning,
        md_emph: warning,
        md_strong: accent,
        md_horizontal_rule: text_muted,
        md_list_item: primary,
        md_list_enum: secondary,
        md_code_block: text,
        syntax_comment: text_muted,
        syntax_keyword: secondary,
        syntax_function: primary,
        syntax_variable: error,
        syntax_string: success,
        syntax_number: accent,
        syntax_type: warning,
        syntax_operator: secondary,
        syntax_punctuation: text,
    }
}

pub fn builtin_themes() -> Vec<(&'static str, Theme)> {
    vec![
        ("nord", nord()),
        ("tokyo-night", tokyo_night()),
        ("catppuccin-mocha", catppuccin_mocha()),
        ("dracula", dracula()),
    ]
}

pub fn list_theme_names() -> Vec<String> {
    let mut names = vec!["default".to_string()];
    for (name, _) in builtin_themes() {
        names.push(name.to_string());
    }
    names
}

pub fn load_theme(name: &str) -> Option<Theme> {
    if name == "default" || name == "nord" {
        return Some(Theme::default());
    }
    builtin_themes().into_iter().find(|(n, _)| *n == name).map(|(_, t)| t)
}

pub fn load_theme_from_file(path: &str) -> Option<Theme> {
    let data = std::fs::read_to_string(path).ok()?;
    let overrides: std::collections::HashMap<String, String> = serde_json::from_str(&data).ok()?;
    if overrides.is_empty() {
        return None;
    }
    let mut theme = Theme::default();
    let get_color = |field: &str| -> Option<Color> {
        overrides.get(field).and_then(|hex| parse_hex(hex))
    };
    if let Some(c) = get_color("primary") { theme.primary = c; }
    if let Some(c) = get_color("secondary") { theme.secondary = c; }
    if let Some(c) = get_color("accent") { theme.accent = c; }
    if let Some(c) = get_color("error") { theme.error = c; }
    if let Some(c) = get_color("warning") { theme.warning = c; }
    if let Some(c) = get_color("success") { theme.success = c; }
    if let Some(c) = get_color("info") { theme.info = c; }
    if let Some(c) = get_color("text") { theme.text = c; }
    if let Some(c) = get_color("text_muted") { theme.text_muted = c; }
    if let Some(c) = get_color("text_emphasized") { theme.text_emphasized = c; }
    if let Some(c) = get_color("background") { theme.background = c; }
    if let Some(c) = get_color("background_panel") { theme.background_panel = c; }
    if let Some(c) = get_color("background_darker") { theme.background_darker = c; }
    if let Some(c) = get_color("border") { theme.border = c; }
    if let Some(c) = get_color("border_focused") { theme.border_focused = c; }
    if let Some(c) = get_color("border_dim") { theme.border_dim = c; }
    Some(theme)
}

fn parse_hex(s: &str) -> Option<Color> {
    let s = s.trim().trim_start_matches('#');
    if s.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&s[0..2], 16).ok()?;
    let g = u8::from_str_radix(&s[2..4], 16).ok()?;
    let b = u8::from_str_radix(&s[4..6], 16).ok()?;
    Some(Color::from_rgb(r, g, b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_list_theme_names() {
        let names = list_theme_names();
        assert!(names.contains(&"default".to_string()));
        assert!(names.contains(&"nord".to_string()));
        assert!(names.contains(&"tokyo-night".to_string()));
        assert!(names.contains(&"catppuccin-mocha".to_string()));
        assert!(names.contains(&"dracula".to_string()));
    }

    #[test]
    fn test_builtin_themes_count() {
        let themes = builtin_themes();
        assert_eq!(themes.len(), 4);
    }

    #[test]
    fn test_load_theme_default() {
        let theme = load_theme("default").unwrap();
        assert_eq!(theme.background, Theme::default().background);
    }

    #[test]
    fn test_load_theme_nord() {
        let theme = load_theme("nord").unwrap();
        assert_eq!(theme.background, Theme::default().background);
    }

    #[test]
    fn test_load_theme_tokyo_night() {
        let theme = load_theme("tokyo-night").unwrap();
        assert_eq!(theme.primary, Color::from_rgb(122, 162, 247));
        assert_eq!(theme.background, Color::from_rgb(26, 27, 38));
    }

    #[test]
    fn test_load_theme_catppuccin_mocha() {
        let theme = load_theme("catppuccin-mocha").unwrap();
        assert_eq!(theme.primary, Color::from_rgb(137, 180, 250));
        assert_eq!(theme.background, Color::from_rgb(30, 30, 46));
    }

    #[test]
    fn test_load_theme_dracula() {
        let theme = load_theme("dracula").unwrap();
        assert_eq!(theme.primary, Color::from_rgb(189, 147, 249));
        assert_eq!(theme.accent, Color::from_rgb(255, 121, 198));
    }

    #[test]
    fn test_load_theme_unknown() {
        assert!(load_theme("nonexistent").is_none());
    }

    #[test]
    fn test_load_theme_empty() {
        assert!(load_theme("").is_none());
    }

    #[test]
    fn test_load_theme_from_file() {
        assert!(load_theme_from_file("/some/path").is_none());
    }

    #[test]
    fn test_themes_have_distinct_backgrounds() {
        let themes = builtin_themes();
        let bgs: Vec<_> = themes.iter().map(|(_, t)| t.background.to_rgb()).collect();
        let unique: std::collections::HashSet<_> = bgs.iter().collect();
        assert!(unique.len() >= 2, "Themes should have different backgrounds");
    }

    #[test]
    fn test_each_builtin_loadable_by_name() {
        for (name, _) in builtin_themes() {
            assert!(load_theme(name).is_some(), "Failed to load theme: {}", name);
        }
    }
}
