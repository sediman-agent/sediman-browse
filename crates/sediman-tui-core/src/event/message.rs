use crossterm::event::KeyEvent;

pub enum AppEvent {
    Key(KeyEvent),
    Tick,
    Resize(u16, u16),
    Channel(Box<dyn std::any::Any + Send>),
}
