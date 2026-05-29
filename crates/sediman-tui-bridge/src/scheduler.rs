use crate::client::{ApiClient, BridgeResult};

impl ApiClient {
    pub async fn register_skill_schedule(
        &self,
        skill_name: &str,
        cron_expr: &str,
    ) -> BridgeResult<String> {
        let body = serde_json::json!({
            "skill_name": skill_name,
            "cron_expr": cron_expr,
        });
        let resp = self
            .http
            .post(self.url("/api/schedule")?)
            .json(&body)
            .send()
            .await?;
        let job: serde_json::Value = resp.json().await?;
        Ok(job["id"].as_str().unwrap_or("unknown").to_string())
    }
}
