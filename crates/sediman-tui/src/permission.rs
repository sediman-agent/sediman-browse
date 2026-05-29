const PERMISSION_MODES: &[&str] = &["ask", "acceptEdits", "plan", "auto"];

pub struct PermissionManager {
    mode_idx: usize,
    saved_idx: usize,
    plan_mode: bool,
}

impl PermissionManager {
    pub fn new() -> Self {
        Self {
            mode_idx: 0,
            saved_idx: 0,
            plan_mode: false,
        }
    }

    pub fn current_label(&self) -> &'static str {
        if self.plan_mode {
            "plan"
        } else {
            PERMISSION_MODES[self.mode_idx]
        }
    }

    pub fn cycle(&mut self) {
        if self.plan_mode {
            self.plan_mode = false;
            self.mode_idx = (self.saved_idx + 1) % PERMISSION_MODES.len();
        } else {
            self.mode_idx = (self.mode_idx + 1) % PERMISSION_MODES.len();
        }
    }

    pub fn is_allowed(&self, _command: &str) -> bool {
        !matches!(self.current_label(), "plan" | "ask")
    }

    pub fn set_plan_mode(&mut self, enabled: bool) {
        if enabled {
            self.saved_idx = self.mode_idx;
            self.plan_mode = true;
        } else {
            self.plan_mode = false;
        }
    }

    pub fn is_plan_mode(&self) -> bool {
        self.plan_mode || self.current_label() == "plan"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_is_ask() {
        let pm = PermissionManager::new();
        assert_eq!(pm.current_label(), "ask");
    }

    #[test]
    fn test_cycle_through_all_modes() {
        let mut pm = PermissionManager::new();
        assert_eq!(pm.current_label(), "ask");
        pm.cycle();
        assert_eq!(pm.current_label(), "acceptEdits");
        pm.cycle();
        assert_eq!(pm.current_label(), "plan");
        pm.cycle();
        assert_eq!(pm.current_label(), "auto");
        pm.cycle();
        assert_eq!(pm.current_label(), "ask");
    }

    #[test]
    fn test_cycle_clears_plan_mode() {
        let mut pm = PermissionManager::new();
        pm.set_plan_mode(true);
        assert!(pm.is_plan_mode());
        pm.cycle();
        assert!(!pm.is_plan_mode());
        assert_eq!(pm.current_label(), "acceptEdits");
    }

    #[test]
    fn test_set_plan_mode_on() {
        let mut pm = PermissionManager::new();
        pm.set_plan_mode(true);
        assert!(pm.is_plan_mode());
        assert_eq!(pm.current_label(), "plan");
    }

    #[test]
    fn test_set_plan_mode_off_restores_original_mode() {
        let mut pm = PermissionManager::new();
        assert_eq!(pm.current_label(), "ask");
        pm.set_plan_mode(true);
        assert_eq!(pm.current_label(), "plan");
        pm.set_plan_mode(false);
        assert!(!pm.is_plan_mode());
        // should restore to "ask" (the saved mode before plan was enabled)
        assert_eq!(pm.current_label(), "ask");
    }

    #[test]
    fn test_is_allowed_ask() {
        let pm = PermissionManager::new();
        assert_eq!(pm.current_label(), "ask");
        assert!(!pm.is_allowed("any command"));
    }

    #[test]
    fn test_is_allowed_accept_edits() {
        let mut pm = PermissionManager::new();
        pm.cycle(); // acceptEdits
        assert!(pm.is_allowed("any command"));
    }

    #[test]
    fn test_is_allowed_plan() {
        let mut pm = PermissionManager::new();
        pm.cycle();
        pm.cycle(); // plan
        assert!(!pm.is_allowed("any command"));
    }

    #[test]
    fn test_is_allowed_auto() {
        let mut pm = PermissionManager::new();
        pm.cycle();
        pm.cycle();
        pm.cycle(); // auto
        assert!(pm.is_allowed("any command"));
    }

    #[test]
    fn test_is_allowed_plan_mode() {
        let mut pm = PermissionManager::new();
        pm.set_plan_mode(true);
        assert!(!pm.is_allowed("any command"));
    }

    #[test]
    fn test_is_plan_mode_when_label_is_plan() {
        let mut pm = PermissionManager::new();
        pm.cycle();
        pm.cycle(); // "plan" mode
        assert!(pm.is_plan_mode());
    }

    #[test]
    fn test_plan_mode_false_in_ask() {
        let pm = PermissionManager::new();
        assert!(!pm.is_plan_mode());
    }
}
