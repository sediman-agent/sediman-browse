pub mod skills;
pub mod hub;
pub mod memory;
pub mod model;
pub mod provider;
pub mod schedule;
pub mod sessions;
pub mod browser;
pub mod record;
pub mod delegate;
pub mod system;
pub mod terminal;
pub mod plan;
pub mod soul;
pub mod misc;
pub mod theming;

use sediman_tui_core::CommandRegistry;

pub fn register_commands(registry: &mut CommandRegistry) {
    registry.register(&skills::CMD_SKILLS);
    registry.register(&skills::CMD_RUN_SKILL);
    registry.register(&hub::CMD_HUB_BROWSE);
    registry.register(&hub::CMD_HUB_SEARCH);
    registry.register(&hub::CMD_HUB_INSTALL);
    registry.register(&hub::CMD_HUB_INSTALL_GITHUB);
    registry.register(&hub::CMD_HUB_INFO);
    registry.register(&hub::CMD_HUB_PUBLISH);
    registry.register(&memory::CMD_MEMORY);
    registry.register(&memory::CMD_REMEMBER);
    registry.register(&model::CMD_MODEL);
    registry.register(&provider::CMD_PROVIDER);
    registry.register(&schedule::CMD_SCHEDULE);
    registry.register(&schedule::CMD_SCHEDULE_ADD);
    registry.register(&schedule::CMD_SCHEDULE_REMOVE);
    registry.register(&sessions::CMD_SESSIONS);
    registry.register(&sessions::CMD_RESUME);
    registry.register(&browser::CMD_BROWSER);
    registry.register(&browser::CMD_SCREENSHOT);
    registry.register(&record::CMD_RECORD);
    registry.register(&record::CMD_STOP);
    registry.register(&delegate::CMD_DELEGATE);
    registry.register(&delegate::CMD_PARALLEL);
    registry.register(&system::CMD_HELP);
    registry.register(&system::CMD_CLEAR);
    registry.register(&system::CMD_RESET);
    registry.register(&system::CMD_COMPRESS);
    registry.register(&system::CMD_EXIT);
    registry.register(&system::CMD_STATUS);
    registry.register(&terminal::CMD_TERMINAL);
    registry.register(&plan::CMD_PLAN);
    registry.register(&soul::CMD_SOUL);
    registry.register(&misc::CMD_USAGE);
    registry.register(&misc::CMD_DOCTOR);
    registry.register(&misc::CMD_EXPORT);
    registry.register(&misc::CMD_BTW);
    registry.register(&misc::CMD_COLOR);
    registry.register(&misc::CMD_RENAME);
    registry.register(&theming::CMD_THEMES);
}

#[cfg(test)]
mod tests {
    use super::*;
    use sediman_tui_core::CommandRegistry;

    #[test]
    fn test_register_commands_counts() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        let all = registry.all();
        assert_eq!(all.len(), 39);
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
        assert!(registry.get("/h").is_some());
        assert!(registry.get("/?").is_some());
        assert!(registry.get("/quit").is_some());
        assert!(registry.get("/q").is_some());
    }

    #[test]
    fn test_register_commands_agent_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/delegate").is_some());
        assert!(registry.get("/parallel").is_some());
        assert!(registry.get("/plan").is_some());
        assert!(registry.get("/model").is_some());
        // /models is now an alias of /model
    }

    #[test]
    fn test_register_commands_hub_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/hub browse").is_some());
        assert!(registry.get("/hub search").is_some());
        assert!(registry.get("/hub install").is_some());
        assert!(registry.get("/hub install-github").is_some());
        assert!(registry.get("/hub info").is_some());
        assert!(registry.get("/hub publish").is_some());
    }

    #[test]
    fn test_register_commands_utility_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/usage").is_some());
        assert!(registry.get("/export").is_some());
        assert!(registry.get("/color").is_some());
        assert!(registry.get("/rename").is_some());
        assert!(registry.get("/themes").is_some());
        assert!(registry.get("/theme").is_some());
    }

    #[test]
    fn test_register_commands_browser_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/browser").is_some());
        assert!(registry.get("/screenshot").is_some());
    }

    #[test]
    fn test_register_commands_schedule_commands() {
        let mut registry = CommandRegistry::new();
        register_commands(&mut registry);
        assert!(registry.get("/schedule").is_some());
        assert!(registry.get("/schedule-add").is_some());
        assert!(registry.get("/schedule-remove").is_some());
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
