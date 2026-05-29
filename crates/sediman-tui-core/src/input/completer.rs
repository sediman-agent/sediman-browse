pub struct Completer {
    candidates: Vec<String>,
    filtered: Vec<String>,
    selected: Option<usize>,
}

impl Completer {
    pub fn new() -> Self {
        Self {
            candidates: Vec::new(),
            filtered: Vec::new(),
            selected: None,
        }
    }

    pub fn set_candidates(&mut self, candidates: Vec<String>) {
        self.candidates = candidates;
    }

    pub fn complete(&mut self, prefix: &str) -> Option<String> {
        self.filtered = self.candidates.iter()
            .filter(|c| c.starts_with(prefix))
            .cloned()
            .collect();
        self.selected = None;
        self.filtered.first().cloned()
    }

    /// # Cycle to next candidate
    /// Use `cycle_candidate` instead to avoid confusion with `Iterator::next`.
    #[allow(clippy::should_implement_trait)]
    pub fn next(&mut self) -> Option<String> {
        let idx = self.selected.map(|i| i + 1).unwrap_or(0);
        if idx < self.filtered.len() {
            self.selected = Some(idx);
            self.filtered.get(idx).cloned()
        } else {
            self.selected = None;
            self.filtered.first().cloned()
        }
    }
}

impl Default for Completer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup() -> Completer {
        let mut c = Completer::new();
        c.set_candidates(vec![
            "/help".into(),
            "/skills".into(),
            "/schedule".into(),
            "/sessions".into(),
            "/exit".into(),
        ]);
        c
    }

    #[test]
    fn test_new_completer() {
        let c = Completer::new();
        assert!(c.candidates.is_empty());
        assert!(c.filtered.is_empty());
        assert!(c.selected.is_none());
    }

    #[test]
    fn test_complete_exact() {
        let mut c = setup();
        assert_eq!(c.complete("/help"), Some("/help".into()));
    }

    #[test]
    fn test_complete_no_match() {
        let mut c = setup();
        assert_eq!(c.complete("/xyz"), None);
    }

    #[test]
    fn test_complete_empty_prefix() {
        let mut c = setup();
        // empty prefix matches all in Vec order: /help is first
        assert_eq!(c.complete(""), Some("/help".into()));
    }

    #[test]
    fn test_complete_prefix() {
        let mut c = setup();
        // /s prefix matches /skills, /schedule, /sessions in Vec order
        assert_eq!(c.complete("/s"), Some("/skills".into()));
    }

    #[test]
    fn test_next_cycles() {
        let mut c = setup();
        c.complete("/s");
        let _first = c.next();
        let _second = c.next();
        assert_eq!(c.next(), Some("/sessions".into()));
    }

    #[test]
    fn test_next_wraps() {
        let mut c = setup();
        c.complete("/s");
        let _first = c.next();
        let _second = c.next();
        let _third = c.next();
        let fourth = c.next();
        assert_eq!(fourth, Some("/skills".into()));
    }

    #[test]
    fn test_set_candidates() {
        let mut c = Completer::new();
        let items = vec!["a".into(), "b".into()];
        c.set_candidates(items.clone());
        assert_eq!(c.candidates, items);
    }

    #[test]
    fn test_next_before_complete() {
        let mut c = setup();
        // calling next() before complete() with no filtered candidates returns None
        assert_eq!(c.next(), None);
    }

    #[test]
    fn test_next_wraps_to_first() {
        let mut c = Completer::new();
        c.set_candidates(vec!["a".into(), "b".into()]);
        c.complete("");
        assert_eq!(c.next(), Some("a".into()));
        assert_eq!(c.next(), Some("b".into()));
        assert_eq!(c.next(), Some("a".into()));
    }

    #[test]
    fn test_complete_and_next_reset() {
        let mut c = setup();
        c.complete("/s");
        assert_eq!(c.next(), Some("/skills".into()));
        // re-complete resets the cycle to start of new filtered list
        c.complete("/h");
        assert_eq!(c.next(), Some("/help".into()));
        // only one "/h" match, so next wraps back to it
        assert_eq!(c.next(), Some("/help".into()));
    }

    #[test]
    fn test_complete_case_sensitive() {
        let mut c = Completer::new();
        c.set_candidates(vec!["/Help".into(), "/help".into()]);
        assert_eq!(c.complete("/H"), Some("/Help".into()));
        assert_eq!(c.complete("/h"), Some("/help".into()));
    }

    #[test]
    fn test_complete_with_no_candidates() {
        let mut c = Completer::new();
        assert_eq!(c.complete("anything"), None);
    }

    #[test]
    fn test_next_with_no_filtered() {
        let mut c = Completer::new();
        c.complete("xyz");
        assert_eq!(c.next(), None);
    }

    #[test]
    fn test_complete_empty_candidates() {
        let mut c = Completer::new();
        c.set_candidates(vec![]);
        assert_eq!(c.complete("/"), None);
    }

    #[test]
    fn test_complete_emoji() {
        let mut c = Completer::new();
        c.set_candidates(vec!["🔥".into(), "/fire".into()]);
        assert_eq!(c.complete("🔥"), Some("🔥".into()));
    }
}
