use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

use crate::types::*;

#[derive(thiserror::Error, Debug)]
pub enum BridgeError {
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("API error: {0}")]
    Api(String),
    #[error("Connection failed: {0}")]
    Connection(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

pub type BridgeResult<T> = Result<T, BridgeError>;

#[derive(Debug)]
pub struct ApiClient {
    socket_path: PathBuf,
    next_id: AtomicU64,
}

impl ApiClient {
    pub fn new(socket_path: &str) -> Self {
        Self {
            socket_path: PathBuf::from(socket_path),
            next_id: AtomicU64::new(1),
        }
    }

    pub fn socket_path_str(&self) -> &str {
        self.socket_path.to_str().unwrap_or("/tmp/sediman.sock")
    }

    /// Send a JSON-RPC 2.0 request and deserialize the result.
    pub(crate) async fn call<T: serde::de::DeserializeOwned>(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> BridgeResult<T> {
        let result = self.send_request(method, params).await?;
        Ok(serde_json::from_value(result)?)
    }

    /// Send a JSON-RPC 2.0 request and return the raw result Value.
    pub(crate) async fn send_request(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> BridgeResult<serde_json::Value> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        let stream = UnixStream::connect(&self.socket_path)
            .await
            .map_err(|e| BridgeError::Connection(e.to_string()))?;
        let (reader, mut writer) = stream.into_split();

        let mut raw = serde_json::to_string(&request)?;
        raw.push('\n');
        writer
            .write_all(raw.as_bytes())
            .await
            .map_err(|e| BridgeError::Connection(e.to_string()))?;
        writer.shutdown().await.ok();

        let mut line = String::new();
        let mut buf_reader = BufReader::new(reader);
        buf_reader
            .read_line(&mut line)
            .await
            .map_err(|e| BridgeError::Connection(e.to_string()))?;

        let response: serde_json::Value = serde_json::from_str(&line)?;

        if let Some(err) = response.get("error") {
            let msg = err["message"]
                .as_str()
                .unwrap_or("unknown error")
                .to_string();
            return Err(BridgeError::Api(msg));
        }

        Ok(response["result"].clone())
    }

    /// Send a JSON-RPC request with automatic retry on connection failure.
    /// Retries up to `max_retries` times with exponential backoff.
    #[allow(dead_code)]
    pub async fn call_with_retry<T: serde::de::DeserializeOwned>(
        &self,
        method: &str,
        params: serde_json::Value,
        max_retries: u32,
    ) -> BridgeResult<T> {
        let mut attempt = 0;
        loop {
            match self.call(method, params.clone()).await {
                Ok(result) => return Ok(result),
                Err(BridgeError::Connection(msg)) => {
                    attempt += 1;
                    if attempt > max_retries {
                        return Err(BridgeError::Connection(msg));
                    }
                    // Exponential backoff: 100ms, 200ms, 400ms, 800ms...
                    let delay = std::time::Duration::from_millis(100 * 2u64.pow(attempt - 1));
                    tokio::time::sleep(delay).await;
                }
                Err(e) => return Err(e),
            }
        }
    }

    /// Check if the backend socket exists and is connectable.
    pub async fn is_connected(&self) -> bool {
        tokio::fs::metadata(&self.socket_path).await.is_ok()
    }

    // ── public API methods ──────────────────────────────────────

    pub async fn status(&self) -> BridgeResult<ServerStatus> {
        self.call("system.status", serde_json::json!({})).await
    }

    pub async fn list_skills(&self) -> BridgeResult<Vec<SkillSummary>> {
        self.call("skills.list", serde_json::json!({})).await
    }

    pub async fn get_skill(&self, name: &str) -> BridgeResult<SkillDetail> {
        self.call("skills.get", serde_json::json!({"name": name})).await
    }

    pub async fn delete_skill(&self, name: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "skills.delete",
            serde_json::json!({"name": name}),
        )
        .await?;
        Ok(())
    }

    pub async fn execute_skill(&self, name: &str) -> BridgeResult<AgentResult> {
        self.call("skills.run", serde_json::json!({"name": name})).await
    }

    pub async fn hub_browse(
        &self,
        category: Option<&str>,
    ) -> BridgeResult<Vec<HubSkill>> {
        let mut params = serde_json::json!({});
        if let Some(cat) = category {
            params["category"] = serde_json::json!(cat);
        }
        self.call("hub.browse", params).await
    }

    pub async fn hub_search(&self, query: &str) -> BridgeResult<Vec<HubSkill>> {
        self.call("hub.search", serde_json::json!({"query": query}))
            .await
    }

    pub async fn hub_install(&self, name: &str, force: bool) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "hub.install",
            serde_json::json!({"name": name, "force": force}),
        )
        .await?;
        Ok(())
    }

    pub async fn hub_install_github(&self, ref_: &str, force: bool) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "hub.install_github",
            serde_json::json!({"ref": ref_, "force": force}),
        )
        .await?;
        Ok(())
    }

    pub async fn hub_info(&self, name: &str) -> BridgeResult<HubSkill> {
        self.call("hub.info", serde_json::json!({"name": name}))
            .await
    }

    pub async fn hub_info_detail(&self, name: &str) -> BridgeResult<HubSkillDetail> {
        self.call("hub.info", serde_json::json!({"name": name}))
            .await
    }

    pub async fn hub_update(&self, name: &str) -> BridgeResult<String> {
        let resp: serde_json::Value = self
            .call(
                "hub.update_skill",
                serde_json::json!({"name": name}),
            )
            .await?;
        Ok(resp["message"].as_str().unwrap_or("Updated").to_string())
    }

    pub async fn hub_remove(&self, name: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "hub.remove",
            serde_json::json!({"name": name}),
        )
        .await?;
        Ok(())
    }

    pub async fn hub_check_update(&self, name: &str) -> BridgeResult<(bool, String)> {
        let resp: serde_json::Value = self
            .call(
                "hub.check_update",
                serde_json::json!({"name": name}),
            )
            .await?;
        let has_update = resp["hasUpdate"].as_bool().unwrap_or(false);
        let message = resp["message"].as_str().unwrap_or("").to_string();
        Ok((has_update, message))
    }

    pub async fn hub_publish(&self, name: &str) -> BridgeResult<String> {
        let resp: serde_json::Value = self
            .call(
                "hub.publish",
                serde_json::json!({"name": name}),
            )
            .await?;
        Ok(resp["message"].as_str().unwrap_or("Published").to_string())
    }

    pub async fn search_skills(&self, query: &str, limit: Option<usize>) -> BridgeResult<Vec<SkillSearchResult>> {
        let mut params = serde_json::json!({"query": query});
        if let Some(l) = limit {
            params["limit"] = serde_json::json!(l);
        }
        self.call("skills.search", params).await
    }

    pub async fn list_schedules(&self) -> BridgeResult<Vec<CronJob>> {
        self.call("schedule.list", serde_json::json!({})).await
    }

    pub async fn add_schedule(
        &self,
        cron_expr: &str,
        task: &str,
    ) -> BridgeResult<String> {
        let resp: serde_json::Value = self
            .call(
                "schedule.add",
                serde_json::json!({"cron": cron_expr, "task": task}),
            )
            .await?;
        Ok(resp["job_id"].as_str().unwrap_or("unknown").to_string())
    }

    pub async fn remove_schedule(&self, job_id: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "schedule.remove",
            serde_json::json!({"job_id": job_id}),
        )
        .await?;
        Ok(())
    }

    pub async fn get_memory(&self) -> BridgeResult<MemoryData> {
        self.call("memory.get", serde_json::json!({})).await
    }

    pub async fn get_sessions(&self) -> BridgeResult<Vec<SessionInfo>> {
        self.call("sessions.list", serde_json::json!({})).await
    }

    pub async fn get_screenshot(&self) -> BridgeResult<Vec<u8>> {
        let resp: serde_json::Value = self
            .call("system.screenshot", serde_json::json!({}))
            .await?;
        match resp.get("data").and_then(|d| d.as_str()) {
            Some(hex_data) => {
                let bytes: Result<Vec<u8>, _> = (0..hex_data.len())
                    .step_by(2)
                    .map(|i| u8::from_str_radix(&hex_data[i..i + 2], 16))
                    .collect();
                bytes.map_err(|e| BridgeError::Api(format!("hex decode: {}", e)))
            }
            None => Ok(Vec::new()),
        }
    }

    pub async fn start_recording(&self, name: &str) -> BridgeResult<String> {
        let resp: serde_json::Value = self
            .call("record.start", serde_json::json!({"name": name}))
            .await?;
        Ok(resp["id"].as_str().unwrap_or("unknown").to_string())
    }

    pub async fn stop_recording(&self, id: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "record.stop",
            serde_json::json!({"id": id}),
        )
        .await?;
        Ok(())
    }

    pub async fn set_soul(&self, text: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "system.set_soul",
            serde_json::json!({"text": text}),
        )
        .await?;
        Ok(())
    }

    pub async fn reset_soul(&self) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "system.set_soul",
            serde_json::json!({"text": "", "reset": true}),
        )
        .await?;
        Ok(())
    }

    /// Switch the LLM provider/model/base-url at runtime via model.switch RPC.
    pub async fn switch_model(
        &self,
        provider: &str,
        model: Option<&str>,
        base_url: Option<&str>,
    ) -> BridgeResult<()> {
        let mut params = serde_json::json!({"provider": provider});
        if let Some(m) = model {
            params["model"] = serde_json::json!(m);
        }
        if let Some(url) = base_url {
            params["base_url"] = serde_json::json!(url);
        }
        self.call::<serde_json::Value>("model.switch", params).await?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_client() {
        let c = ApiClient::new("/tmp/sediman.sock");
        assert_eq!(c.socket_path_str(), "/tmp/sediman.sock");
    }

    #[test]
    fn test_new_client_custom_path() {
        let c = ApiClient::new("/var/run/sediman.sock");
        assert_eq!(c.socket_path_str(), "/var/run/sediman.sock");
    }

    #[test]
    fn test_bridge_error_display_api() {
        let err = BridgeError::Api("bad request".into());
        assert_eq!(format!("{}", err), "API error: bad request");
    }

    #[test]
    fn test_bridge_error_display_connection() {
        let err = BridgeError::Connection("refused".into());
        assert_eq!(
            format!("{}", err),
            "Connection failed: refused"
        );
    }

    #[test]
    fn test_bridge_error_from_json() {
        let result: Result<serde_json::Value, serde_json::Error> =
            serde_json::from_str("invalid json");
        let err: BridgeError = result.unwrap_err().into();
        assert!(matches!(err, BridgeError::Json(_)));
    }
}
