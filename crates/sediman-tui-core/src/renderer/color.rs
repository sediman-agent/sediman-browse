#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rgba {
    pub r: f32,
    pub g: f32,
    pub b: f32,
    pub a: f32,
}

impl Rgba {
    pub const fn new(r: f32, g: f32, b: f32, a: f32) -> Self {
        Self { r, g, b, a }
    }

    pub fn from_u8(r: u8, g: u8, b: u8, a: u8) -> Self {
        Self {
            r: r as f32 / 255.0,
            g: g as f32 / 255.0,
            b: b as f32 / 255.0,
            a: a as f32 / 255.0,
        }
    }

    pub fn to_u8(self) -> (u8, u8, u8, u8) {
        (
            (self.r * 255.0).round().clamp(0.0, 255.0) as u8,
            (self.g * 255.0).round().clamp(0.0, 255.0) as u8,
            (self.b * 255.0).round().clamp(0.0, 255.0) as u8,
            (self.a * 255.0).round().clamp(0.0, 255.0) as u8,
        )
    }

    pub fn to_rgb_u8(self) -> (u8, u8, u8) {
        let (r, g, b, _) = self.to_u8();
        (r, g, b)
    }

    pub fn blend_over(self, bg: Self) -> Self {
        let a_out = self.a + bg.a * (1.0 - self.a);
        if a_out < 1e-6 {
            return Self::new(0.0, 0.0, 0.0, 0.0);
        }
        let r_out = (self.r * self.a + bg.r * bg.a * (1.0 - self.a)) / a_out;
        let g_out = (self.g * self.a + bg.g * bg.a * (1.0 - self.a)) / a_out;
        let b_out = (self.b * self.a + bg.b * bg.a * (1.0 - self.a)) / a_out;
        Self::new(
            r_out.clamp(0.0, 1.0),
            g_out.clamp(0.0, 1.0),
            b_out.clamp(0.0, 1.0),
            a_out.clamp(0.0, 1.0),
        )
    }
}

