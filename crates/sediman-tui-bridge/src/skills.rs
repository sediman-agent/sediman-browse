use crate::client::{ApiClient, BridgeResult};
use crate::types::HubSkill;

impl ApiClient {
    pub async fn hub_info(&self, name: &str) -> BridgeResult<HubSkill> {
        let resp = self
            .http
            .get(self.url(&format!("/api/hub/{}", name))?)
            .send()
            .await?;
        Ok(resp.json().await?)
    }
}
