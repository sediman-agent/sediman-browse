use super::theme::{Theme, ThemeColors, parse_hex};
use crate::renderer::Color;
use std::collections::HashMap;
use std::path::PathBuf;

fn nord() -> Theme {
    ThemeColors {
        primary: "#88c0d0".into(), secondary: "#81a1c1".into(), accent: "#b48ead".into(),
        error: "#bf616a".into(), warning: "#ebcb8b".into(), success: "#a3be8c".into(),
        info: "#5e81ac".into(), text: "#d8dee9".into(), text_muted: "#616e88".into(),
        text_emphasized: "#ebcb8b".into(), background: "#2e3440".into(),
        background_panel: "#3b4252".into(), background_darker: "#242933".into(),
    }.to_theme()
}

fn tokyo_night() -> Theme {
    ThemeColors {
        primary: "#7aa2f7".into(), secondary: "#bb9af7".into(), accent: "#7dcfff".into(),
        error: "#f7768e".into(), warning: "#e0af68".into(), success: "#9ece6a".into(),
        info: "#7dcfff".into(), text: "#a9b1d6".into(), text_muted: "#565f89".into(),
        text_emphasized: "#e0af68".into(), background: "#1a1b26".into(),
        background_panel: "#24283b".into(), background_darker: "#141521".into(),
    }.to_theme()
}

fn catppuccin_mocha() -> Theme {
    ThemeColors {
        primary: "#89b4fa".into(), secondary: "#cba6f7".into(), accent: "#94e2d5".into(),
        error: "#f38ba8".into(), warning: "#f9e2af".into(), success: "#a6e3a1".into(),
        info: "#94e2d5".into(), text: "#cdd6f4".into(), text_muted: "#585b70".into(),
        text_emphasized: "#f9e2af".into(), background: "#1e1e2e".into(),
        background_panel: "#313244".into(), background_darker: "#16161e".into(),
    }.to_theme()
}

fn dracula() -> Theme {
    ThemeColors {
        primary: "#bd93f9".into(), secondary: "#8be9fd".into(), accent: "#ff79c6".into(),
        error: "#ff5555".into(), warning: "#f1fa8c".into(), success: "#50fa7b".into(),
        info: "#6272a4".into(), text: "#f8f8f2".into(), text_muted: "#6272a4".into(),
        text_emphasized: "#f1fa8c".into(), background: "#282a36".into(),
        background_panel: "#282a36".into(), background_darker: "#1e2029".into(),
    }.to_theme()
}

fn gruvbox_dark() -> Theme {
    ThemeColors {
        primary: "#fe8019".into(), secondary: "#83a598".into(), accent: "#d3869b".into(),
        error: "#fb4934".into(), warning: "#fabd2f".into(), success: "#b8bb26".into(),
        info: "#8ec07c".into(), text: "#ebdbb2".into(), text_muted: "#665c54".into(),
        text_emphasized: "#fabd2f".into(), background: "#282828".into(),
        background_panel: "#3c3836".into(), background_darker: "#1d2021".into(),
    }.to_theme()
}

fn catppuccin_latte() -> Theme {
    ThemeColors {
        primary: "#1e66f5".into(), secondary: "#7287fd".into(), accent: "#179299".into(),
        error: "#d20f39".into(), warning: "#df8e1d".into(), success: "#40a02b".into(),
        info: "#179299".into(), text: "#4c4f69".into(), text_muted: "#9ca0b0".into(),
        text_emphasized: "#df8e1d".into(), background: "#eff1f5".into(),
        background_panel: "#e6e9ef".into(), background_darker: "#dce0e8".into(),
    }.to_theme()
}

fn solarized_light() -> Theme {
    ThemeColors {
        primary: "#268bd2".into(), secondary: "#2aa198".into(), accent: "#d33682".into(),
        error: "#dc322f".into(), warning: "#b58900".into(), success: "#859900".into(),
        info: "#2aa198".into(), text: "#657b83".into(), text_muted: "#93a1a1".into(),
        text_emphasized: "#b58900".into(), background: "#fdf6e3".into(),
        background_panel: "#eee8d5".into(), background_darker: "#e8e1c9".into(),
    }.to_theme()
}

fn one_dark() -> Theme {
    ThemeColors {
        primary: "#e06c75".into(), secondary: "#61afef".into(), accent: "#c678dd".into(),
        error: "#e06c75".into(), warning: "#d19a66".into(), success: "#98c379".into(),
        info: "#56b6c2".into(), text: "#abb2bf".into(), text_muted: "#5c6370".into(),
        text_emphasized: "#d19a66".into(), background: "#282c34".into(),
        background_panel: "#2c323c".into(), background_darker: "#21252b".into(),
    }.to_theme()
}

