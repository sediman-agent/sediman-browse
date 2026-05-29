mod registry;
mod fuzzy;

pub use registry::{CommandRegistry, Command, CommandCategory, AppContext};
pub use fuzzy::fuzzy_match;
