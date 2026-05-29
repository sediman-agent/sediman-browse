use crate::client::{ApiClient, BridgeResult};

impl ApiClient {
    pub async fn register_skill_schedule(
        &self,
        skill_name: &str,
        cron_expr: &str,
    ) -> BridgeResult<String> {
        self.add_schedule(cron_expr, skill_name).await
    }
}
