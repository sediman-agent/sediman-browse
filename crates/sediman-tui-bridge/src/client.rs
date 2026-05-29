use std::sync::Arc;

use reqwest::header::{HeaderMap, HeaderValue};
use tokio::sync::Mutex;
use url::Url;

use crate::types::*;

#[derive(thiserror::Error, Debug)]
pub enum BridgeError {
    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("WebSocket error: {0}")]
    Ws(#[from] tokio_tungstenite::tungstenite::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("URL parse error: {0}")]
    Url(#[from] url::ParseError),
    #[error("API error: {0}")]
    Api(String),
    #[error("Connection refused: {0}")]
    Connection(String),
}

pub type BridgeResult<T> = Result<T, BridgeError>;

#[derive(Debug)]
pub struct ApiClient {
    base_url: Url,
    pub(crate) http: reqwest::Client,
    #[allow(dead_code)]
    ws_tx: Arc<Mutex<Option<tokio::sync::mpsc::UnboundedSender<WsMessage>>>>,
}

impl ApiClient {
    pub fn new(base_url: &str) -> BridgeResult<Self> {
        let base = Url::parse(base_url)?;
        let mut headers = HeaderMap::new();
        headers.insert("Content-Type", HeaderValue::from_static("application/json"));

        let http = reqwest::Client::builder()
            .default_headers(headers)
            .build()?;

        Ok(Self {
            base_url: base,
            http,
            ws_tx: Arc::new(Mutex::new(None)),
        })
    }

    pub(crate) fn url(&self, path: &str) -> BridgeResult<Url> {
        Ok(self.base_url.join(path)?)
    }

    pub async fn status(&self) -> BridgeResult<ServerStatus> {
        let resp = self.http.get(self.url("/api/status")?).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn list_skills(&self) -> BridgeResult<Vec<SkillSummary>> {
        let resp = self.http.get(self.url("/api/skills")?).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn get_skill(&self, name: &str) -> BridgeResult<SkillDetail> {
        let resp = self
            .http
            .get(self.url(&format!("/api/skills/{}", name))?)
            .send()
            .await?;
        Ok(resp.json().await?)
    }

    pub async fn delete_skill(&self, name: &str) -> BridgeResult<()> {
        self.http
            .delete(self.url(&format!("/api/skills/{}", name))?)
            .send()
            .await?;
        Ok(())
    }

    pub async fn execute_skill(&self, name: &str) -> BridgeResult<AgentResult> {
        let resp = self
            .http
            .post(self.url(&format!("/api/skills/{}/run", name))?)
            .send()
            .await?;
        Ok(resp.json().await?)
    }

    pub async fn hub_browse(&self, category: Option<&str>) -> BridgeResult<Vec<HubSkill>> {
        let mut url = self.url("/api/hub/browse")?;
        if let Some(cat) = category {
            url.set_query(Some(&format!("category={}", cat)));
        }
        let resp = self.http.get(url).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn hub_search(&self, query: &str) -> BridgeResult<Vec<HubSkill>> {
        let url = self.url(&format!("/api/hub/search?q={}", query))?;
        let resp = self.http.get(url).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn hub_install(&self, name: &str, force: bool) -> BridgeResult<()> {
        let body = serde_json::json!({"name": name, "force": force});
        let resp = self
            .http
            .post(self.url("/api/hub/install")?)
            .json(&body)
            .send()
            .await?;
        if !resp.status().is_success() {
            return Err(BridgeError::Api(resp.text().await?));
        }
        Ok(())
    }

    pub async fn list_schedules(&self) -> BridgeResult<Vec<CronJob>> {
        let resp = self.http.get(self.url("/api/schedule")?).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn add_schedule(
        &self,
        cron_expr: &str,
        task: &str,
    ) -> BridgeResult<String> {
        let body = serde_json::json!({"cron_expr": cron_expr, "task": task});
        let resp = self
            .http
            .post(self.url("/api/schedule")?)
            .json(&body)
            .send()
            .await?;
        let job: serde_json::Value = resp.json().await?;
        Ok(job["id"].as_str().unwrap_or("unknown").to_string())
    }

    pub async fn remove_schedule(&self, job_id: &str) -> BridgeResult<()> {
        self.http
            .delete(self.url(&format!("/api/schedule/{}", job_id))?)
            .send()
            .await?;
        Ok(())
    }

    pub async fn get_memory(&self) -> BridgeResult<MemoryData> {
        let resp = self.http.get(self.url("/api/memory")?).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn get_sessions(&self) -> BridgeResult<Vec<SessionInfo>> {
        let resp = self.http.get(self.url("/api/sessions")?).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn get_screenshot(&self) -> BridgeResult<Vec<u8>> {
        let resp = self.http.get(self.url("/api/screenshot")?).send().await?;
        Ok(resp.bytes().await?.to_vec())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_client_valid_url() {
        let c = ApiClient::new("http://localhost:8080").unwrap();
        assert_eq!(c.base_url.as_str(), "http://localhost:8080/");
    }

    #[test]
    fn test_new_client_trailing_slash() {
        let c = ApiClient::new("http://localhost:8080/").unwrap();
        assert_eq!(c.base_url.as_str(), "http://localhost:8080/");
    }

    #[test]
    fn test_new_client_invalid_url() {
        let err = ApiClient::new("not a url").unwrap_err();
        assert!(matches!(err, BridgeError::Url(_)));
    }

    #[test]
    fn test_new_client_empty_url() {
        let err = ApiClient::new("").unwrap_err();
        assert!(matches!(err, BridgeError::Url(_)));
    }

    #[test]
    fn test_url_construction() {
        let c = ApiClient::new("http://localhost:8080").unwrap();
        assert_eq!(
            c.url("/api/status").unwrap().as_str(),
            "http://localhost:8080/api/status"
        );
    }

    #[test]
    fn test_url_construction_with_trailing_slash() {
        let c = ApiClient::new("http://localhost:8080/").unwrap();
        assert_eq!(
            c.url("api/skills").unwrap().as_str(),
            "http://localhost:8080/api/skills"
        );
    }

    #[test]
    fn test_url_with_query() {
        let c = ApiClient::new("http://localhost:8080").unwrap();
        let mut url = c.url("/api/hub/search").unwrap();
        url.set_query(Some("q=test"));
        assert_eq!(url.as_str(), "http://localhost:8080/api/hub/search?q=test");
    }

    #[test]
    fn test_url_with_nested_path() {
        let c = ApiClient::new("http://localhost:8080").unwrap();
        let url = c.url("/api/skills/my-skill").unwrap();
        assert_eq!(url.as_str(), "http://localhost:8080/api/skills/my-skill");
    }

    #[test]
    fn test_url_https() {
        let c = ApiClient::new("https://api.sediman.ai").unwrap();
        let url = c.url("/v1/status").unwrap();
        assert_eq!(url.as_str(), "https://api.sediman.ai/v1/status");
    }

    #[test]
    fn test_bridge_error_display_http() {
        let err = BridgeError::Api("bad request".into());
        assert_eq!(format!("{}", err), "API error: bad request");
    }

    #[test]
    fn test_bridge_error_display_connection() {
        let err = BridgeError::Connection("refused".into());
        assert_eq!(format!("{}", err), "Connection refused: refused");
    }

    #[test]
    fn test_bridge_error_from_url_parse() {
        let err: BridgeError = url::ParseError::EmptyHost.into();
        assert!(matches!(err, BridgeError::Url(_)));
    }

    #[test]
    fn test_bridge_error_from_json() {
        let result: Result<serde_json::Value, serde_json::Error> =
            serde_json::from_str("invalid json");
        let err: BridgeError = result.unwrap_err().into();
        assert!(matches!(err, BridgeError::Json(_)));
    }
}