pub fn builtin_themes() -> Vec<(&'static str, Theme)> {
    vec![
        ("nord", nord()),
        ("tokyo-night", tokyo_night()),
        ("catppuccin-mocha", catppuccin_mocha()),
        ("dracula", dracula()),
        ("gruvbox-dark", gruvbox_dark()),
        ("catppuccin-latte", catppuccin_latte()),
        ("solarized-light", solarized_light()),
        ("one-dark", one_dark()),
    ]
}

pub fn list_theme_names() -> Vec<String> {
    let mut names = vec!["default".to_string()];
    for (name, _) in builtin_themes() { names.push(name.to_string()); }
    for (name, _) in discover_custom_themes() { names.push(name); }
    names.sort(); names.dedup(); names
}

pub fn load_theme(name: &str) -> Option<Theme> {
    if name == "default" { return Some(Theme::default()); }
    if let Some((_, t)) = builtin_themes().into_iter().find(|(n, _)| *n == name) { return Some(t); }
    if let Some((_, t)) = discover_custom_themes().into_iter().find(|(n, _)| n == name) { return Some(t); }
    None
}

pub fn custom_themes_dir() -> PathBuf {
    std::env::var("HOME").ok()
        .map(|h| PathBuf::from(h).join(".sediman").join("themes"))
        .unwrap_or_else(|| PathBuf::from(".sediman/themes"))
}

pub fn discover_custom_themes() -> Vec<(String, Theme)> {
    let dir = custom_themes_dir();
    let mut out = Vec::new();
    let Ok(entries) = std::fs::read_dir(&dir) else { return out; };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("json") {
            if let Some(name) = path.file_stem().and_then(|s| s.to_str()) {
                if let Some(theme) = load_theme_from_file(path.to_str().unwrap_or("")) {
                    out.push((name.to_string(), theme));
                }
            }
        }
    }
    out
}

pub fn load_theme_from_file(path: &str) -> Option<Theme> {
    let data = std::fs::read_to_string(path).ok()?;
    load_theme_from_json(&data)
}

pub fn load_theme_from_json(data: &str) -> Option<Theme> {
    let raw: serde_json::Value = serde_json::from_str(data).ok()?;
    let defs = raw.get("defs").and_then(|d| d.as_object()).map(|obj| {
        obj.iter().filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string()))).collect::<HashMap<String, String>>()
    }).unwrap_or_default();

    let colors_raw = raw.get("colors").unwrap_or(&raw);
    let resolve = |key: &str| -> Option<Color> {
        let val = colors_raw.get(key)?;
        match val {
            serde_json::Value::String(s) => {
                if s == "none" { return None; }
                if let Some(resolved) = defs.get(s) { return parse_hex(resolved); }
                parse_hex(s)
            }
            serde_json::Value::Number(n) => Some(Color::from_rgb(n.as_u64()? as u8, n.as_u64()? as u8, n.as_u64()? as u8)),
            _ => None,
        }
    };
    let get = |key: &str, fb: &Color| -> Color { resolve(key).unwrap_or(*fb) };

    let dt = Theme::default();
    let primary = get("primary", &dt.primary);
    let secondary = get("secondary", &dt.secondary);
    let accent = get("accent", &dt.accent);
    let error = get("error", &dt.error);
    let warning = get("warning", &dt.warning);
    let success = get("success", &dt.success);
    let info = get("info", &dt.info);
    let text = get("text", &dt.text);
    let text_muted = get("text_muted", &dt.text_muted);
    let text_emph = get("text_emphasized", &dt.text_emphasized);
    let background = get("background", &dt.background);
    let bg_panel = get("background_panel", &dt.background_panel);
    let bg_darker = get("background_darker", &dt.background_darker);
    let (br, bg_, bb) = background.to_rgb();
    let border = get("border", &Color::from_rgb(br.saturating_add(40), bg_.saturating_add(40), bb.saturating_add(40)));

    Some(Theme {
        primary, secondary, accent, error, warning, success, info,
        text, text_muted, text_emphasized: text_emph,
        background, background_panel: bg_panel, background_darker: bg_darker,
        border, border_focused: get("border_focused", &primary),
        border_dim: get("border_dim", &Color::from_rgb(br.saturating_add(15), bg_.saturating_add(15), bb.saturating_add(15))),
        user_message: get("user_message", &secondary), agent_message: get("agent_message", &primary),
        md_text: get("md_text", &text), md_heading: get("md_heading", &secondary),
        md_link: get("md_link", &primary), md_link_text: get("md_link_text", &info),
        md_code: get("md_code", &success), md_blockquote: get("md_blockquote", &text_emph),
        md_emph: get("md_emph", &text_emph), md_strong: get("md_strong", &accent),
        md_horizontal_rule: get("md_horizontal_rule", &text_muted),
        md_list_item: get("md_list_item", &primary), md_list_enum: get("md_list_enum", &info),
        md_code_block: get("md_code_block", &text),
        syntax_comment: get("syntax_comment", &text_muted), syntax_keyword: get("syntax_keyword", &secondary),
        syntax_function: get("syntax_function", &primary), syntax_variable: get("syntax_variable", &error),
        syntax_string: get("syntax_string", &success), syntax_number: get("syntax_number", &accent),
        syntax_type: get("syntax_type", &text_emph), syntax_operator: get("syntax_operator", &info),
        syntax_punctuation: get("syntax_punctuation", &text),
    })
}

