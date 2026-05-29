use std::collections::HashMap;

use super::fuzzy::fuzzy_match;

#[derive(Clone, Copy, PartialEq)]
pub enum CommandCategory {
    General,
    Agent,
    Skills,
    Hub,
    Browser,
    Sessions,
    Schedule,
    Terminal,
    Tasks,
    Utilities,
}

pub struct Command {
    pub name: &'static str,
    pub aliases: &'static [&'static str],
    pub description: &'static str,
    pub category: CommandCategory,
}

pub struct CommandRegistry {
    commands: HashMap<&'static str, &'static Command>,
    commands_list: Vec<&'static Command>,
}

impl CommandRegistry {
    pub fn new() -> Self {
        Self {
            commands: HashMap::new(),
            commands_list: Vec::new(),
        }
    }

    pub fn register(&mut self, cmd: &'static Command) {
        self.commands.insert(cmd.name, cmd);
        for alias in cmd.aliases {
            self.commands.insert(alias, cmd);
        }
        self.commands_list.push(cmd);
    }

    pub fn get(&self, name: &str) -> Option<&'static Command> {
        self.commands.get(name).copied()
    }

    pub fn find_fuzzy(&self, input: &str) -> Option<&'static Command> {
        fuzzy_match(input, &self.commands_list).map(|i| self.commands_list[i])
    }

    pub fn completions(&self, prefix: &str) -> Vec<&'static str> {
        self.commands_list
            .iter()
            .filter(|c| c.name.starts_with(prefix))
            .map(|c| c.name)
            .collect()
    }

    pub fn all(&self) -> &[&'static Command] {
        &self.commands_list
    }
}

impl Default for CommandRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    static CMD_HELP: Command = Command {
        name: "/help",
        aliases: &["/h", "/?"],
        description: "Show help",
        category: CommandCategory::General,
    };

    static CMD_SKILLS: Command = Command {
        name: "/skills",
        aliases: &["/skill list"],
        description: "List skills",
        category: CommandCategory::Skills,
    };

    static CMD_EXIT: Command = Command {
        name: "/exit",
        aliases: &["/quit"],
        description: "Exit",
        category: CommandCategory::General,
    };

    fn setup() -> CommandRegistry {
        let mut reg = CommandRegistry::new();
        reg.register(&CMD_HELP);
        reg.register(&CMD_SKILLS);
        reg.register(&CMD_EXIT);
        reg
    }

    #[test]
    fn test_register_and_get() {
        let reg = setup();
        assert!(reg.get("/help").is_some());
        assert!(reg.get("/skills").is_some());
        assert!(reg.get("/exit").is_some());
    }

    #[test]
    fn test_get_alias() {
        let reg = setup();
        assert_eq!(reg.get("/h").unwrap().name, "/help");
        assert_eq!(reg.get("/?").unwrap().name, "/help");
        assert_eq!(reg.get("/quit").unwrap().name, "/exit");
        assert_eq!(reg.get("/skill list").unwrap().name, "/skills");
    }

    #[test]
    fn test_get_unknown() {
        let reg = setup();
        assert!(reg.get("/unknown").is_none());
    }

    #[test]
    fn test_find_fuzzy() {
        let reg = setup();
        assert_eq!(reg.find_fuzzy("/helkp").unwrap().name, "/help");
    }

    #[test]
    fn test_completions() {
        let reg = setup();
        let comp = reg.completions("/");
        assert!(comp.contains(&"/help"));
        assert!(comp.contains(&"/skills"));
        assert!(comp.contains(&"/exit"));
    }

    #[test]
    fn test_completions_prefix() {
        let reg = setup();
        let comp = reg.completions("/he");
        assert_eq!(comp, vec!["/help"]);
    }

    #[test]
    fn test_completions_no_match() {
        let reg = setup();
        let comp = reg.completions("/xyz");
        assert!(comp.is_empty());
    }

    #[test]
    fn test_all_returns_all() {
        let reg = setup();
        assert_eq!(reg.all().len(), 3);
    }
}
