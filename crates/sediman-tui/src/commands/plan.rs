use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_plan(app: &mut App, _args: &str) {
    if app.permission.is_plan_mode() {
        app.permission.set_plan_mode(false);
        app.add_system_message("Plan mode off.".into());
    } else {
        app.permission.set_plan_mode(true);
        app.add_system_message("Plan mode: researching without making changes.".into());
        app.add_system_message("Type /plan again to toggle off.".into());
    }
}

pub static CMD_PLAN: Command = Command {
    name: "/plan",
    aliases: &[],
    description: "Toggle plan mode (read-only research)",
    category: CommandCategory::Agent,
};
