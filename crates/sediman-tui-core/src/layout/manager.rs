use crate::renderer::Rect;

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
            input_lines: 4,
        }
    }

    pub fn split(&self, area: Rect) -> LayoutZones {
        let area = if area.width < 10 || area.height < 3 {
            Rect::new(area.x, area.y, area.width.max(10), area.height.max(3))
        } else {
            area
        };
        let title_bar = Rect::new(area.x, area.y, area.width, 1);
        let input_area = Rect::new(area.x, area.y + area.height.saturating_sub(self.input_lines), area.width, self.input_lines);
        let status_bar = Rect::new(area.x, input_area.y.saturating_sub(1), area.width, 1);
        let mut main_area = Rect::new(area.x, title_bar.y + 1, area.width, status_bar.y.saturating_sub(title_bar.y + 1));

        let side_panel = if self.show_side_panel {
            let (left, right) = main_area.split_left(main_area.width * 3 / 5);
            main_area = left;
            Some(right)
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

    fn area(w: u16, h: u16) -> Rect {
        Rect::new(0, 0, w, h)
    }

    #[test]
    fn test_new_defaults() {
        let lm = LayoutManager::new();
        assert!(lm.show_banner);
        assert!(!lm.show_progress);
        assert!(!lm.show_side_panel);
        assert_eq!(lm.input_lines, 4);
    }

    #[test]
    fn test_split_basic() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(80, 24));
        assert_eq!(zones.title_bar.height, 1);
        assert_eq!(zones.status_bar.height, 1);
        assert_eq!(zones.input.height, 4);
        assert!(zones.main.height >= 18);
        assert!(zones.side_panel.is_none());
    }

    #[test]
    fn test_split_side_panel() {
        let mut lm = LayoutManager::new();
        lm.show_side_panel = true;
        let zones = lm.split(area(100, 24));
        assert!(zones.side_panel.is_some());
        let panel = zones.side_panel.unwrap();
        assert_eq!(panel.width, 40);
        assert_eq!(zones.main.width, 60);
    }

    #[test]
    fn test_split_small_terminal() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(20, 6));
        assert_eq!(zones.title_bar.height, 1);
        assert_eq!(zones.status_bar.height, 1);
        assert_eq!(zones.input.height, 4);
    }

    #[test]
    fn test_split_tiny_terminal_does_not_panic() {
        let lm = LayoutManager::new();
        let zones = lm.split(area(10, 3));
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
        assert_eq!(zones.title_bar.width, 120);
        assert_eq!(zones.status_bar.width, 120);
        assert_eq!(zones.input.width, 120);
        assert_eq!(zones.main.width, 120);
    }

    #[test]
    fn test_split_zones_non_overlapping() {
        let mut lm = LayoutManager::new();
        let area = Rect::new(0, 0, 80, 24);
        lm.show_side_panel = false;
        let zones = lm.split(area);

        assert!(zones.title_bar.y < zones.main.y);
        assert!(zones.main.y + zones.main.height <= zones.status_bar.y);
        assert!(zones.status_bar.y + zones.status_bar.height <= zones.input.y);
    }

    #[test]
    fn test_split_zones_cover_full_width() {
        let mut lm = LayoutManager::new();
        let area = Rect::new(0, 0, 80, 24);
        lm.show_side_panel = false;
        let zones = lm.split(area);

        assert_eq!(zones.title_bar.width, 80);
        assert_eq!(zones.main.width, 80);
        assert_eq!(zones.status_bar.width, 80);
        assert_eq!(zones.input.width, 80);
    }

    #[test]
    fn test_split_with_side_panel() {
        let mut lm = LayoutManager::new();
        let area = Rect::new(0, 0, 100, 24);
        lm.show_side_panel = true;
        let zones = lm.split(area);

        let side = zones.side_panel.expect("side panel should exist");
        assert!(side.width > 0);
        assert!(side.width < 100);
        assert!(zones.main.width > 0);
        assert!(zones.main.width < 100);
    }
}
