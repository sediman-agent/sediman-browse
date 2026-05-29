use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::App;

pub async fn handle_plan(app: &mut App, _args: &str) {
    if app.permission.current_label() == "plan" {
        app.permission.set_plan_mode(!app.permission.is_plan_mode());
        if app.permission.is_plan_mode() {
            app.step_log.push("ℹ Plan mode on — research only, no changes.".into());
        } else {
            app.step_log.push("ℹ Plan mode off.".into());
        }
    } else {
        app.permission.set_plan_mode(true);
        app.step_log.push("ℹ Plan mode: researching without making changes.".into());
        app.step_log.push("  Type /plan again to toggle off.".into());
    }
}

pub static CMD_PLAN: Command = Command {
    name: "/plan",
    aliases: &[],
    description: "Toggle plan mode (read-only research)",
    category: CommandCategory::Agent,
    handler: |_, _| Box::new(std::future::ready(())),
};
