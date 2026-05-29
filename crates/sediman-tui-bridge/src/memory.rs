use crate::client::{ApiClient, BridgeResult};

impl ApiClient {
    pub async fn remember(&self, text: &str) -> BridgeResult<()> {
        let body = serde_json::json!({"text": text});
        let resp = self
            .http
            .post(self.url("/api/memory")?)
            .json(&body)
            .send()
            .await?;
        if !resp.status().is_success() {
            return Err(crate::client::BridgeError::Api(resp.text().await?));
        }
        Ok(())
    }
}
