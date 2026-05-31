pub mod skills;
pub mod hub;
pub mod memory;
pub mod model;
pub mod provider;
pub mod connect;
pub mod schedule;
pub mod sessions;
pub mod browser;
pub mod delegate;
pub mod system;
pub mod plan;
pub mod soul;
pub mod theming;
pub mod coder;

use sediman_tui_core::CommandRegistry;

pub fn register_commands(registry: &mut CommandRegistry) {
    // Core
    registry.register(&system::CMD_HELP);
    registry.register(&system::CMD_EXIT);
    registry.register(&system::CMD_CLEAR);
    registry.register(&system::CMD_RESET);
    registry.register(&system::CMD_COMPRESS);
    registry.register(&system::CMD_STATUS);
    // Agent
    registry.register(&model::CMD_MODEL);
    registry.register(&provider::CMD_PROVIDER);
    registry.register(&connect::CMD_CONNECT);
    registry.register(&plan::CMD_PLAN);
    registry.register(&soul::CMD_SOUL);
    registry.register(&theming::CMD_THEMES);
    registry.register(&coder::CMD_CODER);
    // Skills & Hub
    registry.register(&skills::CMD_SKILLS);
    registry.register(&hub::CMD_HUB);
    // Memory
    registry.register(&memory::CMD_MEMORY);
    registry.register(&memory::CMD_REMEMBER);
    // Schedule
    registry.register(&schedule::CMD_SCHEDULE);
    // Sessions
    registry.register(&sessions::CMD_SESSIONS);
    // Browser
    registry.register(&browser::CMD_BROWSER);
    registry.register(&browser::CMD_SCREENSHOT);
    // Tasks
    registry.register(&delegate::CMD_DELEGATE);
    registry.register(&delegate::CMD_PARALLEL);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_register_commands_counts() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        let all = registry.all();
        assert_eq!(all.len(), 23);
    }

    #[test]
    fn test_register_commands_has_core_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/help").is_some());
        assert!(registry.get("/exit").is_some());
        assert!(registry.get("/clear").is_some());
        assert!(registry.get("/reset").is_some());
        assert!(registry.get("/status").is_some());
        assert!(registry.get("/compress").is_some());
    }

    #[test]
    fn test_register_commands_aliases() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/quit").is_some());
        assert!(registry.get("/q").is_some());
    }

    #[test]
    fn test_register_commands_no_removed_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        // These should NOT be registered anymore
        assert!(registry.get("/btw").is_none());
        assert!(registry.get("/color").is_none());
        assert!(registry.get("/rename").is_none());
        assert!(registry.get("/export").is_none());
        assert!(registry.get("/usage").is_none());
        assert!(registry.get("/doctor").is_none());
        assert!(registry.get("/record").is_none());
        assert!(registry.get("/stop").is_none());
        assert!(registry.get("/terminal").is_none());
        assert!(registry.get("/run-skill").is_none());
        assert!(registry.get("/schedule-add").is_none());
        assert!(registry.get("/schedule-remove").is_none());
        assert!(registry.get("/resume").is_none());
        assert!(registry.get("/hub browse").is_none());
        assert!(registry.get("/hub search").is_none());
        assert!(registry.get("/hub install").is_none());
        assert!(registry.get("/hub update").is_none());
        assert!(registry.get("/hub remove").is_none());
        assert!(registry.get("/hub publish").is_none());
    }

    #[test]
    fn test_register_commands_no_duplicates() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        let all = registry.all();
        let names: Vec<&str> = all.iter().map(|c| c.name).collect();
        let mut unique = names.clone();
        unique.sort();
        unique.dedup();
        assert_eq!(names.len(), unique.len(), "Duplicate command names found");
    }
}
