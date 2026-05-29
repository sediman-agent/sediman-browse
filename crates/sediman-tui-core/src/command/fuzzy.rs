fn levenshtein(a: &str, b: &str) -> usize {
    let a_len = a.chars().count();
    let b_len = b.chars().count();
    let mut matrix = vec![vec![0; b_len + 1]; a_len + 1];

    for (i, row) in matrix.iter_mut().enumerate() {
        row[0] = i;
    }
    for (j, val) in matrix[0].iter_mut().enumerate() {
        *val = j;
    }

    for (i, ca) in a.chars().enumerate() {
        for (j, cb) in b.chars().enumerate() {
            let cost = if ca == cb { 0 } else { 1 };
            matrix[i + 1][j + 1] = (matrix[i][j + 1] + 1)
                .min(matrix[i + 1][j] + 1)
                .min(matrix[i][j] + cost);
        }
    }

    matrix[a_len][b_len]
}

use super::registry::Command;

pub fn fuzzy_match(input: &str, commands: &[&Command]) -> Option<usize> {
    let input_lower = input.to_lowercase();

    let exact = commands.iter().position(|c| {
        c.name.to_lowercase() == input_lower
            || c.aliases.iter().any(|a| a.to_lowercase() == input_lower)
    });
    if let Some(idx) = exact {
        return Some(idx);
    }

    let starts_with = commands.iter().position(|c| {
        c.name.to_lowercase().starts_with(&input_lower)
            || c.aliases.iter().any(|a| a.to_lowercase().starts_with(&input_lower))
    });
    if let Some(idx) = starts_with {
        return Some(idx);
    }

    let contains = commands.iter().position(|c| {
        c.name.to_lowercase().contains(&input_lower)
    });
    if let Some(idx) = contains {
        return Some(idx);
    }

    let best = commands
        .iter()
        .enumerate()
        .map(|(i, c)| (levenshtein(&input_lower, &c.name.to_lowercase()), i))
        .filter(|(dist, _)| *dist <= 3)
        .min_by_key(|(dist, _)| *dist);

    best.map(|(_, i)| i)
}

#[cfg(test)]
mod tests {
    use super::*;

    static CMD_SKILLS: Command = Command {
        name: "/skills",
        aliases: &["/skill list"],
        description: "",
        category: super::super::registry::CommandCategory::General,
        handler: |_, _| Box::new(std::future::ready(())),
    };

    static CMD_HELP: Command = Command {
        name: "/help",
        aliases: &["/h", "/?"],
        description: "",
        category: super::super::registry::CommandCategory::General,
        handler: |_, _| Box::new(std::future::ready(())),
    };

    static CMD_EXIT: Command = Command {
        name: "/exit",
        aliases: &["/quit"],
        description: "",
        category: super::super::registry::CommandCategory::General,
        handler: |_, _| Box::new(std::future::ready(())),
    };

    static CMD_SCHEDULE: Command = Command {
        name: "/schedule",
        aliases: &[],
        description: "",
        category: super::super::registry::CommandCategory::General,
        handler: |_, _| Box::new(std::future::ready(())),
    };

    static CMD_SESSIONS: Command = Command {
        name: "/sessions",
        aliases: &[],
        description: "",
        category: super::super::registry::CommandCategory::General,
        handler: |_, _| Box::new(std::future::ready(())),
    };

    static CMD_RUN_SKILL: Command = Command {
        name: "/run-skill",
        aliases: &[],
        description: "",
        category: super::super::registry::CommandCategory::General,
        handler: |_, _| Box::new(std::future::ready(())),
    };

    #[test]
    fn test_levenshtein_identical() {
        assert_eq!(levenshtein("hello", "hello"), 0);
    }

    #[test]
    fn test_levenshtein_empty() {
        assert_eq!(levenshtein("", "abc"), 3);
        assert_eq!(levenshtein("abc", ""), 3);
        assert_eq!(levenshtein("", ""), 0);
    }

    #[test]
    fn test_levenshtein_substitution() {
        assert_eq!(levenshtein("cat", "car"), 1);
    }

    #[test]
    fn test_levenshtein_insertion() {
        assert_eq!(levenshtein("cat", "cats"), 1);
    }

    #[test]
    fn test_levenshtein_deletion() {
        assert_eq!(levenshtein("cats", "cat"), 1);
    }

    #[test]
    fn test_levenshtein_complex() {
        assert_eq!(levenshtein("kitten", "sitting"), 3);
    }

    #[test]
    fn test_fuzzy_match_exact() {
        let cmds: [&Command; 3] = [&CMD_SKILLS, &CMD_HELP, &CMD_EXIT];
        assert_eq!(fuzzy_match("/skills", &cmds), Some(0));
        assert_eq!(fuzzy_match("/help", &cmds), Some(1));
        assert_eq!(fuzzy_match("/exit", &cmds), Some(2));
    }

    #[test]
    fn test_fuzzy_match_alias() {
        let cmds: [&Command; 2] = [&CMD_SKILLS, &CMD_HELP];
        assert_eq!(fuzzy_match("/skill list", &cmds), Some(0));
        assert_eq!(fuzzy_match("/h", &cmds), Some(1));
        assert_eq!(fuzzy_match("/?", &cmds), Some(1));
    }

    #[test]
    fn test_fuzzy_match_starts_with() {
        let cmds: [&Command; 3] = [&CMD_SKILLS, &CMD_SCHEDULE, &CMD_SESSIONS];
        assert_eq!(fuzzy_match("/sk", &cmds), Some(0));
        assert_eq!(fuzzy_match("/sch", &cmds), Some(1));
        assert_eq!(fuzzy_match("/ses", &cmds), Some(2));
    }

    #[test]
    fn test_fuzzy_match_contains() {
        let cmds: [&Command; 3] = [&CMD_RUN_SKILL, &CMD_SKILLS, &CMD_SCHEDULE];
        // "/run-skill" contains "skill" → matched first at index 0
        assert_eq!(fuzzy_match("skill", &cmds), Some(0));
    }

    #[test]
    fn test_fuzzy_match_case_insensitive() {
        let cmds: [&Command; 1] = [&CMD_HELP];
        assert_eq!(fuzzy_match("/help", &cmds), Some(0));
        assert_eq!(fuzzy_match("/HELP", &cmds), Some(0));
    }

    #[test]
    fn test_fuzzy_match_levenshtein_fallback() {
        let cmds: [&Command; 2] = [&CMD_SKILLS, &CMD_HELP];
        assert_eq!(fuzzy_match("/helkp", &cmds), Some(1));
    }

    #[test]
    fn test_fuzzy_match_no_match() {
        let cmds: [&Command; 1] = [&CMD_HELP];
        assert_eq!(fuzzy_match("/xyz", &cmds), None);
    }

    #[test]
    fn test_fuzzy_match_empty_input() {
        let cmds: [&Command; 1] = [&CMD_HELP];
        // empty string starts every command name → match at 0
        assert_eq!(fuzzy_match("", &cmds), Some(0));
    }

    #[test]
    fn test_fuzzy_match_empty_commands() {
        let cmds: [&Command; 0] = [];
        assert_eq!(fuzzy_match("/help", &cmds), None);
    }
}