pub fn save_custom_theme(name: &str, colors: &ThemeColors) -> Result<(), String> {
    let dir = custom_themes_dir();
    std::fs::create_dir_all(&dir).map_err(|e| format!("{}", e))?;
    let json = serde_json::to_string_pretty(colors).map_err(|e| format!("{}", e))?;
    std::fs::write(dir.join(format!("{}.json", name)), json).map_err(|e| format!("{}", e))
}

pub fn is_custom_theme(name: &str) -> bool {
    custom_themes_dir().join(format!("{}.json", name)).exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builtin_count() { assert_eq!(builtin_themes().len(), 8); }

    #[test]
    fn test_each_loadable() {
        for (n, _) in builtin_themes() { assert!(load_theme(n).is_some()); }
    }

    #[test]
    fn test_load_default() { assert!(load_theme("default").is_some()); }

    #[test]
    fn test_load_unknown() { assert!(load_theme("nope").is_none()); }

    #[test]
    fn test_nord_not_default() {
        let n = load_theme("nord").unwrap();
        let d = Theme::default();
        assert_ne!(n.background, d.background);
    }

    #[test]
    fn test_all_builtins_have_contrast() {
        for (name, t) in builtin_themes() {
            let (br, bg, _bb) = t.background.to_rgb();
            let (tr, tg, tb) = t.text.to_rgb();
            let bl: f64 = 0.299 * br as f64 + 0.587 * bg as f64 + 0.114 * _bb as f64;
            let tl: f64 = 0.299 * tr as f64 + 0.587 * tg as f64 + 0.114 * tb as f64;
            assert!((tl - bl).abs() > 40.0, "{}: poor contrast", name);
        }
    }

    #[test]
    fn test_dark_themes_dark() {
        for n in &["nord","tokyo-night","catppuccin-mocha","dracula","gruvbox-dark","one-dark"] {
            let t = load_theme(n).unwrap();
            let (r,g,b) = t.background.to_rgb();
            let lum: f64 = 0.299 * r as f64 + 0.587 * g as f64 + 0.114 * b as f64;
            assert!(lum < 128.0, "{}", n);
        }
    }

    #[test]
    fn test_light_themes_light() {
        for n in &["catppuccin-latte","solarized-light"] {
            let t = load_theme(n).unwrap();
            let (r,g,b) = t.background.to_rgb();
            let lum: f64 = 0.299 * r as f64 + 0.587 * g as f64 + 0.114 * b as f64;
            assert!(lum > 128.0, "{}", n);
        }
    }

    #[test]
    fn test_json_loader_basic() {
        let json = r##"{"primary":"#ff0000","secondary":"#00ff00","background":"#111111","text":"#ffffff"}"##;
        let t = load_theme_from_json(json).unwrap();
        assert_eq!(t.primary, Color::from_rgb(255, 0, 0));
    }

    #[test]
    fn test_json_loader_with_defs() {
        let json = r##"{"defs":{"bg":"#2e3440"},"colors":{"primary":"#88c0d0","background":"bg"}}"##;
        let t = load_theme_from_json(json).unwrap();
        assert_eq!(t.background, Color::from_rgb(0x2e, 0x34, 0x40));
    }

    #[test]
    fn test_json_loader_invalid() { assert!(load_theme_from_json("bad").is_none()); }
    fn test_json_loader_empty() { assert!(load_theme_from_json("").is_none()); }
}
