pub mod input;
pub mod widgets;
pub mod layout;
pub mod styling;
pub mod command;
pub mod event;

pub use event::{AppEvent, EventLoop};
pub use layout::{LayoutManager, Zone};
pub use styling::Theme;
pub use command::CommandRegistry;
pub use command::{AppContext, Command, CommandCategory};
pub use input::{TextEditor, Completer};
pub use widgets::{
    StatusBar, ProgressPanel, ResultPanel, Banner, HelpOverlay, ContextBar,
};
