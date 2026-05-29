mod registry;
mod fuzzy;

pub use registry::{CommandRegistry, Command, CommandCategory};
pub use fuzzy::fuzzy_match;
