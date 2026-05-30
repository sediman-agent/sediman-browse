mod theme;
pub mod themes;

pub use theme::{Theme, ThemeColors, parse_hex};
pub use themes::{
    load_theme, list_theme_names, builtin_themes, load_theme_from_file,
    load_theme_from_json, discover_custom_themes, save_custom_theme,
    is_custom_theme, custom_themes_dir,
};
