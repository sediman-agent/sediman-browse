use std::collections::HashMap;

use fontdue::Font;

#[derive(Clone, Copy, Debug)]
pub struct GlyphInfo {
    pub u0: f32,
    pub v0: f32,
    pub u1: f32,
    pub v1: f32,
    pub advance: f32,
}

pub struct FontAtlas {
    pub pixels: Vec<u8>,
    pub width: u32,
    pub height: u32,
    pub glyphs: HashMap<char, GlyphInfo>,
    pub line_height: f32,
    pub baseline: f32,
    cursor_x: u32,
    cursor_y: u32,
    glyph_w: u32,
    glyph_h: u32,
    dirty_rect: Option<(u32, u32, u32, u32)>,
}

impl FontAtlas {
    pub fn new(font_data: &[u8], font_size: f32) -> Self {
        let settings = fontdue::FontSettings {
            scale: font_size,
            ..Default::default()
        };
        let font = Font::from_bytes(font_data, settings)
            .expect("Failed to load font");

        let atlas_width: u32 = 4096;
        let atlas_height: u32 = 4096;

        let (metrics, _) = font.rasterize('M', font_size);
        let line_height = metrics.height as f32;
        let baseline = line_height * 0.8;

        let glyph_w = font_size.ceil() as u32 + 2;
        let glyph_h = line_height.ceil() as u32 + 2;

        let chars: Vec<char> = {
            let mut v: Vec<char> = (32u8..=126u8).map(|c| c as char).collect();
            for c in 0x2500u16..=0x257Fu16 {
                if let Some(ch) = char::from_u32(c as u32) {
                    v.push(ch);
                }
            }
            for c in 0x2580u16..=0x259Fu16 {
                if let Some(ch) = char::from_u32(c as u32) {
                    v.push(ch);
                }
            }
            for &ch in &[
                '•', '✓', '✗', '◆', '◇', '◎', '▶', '▸', '◈', '⋄',
                '★', '✦', '✧', '→', '←', '↑', '↓', '☐', '☑', '○',
                '●', '◉', '⚡', '⚠', '✂', '✎', '⚙', '∞', '━', '│',
                '─', '┄', '┅', '┆', '┇', '┈', '┉', '┊', '┋', '┬',
                '├', '┴', '┤', '┼', '┐', '└', '┘', '░', '▒', '▓',
                '█', '▔', '▕', '▁', '▏',
            ] {
                v.push(ch);
            }
            v.sort();
            v.dedup();
            v
        };

        let mut pixels = vec![0u8; (atlas_width * atlas_height * 4) as usize];
        let mut glyphs = HashMap::new();

        let mut cx: u32 = 0;
        let mut cy: u32 = 0;

        for &ch in &chars {
            let (m, bitmap) = font.rasterize(ch, font_size);
            if bitmap.is_empty() {
                continue;
            }
            let w = m.width.min(glyph_w as usize) as u32;
            let h = m.height.min(glyph_h as usize) as u32;

            for row in 0..h {
                for col in 0..w {
                    let src_idx = row as usize * m.width + col as usize;
                    let alpha = if src_idx < bitmap.len() { bitmap[src_idx] } else { 0 };
                    let dst_idx = ((cy + row) as usize * atlas_width as usize + (cx + col) as usize) * 4;
                    pixels[dst_idx] = 255;
                    pixels[dst_idx + 1] = 255;
                    pixels[dst_idx + 2] = 255;
                    pixels[dst_idx + 3] = alpha;
                }
            }

            glyphs.insert(ch, GlyphInfo {
                u0: cx as f32 / atlas_width as f32,
                v0: cy as f32 / atlas_height as f32,
                u1: (cx + w) as f32 / atlas_width as f32,
                v1: (cy + h) as f32 / atlas_height as f32,
                advance: m.advance_width,
            });

            cx += glyph_w;
            if cx + glyph_w >= atlas_width {
                cx = 0;
                cy += glyph_h;
            }
        }

        Self {
            pixels,
            width: atlas_width,
            height: atlas_height,
            glyphs,
            line_height,
            baseline,
            cursor_x: cx,
            cursor_y: cy,
            glyph_w,
            glyph_h,
            dirty_rect: None,
        }
    }

    pub fn get_or_default(&self, ch: char) -> &GlyphInfo {
        self.glyphs.get(&ch)
            .or_else(|| self.glyphs.get(&'?'))
            .or_else(|| self.glyphs.get(&' '))
            .expect("Font atlas must have at least space and ? glyphs")
    }

    pub fn rasterize_glyph(&mut self, font: &Font, font_size: f32, ch: char) -> Option<GlyphInfo> {
        if self.glyphs.contains_key(&ch) {
            return self.glyphs.get(&ch).copied();
        }

        let (m, bitmap) = font.rasterize(ch, font_size);
        if bitmap.is_empty() {
            return None;
        }

        let w = m.width.min(self.glyph_w as usize) as u32;
        let h = m.height.min(self.glyph_h as usize) as u32;

        if self.cursor_x + self.glyph_w >= self.width {
            self.cursor_x = 0;
            self.cursor_y += self.glyph_h;
        }

        if self.cursor_y + self.glyph_h >= self.height {
            return None;
        }

        let cx = self.cursor_x;
        let cy = self.cursor_y;

        for row in 0..h {
            for col in 0..w {
                let src_idx = row as usize * m.width + col as usize;
                let alpha = if src_idx < bitmap.len() { bitmap[src_idx] } else { 0 };
                let dst_idx = ((cy + row) as usize * self.width as usize + (cx + col) as usize) * 4;
                self.pixels[dst_idx] = 255;
                self.pixels[dst_idx + 1] = 255;
                self.pixels[dst_idx + 2] = 255;
                self.pixels[dst_idx + 3] = alpha;
            }
        }

        let info = GlyphInfo {
            u0: cx as f32 / self.width as f32,
            v0: cy as f32 / self.height as f32,
            u1: (cx + w) as f32 / self.width as f32,
            v1: (cy + h) as f32 / self.height as f32,
            advance: m.advance_width,
        };

        self.glyphs.insert(ch, info);
        self.cursor_x += self.glyph_w;
        self.dirty_rect = Some(match self.dirty_rect {
            Some((x0, y0, x1, y1)) => (
                x0.min(cx), y0.min(cy), x1.max(cx + w), y1.max(cy + h),
            ),
            None => (cx, cy, cx + w, cy + h),
        });

        Some(info)
    }

    pub fn take_dirty_rect(&mut self) -> Option<(u32, u32, u32, u32)> {
        self.dirty_rect.take()
    }
}
