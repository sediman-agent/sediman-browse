use sediman_tui_core::command::{Command, CommandCategory};

use crate::app::{App, AppModal};

pub async fn handle_sessions(app: &mut App, _args: &str) {
    match app.bridge.get_sessions().await {
        Ok(sessions) => {
            app.session_list = sessions;
            app.session_selected = 0;
            app.session_scroll = 0;
            app.session_filter.clear();
            app.active_modal = Some(AppModal::SessionBrowser);
        }
        Err(e) => {
            app.add_error_message(format!("Failed to load sessions: {}", e));
        }
    }
}

pub static CMD_SESSIONS: Command = Command {
    name: "/sessions",
    aliases: &["/session"],
    description: "Browse & manage sessions",
    category: CommandCategory::Sessions,
};
