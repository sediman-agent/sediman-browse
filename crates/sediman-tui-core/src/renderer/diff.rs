use super::{Cell, CellBuffer};

#[derive(Clone, Debug, PartialEq)]
pub struct Change {
    pub x: u16,
    pub y: u16,
    pub cell: Cell,
}

pub struct DiffEngine;

impl DiffEngine {
    pub fn diff(old: &CellBuffer, new: &CellBuffer) -> Vec<Change> {
        let width = old.width().max(new.width());
        let height = old.height().max(new.height());
        let mut changes = Vec::new();

        for y in 0..height {
            let old_dirty = old.is_row_dirty(y);
            let new_dirty = new.is_row_dirty(y);
            if !old_dirty && !new_dirty {
                continue;
            }
            for x in 0..width {
                let old_cell = old.get(x, y);
                let new_cell = new.get(x, y);
                match (old_cell, new_cell) {
                    (Some(old), Some(new)) if old != new => {
                        changes.push(Change {
                            x,
                            y,
                            cell: *new,
                        });
                    }
                    (None, Some(new)) if !new.is_empty() => {
                        changes.push(Change {
                            x,
                            y,
                            cell: *new,
                        });
                    }
                    (Some(old), None) if !old.is_empty() => {
                        changes.push(Change {
                            x,
                            y,
                            cell: Cell::default(),
                        });
                    }
                    _ => {}
                }
            }
        }
        changes
    }

    pub fn diff_and_clear(old: &mut CellBuffer, new: &mut CellBuffer) -> Vec<Change> {
        let changes = Self::diff(old, new);
        old.clear_dirty();
        new.clear_dirty();
        changes
    }

