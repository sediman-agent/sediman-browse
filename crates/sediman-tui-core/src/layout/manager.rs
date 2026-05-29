use ratatui::layout::{Constraint, Layout, Rect};

pub enum Zone {
    TitleBar,
    Main,
    SidePanel,
    StatusBar,
    Input,
}

pub struct LayoutManager {
    pub show_banner: bool,
    pub show_progress: bool,
    pub show_side_panel: bool,
    pub input_lines: u16,
}

impl LayoutManager {
    pub fn new() -> Self {
        Self {
            show_banner: true,
            show_progress: false,
            show_side_panel: false,
            input_lines: 3,
        }
    }

    pub fn split(&self, area: Rect) -> LayoutZones {
        let _main_height = area.height.saturating_sub(2 + self.input_lines);
        let chunks = Layout::vertical([
            Constraint::Length(1),
            Constraint::Min(0),
            Constraint::Length(1),
            Constraint::Length(self.input_lines),
        ])
        .areas::<4>(area);

        let title_bar = chunks[0];
        let status_bar = chunks[2];
        let input_area = chunks[3];
        let mut main_area = chunks[1];

        let side_panel = if self.show_side_panel {
            let cols = Layout::horizontal([
                Constraint::Percentage(60),
                Constraint::Percentage(40),
            ])
            .areas::<2>(main_area);
            main_area = cols[0];
            Some(cols[1])
        } else {
            None
        };

        LayoutZones {
            title_bar,
            main: main_area,
            side_panel,
            status_bar,
            input: input_area,
        }
    }
}

impl Default for LayoutManager {
    fn default() -> Self {
        Self::new()
    }
}

pub struct LayoutZones {
    pub title_bar: Rect,
    pub main: Rect,
    pub side_panel: Option<Rect>,
    pub status_bar: Rect,
    pub input: Rect,
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::layout::Rect;

    fn area(w: u16, h: u16) -> Rect {
        Rect::new(0, 0, w, h)
    }

    #[test]
    fn test_new_defaults() {
        let lm = LayoutManager::new();
        assert!(lm.show_banner);
        assert!(!lm.show_progress);
        assert!(!lm.show_side_panel);
        assert_eq!(lm.input_lines, 3);
    }

    #[test]
    fn test_split_basic() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(80, 24));
        // 1 title + 20 main + 1 status + 2 input (24 total)
        assert_eq!(zones.title_bar.height, 1);
        assert_eq!(zones.status_bar.height, 1);
        assert_eq!(zones.input.height, 3);
        assert!(zones.main.height >= 19);
        assert!(zones.side_panel.is_none());
    }

    #[test]
    fn test_split_side_panel() {
        let mut lm = LayoutManager::new();
        lm.show_side_panel = true;
        let zones = lm.split(area(100, 24));
        assert!(zones.side_panel.is_some());
        let panel = zones.side_panel.unwrap();
        // main takes 60%, panel takes 40% of available width
        assert_eq!(panel.width, 40);
        assert_eq!(zones.main.width, 60);
    }

    #[test]
    fn test_split_small_terminal() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(20, 6));
        // minimum viable layout: 1 + 1 + 1 + 3 = 6
        assert_eq!(zones.title_bar.height, 1);
        assert_eq!(zones.status_bar.height, 1);
        assert_eq!(zones.input.height, 3);
        assert_eq!(zones.main.height, 1);
    }

    #[test]
    fn test_split_tiny_terminal_does_not_panic() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(10, 3));
        // In a 3-row terminal, zones may be 0 height; just ensure no panic
        assert_eq!(zones.title_bar.width, 10);
        _ = zones.main.height;
        _ = zones.status_bar.height;
        _ = zones.input.height;
    }

    #[test]
    fn test_input_lines_custom() {
        let mut lm = LayoutManager::new();
        lm.input_lines = 5;
        let zones = lm.split(area(80, 30));
        assert_eq!(zones.input.height, 5);
    }

    #[test]
    fn test_split_full_width() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(120, 40));
        // All zones span full width
        assert_eq!(zones.title_bar.width, 120);
        assert_eq!(zones.status_bar.width, 120);
        assert_eq!(zones.input.width, 120);
        assert_eq!(zones.main.width, 120);
    }

    #[test]
    fn test_show_progress_flag() {
        let mut lm = LayoutManager::new();
        assert!(!lm.show_progress);
        lm.show_progress = true;
        assert!(lm.show_progress);
    }

    #[test]
    fn test_split_side_panel_off() {
        let lm = LayoutManager::new();
        assert!(!lm.show_side_panel);
        let zones = lm.split(area(80, 24));
        assert!(zones.side_panel.is_none());
    }
}
