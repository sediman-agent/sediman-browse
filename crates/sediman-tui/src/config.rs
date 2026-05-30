//! Persistent configuration for the Sediman TUI.
//!
//! Saves/loads user preferences to `~/.sediman/tui.toml`.
//! Theme, permission mode, side panel state, and session history survive restarts.

use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TuiConfig {
    /// Active theme name (nord, tokyo-night, catppuccin, dracula)
    #[serde(default = "default_theme")]
    pub theme: String,

    /// Permission mode: ask, acceptEdits, plan, auto
    #[serde(default = "default_permission")]
    pub permission_mode: String,

    /// Whether the side panel is visible
    #[serde(default)]
    pub side_panel_open: bool,

    /// Last active side panel tab: Skills, Memory, Schedule, Status
    #[serde(default = "default_side_tab")]
    pub side_panel_tab: String,

    /// Browser mode: headless or headed
    #[serde(default = "default_headless")]
    pub headless: bool,

    /// User's saved model identifiers (e.g. "openai:gpt-4o", "ollama:qwen3")
    #[serde(default)]
    pub saved_models: Vec<String>,
}

fn default_theme() -> String { "default".into() }
fn default_permission() -> String { "ask".into() }
fn default_side_tab() -> String { "Status".into() }
fn default_headless() -> bool { true }

impl Default for TuiConfig {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            permission_mode: default_permission(),
            side_panel_open: false,
            side_panel_tab: default_side_tab(),
            headless: default_headless(),
            saved_models: Vec::new(),
        }
    }
}

impl TuiConfig {
    /// Returns the config file path: `~/.sediman/tui.toml`
    pub fn config_path() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".sediman")
            .join("tui.toml")
    }

    /// Load config from disk. Returns default if file doesn't exist or is invalid.
    pub fn load() -> Self {
        let path = Self::config_path();
        match fs::read_to_string(&path) {
            Ok(content) => {
                toml::from_str(&content).unwrap_or_else(|e| {
                    eprintln!("Warning: failed to parse {}: {} — using defaults", path.display(), e);
                    Self::default()
                })
            }
            Err(_) => Self::default(),
        }
    }

    /// Save config to disk. Creates the directory if needed.
    pub fn save(&self) -> Result<(), String> {
        let path = Self::config_path();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("Failed to create config dir: {}", e))?;
        }
        let content = toml::to_string_pretty(self)
            .map_err(|e| format!("Failed to serialize config: {}", e))?;
        fs::write(&path, content).map_err(|e| format!("Failed to write config: {}", e))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = TuiConfig::default();
        assert_eq!(config.theme, "default");
        assert_eq!(config.permission_mode, "ask");
        assert!(!config.side_panel_open);
        assert_eq!(config.side_panel_tab, "Status");
        assert!(config.headless);
    }

    #[test]
    fn test_config_serialize_roundtrip() {
        let config = TuiConfig {
            theme: "catppuccin".into(),
            permission_mode: "auto".into(),
            side_panel_open: true,
            side_panel_tab: "Skills".into(),
            headless: false,
            saved_models: vec!["openai:gpt-4o".into(), "ollama:qwen3".into()],
        };
        let toml_str = toml::to_string_pretty(&config).unwrap();
        let parsed: TuiConfig = toml::from_str(&toml_str).unwrap();
        assert_eq!(parsed.theme, "catppuccin");
        assert_eq!(parsed.permission_mode, "auto");
        assert!(parsed.side_panel_open);
        assert_eq!(parsed.side_panel_tab, "Skills");
        assert!(!parsed.headless);
    }

    #[test]
    fn test_config_path_is_under_home() {
        let path = TuiConfig::config_path();
        assert!(path.to_str().unwrap().contains(".sediman"));
        assert!(path.to_str().unwrap().contains("tui.toml"));
    }
}