impl Default for Rgba {
    fn default() -> Self {
        Self::new(0.0, 0.0, 0.0, 1.0)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Color {
    Named(u8),
    Rgb(u8, u8, u8),
    Rgba(Rgba),
}

impl Color {
    pub const BLACK: Self = Self::Named(0);
    pub const RED: Self = Self::Named(1);
    pub const GREEN: Self = Self::Named(2);
    pub const YELLOW: Self = Self::Named(3);
    pub const BLUE: Self = Self::Named(4);
    pub const MAGENTA: Self = Self::Named(5);
    pub const CYAN: Self = Self::Named(6);
    pub const WHITE: Self = Self::Named(7);
    pub const DARK_GRAY: Self = Self::Named(8);
    pub const LIGHT_RED: Self = Self::Named(9);
    pub const LIGHT_GREEN: Self = Self::Named(10);
    pub const LIGHT_YELLOW: Self = Self::Named(11);
    pub const LIGHT_BLUE: Self = Self::Named(12);
    pub const LIGHT_MAGENTA: Self = Self::Named(13);
    pub const LIGHT_CYAN: Self = Self::Named(14);
    pub const GRAY: Self = Self::Named(15);

    pub const fn from_rgb(r: u8, g: u8, b: u8) -> Self {
        Self::Rgb(r, g, b)
    }

    pub fn from_hex(hex: &str) -> Option<Self> {
        let hex = hex.trim_start_matches('#');
        if hex.len() != 6 {
            return None;
        }
        let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
        let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
        let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
        Some(Self::Rgb(r, g, b))
    }

    pub fn to_rgba(self) -> Rgba {
        match self {
            Color::Named(idx) => Self::ansi_256_to_rgba(idx as u16),
            Color::Rgb(r, g, b) => Rgba::from_u8(r, g, b, 255),
            Color::Rgba(rgba) => rgba,
        }
    }

    pub fn to_rgb(self) -> (u8, u8, u8) {
        match self {
            Color::Named(idx) => {
                let rgba = Self::ansi_256_to_rgba(idx as u16);
                rgba.to_rgb_u8()
            }
            Color::Rgb(r, g, b) => (r, g, b),
            Color::Rgba(rgba) => rgba.to_rgb_u8(),
        }
    }

    fn ansi_256_to_rgba(idx: u16) -> Rgba {
        let (r, g, b): (u8, u8, u8) = match idx {
            0  => (0, 0, 0),
            1  => (205, 49, 49),
            2  => (13, 188, 121),
            3  => (229, 229, 16),
            4  => (36, 114, 200),
            5  => (188, 63, 188),
            6  => (17, 168, 205),
            7  => (229, 229, 229),
            8  => (102, 102, 102),
            9  => (241, 76, 76),
            10 => (35, 209, 139),
            11 => (245, 245, 67),
            12 => (59, 142, 234),
            13 => (214, 112, 214),
            14 => (41, 184, 219),
            15 => (229, 229, 229),
            16..=231 => {
                let idx = idx - 16;
                let r = (idx / 36) % 6;
                let g = (idx / 6) % 6;
                let b = idx % 6;
                let ramp: [u8; 6] = [0, 95, 135, 175, 215, 255];
                (ramp[r as usize], ramp[g as usize], ramp[b as usize])
            }
            232..=255 => {
                let val: u8 = ((idx - 232) * 10 + 8) as u8;
                (val, val, val)
            }
            _ => (0u8, 0u8, 0u8),
        };
        Rgba::from_u8(r, g, b, 255)
    }
}

impl Default for Color {
    fn default() -> Self {
        Self::WHITE
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rgba_new() {
        let c = Rgba::new(1.0, 0.5, 0.0, 1.0);
        assert!((c.r - 1.0).abs() < 1e-6);
        assert!((c.g - 0.5).abs() < 1e-6);
        assert!((c.b).abs() < 1e-6);
        assert!((c.a - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_rgba_from_u8_roundtrip() {
        let c = Rgba::from_u8(255, 128, 0, 200);
        let (r, g, b, a) = c.to_u8();
        assert_eq!(r, 255);
        assert_eq!(g, 128);
        assert_eq!(b, 0);
        assert!((a as i32 - 200).abs() <= 1);
    }

    #[test]
    fn test_rgba_to_rgb_u8_drops_alpha() {
        let c = Rgba::from_u8(10, 20, 30, 99);
        let (r, g, b) = c.to_rgb_u8();
        assert_eq!(r, 10);
        assert_eq!(g, 20);
        assert_eq!(b, 30);
    }

    #[test]
    fn test_rgba_blend_over_opaque() {
        let fg = Rgba::new(1.0, 0.0, 0.0, 1.0);
        let bg = Rgba::new(0.0, 1.0, 0.0, 1.0);
        let result = fg.blend_over(bg);
        assert_eq!(result.to_rgb_u8(), (255, 0, 0));
    }

    #[test]
    fn test_rgba_blend_over_transparent_fg() {
        let fg = Rgba::new(1.0, 0.0, 0.0, 0.0);
        let bg = Rgba::new(0.0, 0.0, 1.0, 1.0);
        let result = fg.blend_over(bg);
        assert_eq!(result.to_rgb_u8(), (0, 0, 255));
    }

    #[test]
    fn test_rgba_blend_over_half() {
        let fg = Rgba::new(1.0, 0.0, 0.0, 0.5);
        let bg = Rgba::new(0.0, 0.0, 1.0, 1.0);
        let result = fg.blend_over(bg);
        let (r, _, b) = result.to_rgb_u8();
        assert!(r > 100 && r < 200);
        assert!(b > 50 && b < 200);
    }

    #[test]
    fn test_rgba_blend_two_transparent() {
        let fg = Rgba::new(1.0, 0.0, 0.0, 0.0);
        let bg = Rgba::new(0.0, 1.0, 0.0, 0.0);
        let result = fg.blend_over(bg);
        assert!((result.r).abs() < 1e-6);
        assert!((result.a).abs() < 1e-6);
    }

    #[test]
    fn test_rgba_default_is_opaque_black() {
        let c = Rgba::default();
        assert_eq!(c.to_rgb_u8(), (0, 0, 0));
        assert!((c.a - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_color_from_hex_valid() {
        assert_eq!(Color::from_hex("#ff0000"), Some(Color::Rgb(255, 0, 0)));
        assert_eq!(Color::from_hex("#00ff00"), Some(Color::Rgb(0, 255, 0)));
        assert_eq!(Color::from_hex("#0000ff"), Some(Color::Rgb(0, 0, 255)));
        assert_eq!(Color::from_hex("aabbcc"), Some(Color::Rgb(170, 187, 204)));
    }

    #[test]
    fn test_color_from_hex_invalid() {
        assert_eq!(Color::from_hex("gggggg"), None);
        assert_eq!(Color::from_hex("#fff"), None);
        assert_eq!(Color::from_hex(""), None);
        assert_eq!(Color::from_hex("#12345"), None);
    }

    #[test]
    fn test_color_from_rgb_const() {
        let c = Color::from_rgb(100, 200, 50);
        assert_eq!(c, Color::Rgb(100, 200, 50));
    }

    #[test]
    fn test_color_to_rgb_named() {
        let (r, g, b) = Color::RED.to_rgb();
        assert!(r > 100);
        assert!(g < 80);
        assert!(b < 80);
    }

    #[test]
    fn test_color_to_rgb_rgb_variant() {
        let (r, g, b) = Color::Rgb(42, 84, 128).to_rgb();
        assert_eq!((r, g, b), (42, 84, 128));
    }

    #[test]
    fn test_color_to_rgb_rgba_variant() {
        let c = Color::Rgba(Rgba::from_u8(10, 20, 30, 255));
        assert_eq!(c.to_rgb(), (10, 20, 30));
    }

    #[test]
    fn test_color_to_rgba() {
        let c = Color::Rgb(100, 150, 200);
        let rgba = c.to_rgba();
        assert!((rgba.r - 100.0 / 255.0).abs() < 1e-4);
        assert!((rgba.a - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_ansi_black() {
        let (r, g, b) = Color::BLACK.to_rgb();
        assert!(r < 50);
        assert!(g < 50);
        assert!(b < 50);
    }

    #[test]
    fn test_ansi_white() {
        let (r, g, b) = Color::WHITE.to_rgb();
        assert!(r > 200);
        assert!(g > 200);
        assert!(b > 200);
    }

    #[test]
    fn test_ansi_color_cube_16() {
        let (r, g, b) = Color::ansi_256_to_rgba(16).to_rgb_u8();
        assert_eq!((r, g, b), (0, 0, 0));
    }

    #[test]
    fn test_ansi_color_cube_196() {
        let (r, _, _) = Color::ansi_256_to_rgba(196).to_rgb_u8();
        assert_eq!(r, 255);
    }

    #[test]
    fn test_ansi_grayscale_232() {
        let (r, g, b) = Color::ansi_256_to_rgba(232).to_rgb_u8();
        assert_eq!(r, 8);
        assert_eq!(g, 8);
        assert_eq!(b, 8);
    }

    #[test]
    fn test_ansi_grayscale_255() {
        let (r, _, _) = Color::ansi_256_to_rgba(255).to_rgb_u8();
        assert_eq!(r, 238);
    }

    #[test]
    fn test_ansi_out_of_range() {
        let (r, g, b) = Color::ansi_256_to_rgba(999).to_rgb_u8();
        assert_eq!((r, g, b), (0, 0, 0));
    }

    #[test]
    fn test_color_default_is_white() {
        let c: Color = Default::default();
        assert_eq!(c, Color::WHITE);
    }

    #[test]
    fn test_all_named_color_constants() {
        assert!(matches!(Color::BLACK, Color::Named(0)));
        assert!(matches!(Color::RED, Color::Named(1)));
        assert!(matches!(Color::GREEN, Color::Named(2)));
        assert!(matches!(Color::YELLOW, Color::Named(3)));
        assert!(matches!(Color::BLUE, Color::Named(4)));
        assert!(matches!(Color::MAGENTA, Color::Named(5)));
        assert!(matches!(Color::CYAN, Color::Named(6)));
        assert!(matches!(Color::WHITE, Color::Named(7)));
        assert!(matches!(Color::DARK_GRAY, Color::Named(8)));
        assert!(matches!(Color::LIGHT_RED, Color::Named(9)));
        assert!(matches!(Color::LIGHT_GREEN, Color::Named(10)));
        assert!(matches!(Color::LIGHT_YELLOW, Color::Named(11)));
        assert!(matches!(Color::LIGHT_BLUE, Color::Named(12)));
        assert!(matches!(Color::LIGHT_MAGENTA, Color::Named(13)));
        assert!(matches!(Color::LIGHT_CYAN, Color::Named(14)));
        assert!(matches!(Color::GRAY, Color::Named(15)));
    }

    #[test]
    fn test_rgba_clamp_out_of_range() {
        let c = Rgba::new(1.5, -0.2, 2.0, 0.5);
        let (r, g, b, a) = c.to_u8();
        assert_eq!(r, 255);
        assert_eq!(g, 0);
        assert_eq!(b, 255);
        assert_eq!(a, 128);
    }

    #[test]
    fn test_from_hex_mixed_case() {
        let c = Color::from_hex("#FFff00");
        assert!(c.is_some());
    }

    #[test]
    fn test_from_hex_8_digits() {
        let c = Color::from_hex("#ff0000ff");
        assert!(c.is_none());
    }

    #[test]
    fn test_from_hex_whitespace() {
        let c = Color::from_hex("  #ff0000  ");
        assert!(c.is_none());
    }

    #[test]
    fn test_ansi_color_cube_spot_check() {
        let c = Color::Named(196);
        let (r, g, b) = c.to_rgb();
        assert_eq!(r, 255);
        assert_eq!(g, 0);
        assert_eq!(b, 0);
    }

    #[test]
    fn test_ansi_grayscale_spot_check() {
        let c = Color::Named(240);
        let (r, g, b) = c.to_rgb();
        assert_eq!(r, g);
        assert_eq!(g, b);
    }

    #[test]
    fn test_rgba_blend_alpha_half_bg() {
        let fg = Rgba::new(1.0, 0.0, 0.0, 0.5);
        let bg = Rgba::new(0.0, 0.0, 1.0, 0.5);
        let result = fg.blend_over(bg);
        assert!(result.r > 0.0 && result.r < 1.0);
        assert!(result.b > 0.0 && result.b < 1.0);
    }

    #[test]
    fn test_color_to_rgb_rgba_with_alpha() {
        let c = Color::Rgba(Rgba::new(0.5, 0.5, 0.5, 0.3));
        let (r, g, b) = c.to_rgb();
        assert_eq!(r, 128);
        assert_eq!(g, 128);
        assert_eq!(b, 128);
    }
}