    pub fn optimize(changes: &mut [Change]) {
        changes.sort_by(|a, b| {
            a.y.cmp(&b.y).then(a.x.cmp(&b.x))
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::renderer::{CellBuffer, Color, Style};

    #[test]
    fn test_diff_identical() {
        let old = CellBuffer::new(5, 5);
        let new = CellBuffer::new(5, 5);
        let changes = DiffEngine::diff(&old, &new);
        assert!(changes.is_empty());
    }

    #[test]
    fn test_diff_one_cell() {
        let old = CellBuffer::new(5, 5);
        let mut new = CellBuffer::new(5, 5);
        new.put(2, 2, Cell::new('x', Style::new()));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].x, 2);
        assert_eq!(changes[0].y, 2);
        assert_eq!(changes[0].cell.ch, 'x');
    }

    #[test]
    fn test_diff_style_change_only() {
        let mut old = CellBuffer::new(3, 3);
        let mut new = CellBuffer::new(3, 3);
        old.put(0, 0, Cell::new('a', Style::new().fg(Color::RED)));
        new.put(0, 0, Cell::new('a', Style::new().fg(Color::GREEN)));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].cell.style.fg, Some(Color::GREEN));
    }

    #[test]
    fn test_diff_cleared_cell() {
        let mut old = CellBuffer::new(3, 3);
        let new = CellBuffer::new(3, 3);
        old.put(1, 1, Cell::new('z', Style::new()));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 1);
        assert!(changes[0].cell.is_empty());
    }

    #[test]
    fn test_diff_multiple_changes() {
        let mut old = CellBuffer::new(5, 5);
        let mut new = CellBuffer::new(5, 5);
        old.put(0, 0, Cell::new('a', Style::new()));
        old.put(1, 1, Cell::new('b', Style::new()));
        new.put(0, 0, Cell::new('A', Style::new()));
        new.put(1, 1, Cell::new('B', Style::new()));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 2);
    }

    #[test]
    fn test_diff_resize_grow() {
        let old = CellBuffer::new(2, 2);
        let mut new = CellBuffer::new(4, 4);
        new.put(3, 3, Cell::new('z', Style::new()));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].x, 3);
        assert_eq!(changes[0].y, 3);
    }

    #[test]
    fn test_diff_resize_shrink() {
        let mut old = CellBuffer::new(5, 5);
        let new = CellBuffer::new(2, 2);
        old.put(4, 4, Cell::new('x', Style::new()));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 1);
        assert!(changes[0].cell.is_empty());
    }

    #[test]
    fn test_diff_empty_vs_empty() {
        let a = CellBuffer::empty();
        let b = CellBuffer::empty();
        assert!(DiffEngine::diff(&a, &b).is_empty());
    }

    #[test]
    fn test_diff_bg_change() {
        let mut old = CellBuffer::new(3, 3);
        let mut new = CellBuffer::new(3, 3);
        old.put(0, 0, Cell::new('a', Style::new().bg(Color::RED)));
        new.put(0, 0, Cell::new('a', Style::new().bg(Color::BLUE)));
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].cell.style.bg, Some(Color::BLUE));
    }

    #[test]
    fn test_optimize_sorts_by_row_col() {
        let mut changes = vec![
            Change { x: 2, y: 1, cell: Cell::default() },
            Change { x: 0, y: 0, cell: Cell::default() },
            Change { x: 1, y: 0, cell: Cell::default() },
        ];
        DiffEngine::optimize(&mut changes);
        assert_eq!(changes[0].x, 0);
        assert_eq!(changes[0].y, 0);
        assert_eq!(changes[1].x, 1);
        assert_eq!(changes[1].y, 0);
        assert_eq!(changes[2].x, 2);
        assert_eq!(changes[2].y, 1);
    }

    #[test]
    fn test_optimize_empty() {
        let mut changes: Vec<Change> = vec![];
        DiffEngine::optimize(&mut changes);
        assert!(changes.is_empty());
    }

    #[test]
    fn test_diff_full_row_change() {
        let old = CellBuffer::new(5, 1);
        let mut new = CellBuffer::new(5, 1);
        for x in 0..5 {
            new.put_char(x, 0, 'X', Style::new().fg(Color::RED));
        }
        let changes = DiffEngine::diff(&old, &new);
        assert_eq!(changes.len(), 5);
    }

    #[test]
    fn test_diff_skips_clean_rows() {
        let mut old = CellBuffer::new(5, 5);
        let mut new = CellBuffer::new(5, 5);
        old.put(0, 0, Cell::new('a', Style::new()));
        old.put(0, 4, Cell::new('b', Style::new()));
        new.put(0, 0, Cell::new('a', Style::new()));
        new.put(0, 4, Cell::new('Z', Style::new()));
        old.clear_dirty();
        new.clear_dirty();
        assert!(!old.is_row_dirty(0));
        assert!(!new.is_row_dirty(0));
        let changes = DiffEngine::diff(&old, &new);
        assert!(changes.is_empty());
    }

    #[test]
    fn test_diff_and_clear() {
        let mut old = CellBuffer::new(5, 3);
        let mut new = CellBuffer::new(5, 3);
        new.put(2, 1, Cell::new('x', Style::new()));
        assert!(new.is_row_dirty(1));
        let changes = DiffEngine::diff_and_clear(&mut old, &mut new);
        assert_eq!(changes.len(), 1);
        assert!(!old.is_row_dirty(1));
        assert!(!new.is_row_dirty(1));
    }

    #[test]
    fn test_diff_both_empty() {
        let a = CellBuffer::empty();
        let b = CellBuffer::empty();
        assert!(DiffEngine::diff(&a, &b).is_empty());
    }

    #[test]
    fn test_diff_one_empty() {
        let mut a = CellBuffer::new(3, 3);
        a.put(1, 1, Cell::new('x', Style::new()));
        let b = CellBuffer::new(3, 3);
        let changes = DiffEngine::diff(&a, &b);
        assert_eq!(changes.len(), 1);
        assert!(changes[0].cell.is_empty());
    }

    #[test]
    fn test_diff_skip_flag_change() {
        let mut a = CellBuffer::new(2, 1);
        let mut b = CellBuffer::new(2, 1);
        a.put(0, 0, Cell::new('a', Style::new()));
        let mut c = Cell::new('a', Style::new());
        c.skip = true;
        b.put(0, 0, c);
        let changes = DiffEngine::diff(&a, &b);
        assert_eq!(changes.len(), 1);
        assert!(changes[0].cell.skip);
    }

    #[test]
    fn test_optimize_single_element() {
        let mut changes = vec![Change { x: 5, y: 5, cell: Cell::default() }];
        DiffEngine::optimize(&mut changes);
        assert_eq!(changes.len(), 1);
    }

    #[test]
    fn test_optimize_reverse_sorted() {
        let mut changes = vec![
            Change { x: 2, y: 1, cell: Cell::default() },
            Change { x: 1, y: 1, cell: Cell::default() },
            Change { x: 0, y: 0, cell: Cell::default() },
        ];
        DiffEngine::optimize(&mut changes);
        assert_eq!(changes[0].y, 0);
        assert_eq!(changes[1].x, 1);
        assert_eq!(changes[2].x, 2);
    }
}
