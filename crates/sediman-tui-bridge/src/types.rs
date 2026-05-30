#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_step_event_roundtrip() {
        let orig = StepEvent {
            phase: "executing".into(),
            action: "click button".into(),
            detail: Some("on #submit".into()),
            url: Some("https://example.com".into()),
            screenshot: None,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: StepEvent = serde_json::from_str(&json).unwrap();
        assert_eq!(orig.phase, restored.phase);
        assert_eq!(orig.action, restored.action);
        assert_eq!(orig.detail, restored.detail);
        assert_eq!(orig.url, restored.url);
        assert!(restored.screenshot.is_none());
    }

    #[test]
    fn test_step_event_missing_optionals() {
        let json = r#"{"phase":"done","action":"finished"}"#;
        let ev: StepEvent = serde_json::from_str(json).unwrap();
        assert_eq!(ev.phase, "done");
        assert_eq!(ev.action, "finished");
        assert!(ev.detail.is_none());
        assert!(ev.url.is_none());
        assert!(ev.screenshot.is_none());
    }

    #[test]
    fn test_agent_result_roundtrip() {
        let orig = AgentResult {
            task: "test task".into(),
            result: "completed ok".into(),
            success: true,
            steps: vec![StepEvent {
                phase: "executing".into(),
                action: "navigate".into(),
                detail: None,
                url: None,
                screenshot: None,
            }],
            skill_created: Some("my-skill".into()),
            scheduled_job_id: None,
            elapsed_secs: 42,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: AgentResult = serde_json::from_str(&json).unwrap();
        assert!(restored.success);
        assert_eq!(restored.elapsed_secs, 42);
        assert_eq!(restored.skill_created.unwrap(), "my-skill");
        assert_eq!(restored.steps.len(), 1);
    }

    #[test]
    fn test_agent_result_failure() {
        let json = r#"{"task":"fail","result":"error","success":false,"steps":[],"elapsed_secs":5}"#;
        let r: AgentResult = serde_json::from_str(json).unwrap();
        assert!(!r.success);
        assert!(r.skill_created.is_none());
        assert!(r.scheduled_job_id.is_none());
        assert_eq!(r.elapsed_secs, 5);
    }

    #[test]
    fn test_skill_summary_roundtrip() {
        let orig = SkillSummary {
            name: "test".into(),
            description: "a skill".into(),
            category: Some("browser".into()),
            version: 2,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: SkillSummary = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.name, "test");
        assert_eq!(restored.category.unwrap(), "browser");
    }

    #[test]
    fn test_skill_summary_no_category() {
        let json = r#"{"name":"x","description":"desc","version":1}"#;
        let s: SkillSummary = serde_json::from_str(json).unwrap();
        assert!(s.category.is_none());
    }

    #[test]
    fn test_skill_detail_with_steps() {
        let json = r#"{
            "name":"detail-skill","description":"detailed","version":3,
            "steps":[{"description":"Step 1"}],
            "variables":[{"name":"url","description":"the URL"}],
            "when_to_use":["for testing"],
            "pitfalls":["careful"],
            "verification":["works"]
        }"#;
        let s: SkillDetail = serde_json::from_str(json).unwrap();
        assert_eq!(s.steps.len(), 1);
        assert_eq!(s.variables.len(), 1);
        assert_eq!(s.when_to_use[0], "for testing");
        assert_eq!(s.pitfalls[0], "careful");
    }

    #[test]
    fn test_cron_job_roundtrip() {
        let orig = CronJob {
            id: "job-123".into(),
            task: "daily report".into(),
            cron_expr: "0 9 * * *".into(),
            skill_name: Some("report-skill".into()),
            enabled: true,
            last_run: Some("2024-01-01T09:00:00Z".into()),
            next_run: Some("2024-01-02T09:00:00Z".into()),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: CronJob = serde_json::from_str(&json).unwrap();
        assert!(restored.enabled);
        assert_eq!(restored.cron_expr, "0 9 * * *");
        assert_eq!(restored.skill_name.unwrap(), "report-skill");
    }

    #[test]
    fn test_hub_skill_roundtrip() {
        let orig = HubSkill {
            name: "hub-skill".into(),
            description: "community skill".into(),
            category: "data".into(),
            author: "community".into(),
            version: 1,
            trust: "trusted".into(),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: HubSkill = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.trust, "trusted");
    }

    #[test]
    fn test_memory_data_roundtrip() {
        let orig = MemoryData {
            memory: "key info".into(),
            user: "user prefs".into(),
            memory_entries: 3,
            user_entries: 1,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: MemoryData = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.memory_entries, 3);
        assert_eq!(restored.user, "user prefs");
    }

    #[test]
    fn test_ws_message_step() {
        let json = r#"{"type":"step","event":{"phase":"done","action":"ok"}}"#;
        let msg: WsMessage = serde_json::from_str(json).unwrap();
        assert_eq!(msg.msg_type, "step");
        assert!(msg.event.is_some());
        assert!(msg.result.is_none());
    }

    #[test]
    fn test_ws_message_result() {
        let json = r#"{"type":"result","result":{"task":"t","result":"ok","success":true,"steps":[],"elapsed_secs":1}}"#;
        let msg: WsMessage = serde_json::from_str(json).unwrap();
        assert_eq!(msg.msg_type, "result");
        let r = msg.result.unwrap();
        assert!(r.success);
    }

    #[test]
    fn test_ws_message_error() {
        let json = r#"{"type":"error","error":"something broke"}"#;
        let msg: WsMessage = serde_json::from_str(json).unwrap();
        assert_eq!(msg.error.unwrap(), "something broke");
    }

    #[test]
    fn test_server_status_roundtrip() {
        let orig = ServerStatus {
            running: true,
            uptime_secs: 3600,
            browser_open: false,
            tasks_completed: 99,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: ServerStatus = serde_json::from_str(&json).unwrap();
        assert!(restored.running);
        assert_eq!(restored.tasks_completed, 99);
        assert!(!restored.browser_open);
    }

    #[test]
    fn test_session_info() {
        let json = r#"{"id":42,"task":"my task","created_at":"2024-06-01","result":"done"}"#;
        let s: SessionInfo = serde_json::from_str(json).unwrap();
        assert_eq!(s.id, 42);
        assert_eq!(s.result.unwrap(), "done");
    }

    #[test]
    fn test_empty_steps() {
        let json = r#"{"task":"t","result":"ok","success":true,"steps":[],"elapsed_secs":0}"#;
        let r: AgentResult = serde_json::from_str(json).unwrap();
        assert!(r.steps.is_empty());
    }

    #[test]
    fn test_skill_detail_empty_fields() {
        let orig = SkillDetail {
            name: "test".into(),
            description: "desc".into(),
            category: Some("browser".into()),
            version: 1,
            steps: vec![],
            variables: vec![],
            when_to_use: vec![],
            pitfalls: vec![],
            verification: vec![],
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: SkillDetail = serde_json::from_str(&json).unwrap();
        assert!(restored.steps.is_empty());
        assert!(restored.variables.is_empty());
        assert!(restored.when_to_use.is_empty());
        assert!(restored.pitfalls.is_empty());
        assert!(restored.verification.is_empty());
    }

    #[test]
    fn test_session_info_with_result() {
        let orig = SessionInfo {
            id: 42,
            task: "my task".into(),
            created_at: "2024-06-01".into(),
            result: Some("done".into()),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: SessionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.id, 42);
        assert_eq!(restored.result, Some("done".into()));
    }

    #[test]
    fn test_session_info_no_result() {
        let json = r#"{"id":7,"task":"pending","created_at":"2024-01-01","result":null}"#;
        let s: SessionInfo = serde_json::from_str(json).unwrap();
        assert!(s.result.is_none());
    }

    #[test]
    fn test_hub_skill_roundtrip_full() {
        let orig = HubSkill {
            name: "My Skill".into(),
            description: "Does things".into(),
            category: "data".into(),
            author: "dev".into(),
            version: 2,
            trust: "trusted".into(),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: HubSkill = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.author, "dev");
        assert_eq!(restored.version, 2);
        assert_eq!(restored.trust, "trusted");
    }

    #[test]
    fn test_hub_skill_null_string_fields() {
        let json = r#"{"name":"x","description":"d","category":null,"author":null,"version":0,"trust":null}"#;
        let s: HubSkill = serde_json::from_str(json).unwrap();
        assert_eq!(s.name, "x");
        assert_eq!(s.category, "");
        assert_eq!(s.author, "");
        assert_eq!(s.trust, "");
    }

    #[test]
    fn test_hub_skill_all_null_strings() {
        let json = r#"{"name":null,"description":null,"category":null,"author":null,"trust":null}"#;
        let s: HubSkill = serde_json::from_str(json).unwrap();
        assert_eq!(s.name, "");
        assert_eq!(s.description, "");
        assert_eq!(s.category, "");
        assert_eq!(s.author, "");
        assert_eq!(s.trust, "");
    }

    #[test]
    fn test_hub_skill_missing_fields() {
        let json = r#"{}"#;
        let s: HubSkill = serde_json::from_str(json).unwrap();
        assert_eq!(s.name, "");
        assert_eq!(s.version, 0);
    }

    #[test]
    fn test_hub_skill_detail_null_strings() {
        let json = r#"{"name":null,"description":null,"category":null,"author":null,"trust":null}"#;
        let s: HubSkillDetail = serde_json::from_str(json).unwrap();
        assert_eq!(s.name, "");
        assert_eq!(s.description, "");
        assert_eq!(s.category, "");
        assert_eq!(s.author, "");
        assert_eq!(s.trust, "");
    }

    #[test]
    fn test_skill_search_result_null_strings() {
        let json = r#"{"name":null,"description":null,"score":0.5}"#;
        let s: SkillSearchResult = serde_json::from_str(json).unwrap();
        assert_eq!(s.name, "");
        assert_eq!(s.description, "");
        assert_eq!(s.score, 0.5);
    }

    #[test]
    fn test_ws_message_with_data() {
        let json = r#"{"type":"step","data":{"phase":"executing","action":"click"}}"#;
        let msg: WsMessage = serde_json::from_str(json).unwrap();
        assert_eq!(msg.msg_type, "step");
        assert!(msg.data.is_some());
        assert!(msg.event.is_none());
    }

    #[test]
    fn test_ws_message_streaming() {
        let json = r#"{"type":"streaming","streaming_token":{"token":"hello","phase":"responding"}}"#;
        let msg: WsMessage = serde_json::from_str(json).unwrap();
        assert_eq!(msg.msg_type, "streaming");
        let st = msg.streaming_token.unwrap();
        assert_eq!(st.token, "hello");
        assert_eq!(st.phase, "responding");
    }

    #[test]
    fn test_ws_message_streaming_default_phase() {
        let json = r#"{"type":"streaming","streaming_token":{"token":"world"}}"#;
        let msg: WsMessage = serde_json::from_str(json).unwrap();
        let st = msg.streaming_token.unwrap();
        assert_eq!(st.token, "world");
        assert_eq!(st.phase, "responding");
    }

    #[test]
    fn test_memory_data_roundtrip_full() {
        let orig = MemoryData {
            memory: "long memory text with unicode 世界".into(),
            user: "user context".into(),
            memory_entries: 5,
            user_entries: 3,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: MemoryData = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.memory_entries, 5);
        assert_eq!(restored.user_entries, 3);
        assert!(restored.memory.contains("世界"));
    }

    #[test]
    fn test_server_status_roundtrip_full() {
        let orig = ServerStatus {
            running: true,
            uptime_secs: 3600,
            browser_open: true,
            tasks_completed: 42,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: ServerStatus = serde_json::from_str(&json).unwrap();
        assert!(restored.running);
        assert!(restored.browser_open);
        assert_eq!(restored.tasks_completed, 42);
        assert_eq!(restored.uptime_secs, 3600);
    }

    #[test]
    fn test_cron_job_roundtrip_full() {
        let orig = CronJob {
            id: "job-1".into(),
            task: "daily report".into(),
            cron_expr: "0 9 * * *".into(),
            skill_name: Some("daily-backup".into()),
            enabled: true,
            last_run: Some("2024-01-01T09:00:00Z".into()),
            next_run: Some("2024-01-02T09:00:00Z".into()),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: CronJob = serde_json::from_str(&json).unwrap();
        assert!(restored.enabled);
        assert_eq!(restored.cron_expr, "0 9 * * *");
        assert_eq!(restored.skill_name.unwrap(), "daily-backup");
    }

    #[test]
    fn test_skill_variable_roundtrip() {
        let orig = SkillVariable {
            name: "url".into(),
            description: "the target URL".into(),
            default: Some("https://example.com".into()),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: SkillVariable = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.name, "url");
        assert_eq!(restored.default.unwrap(), "https://example.com");
    }

    #[test]
    fn test_skill_step_roundtrip() {
        let orig = SkillStep {
            description: "Click submit".into(),
            action_type: Some("click".into()),
            url: Some("https://example.com".into()),
            selector: Some("#submit".into()),
            text: None,
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: SkillStep = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.action_type.unwrap(), "click");
        assert!(restored.text.is_none());
    }

    #[test]
    fn test_hub_skill_detail_roundtrip() {
        let orig = HubSkillDetail {
            name: "detail-skill".into(),
            description: "A detailed skill".into(),
            category: "browser".into(),
            author: "test-author".into(),
            version: 3,
            trust: "trusted".into(),
            steps: vec![SkillStep {
                description: "Navigate to page".into(),
                action_type: Some("navigate".into()),
                url: Some("https://example.com".into()),
                selector: None,
                text: None,
            }],
            variables: vec![SkillVariable {
                name: "query".into(),
                description: "Search query".into(),
                default: Some("test".into()),
            }],
            warnings: vec!["May fail on slow connections".into()],
            license: Some("MIT".into()),
            schedule: Some("0 9 * * *".into()),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: HubSkillDetail = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.name, "detail-skill");
        assert_eq!(restored.version, 3);
        assert_eq!(restored.steps.len(), 1);
        assert_eq!(restored.variables.len(), 1);
        assert_eq!(restored.warnings.len(), 1);
        assert_eq!(restored.license.unwrap(), "MIT");
        assert_eq!(restored.schedule.unwrap(), "0 9 * * *");
    }

    #[test]
    fn test_hub_skill_detail_minimal() {
        let json = r#"{"name":"x","description":"d"}"#;
        let detail: HubSkillDetail = serde_json::from_str(json).unwrap();
        assert_eq!(detail.name, "x");
        assert!(detail.steps.is_empty());
        assert!(detail.variables.is_empty());
        assert!(detail.warnings.is_empty());
        assert!(detail.license.is_none());
        assert!(detail.schedule.is_none());
    }

    #[test]
    fn test_hub_skill_detail_from_hub_info_response() {
        let json = r#"{
            "name":"stock-checker",
            "description":"Check stock prices",
            "category":"finance",
            "author":"community",
            "version":2,
            "trust":"community",
            "steps":[{"description":"Go to Yahoo Finance","action_type":"navigate","url":"https://finance.yahoo.com"}],
            "variables":[{"name":"ticker","description":"Stock ticker symbol","default":"AAPL"}],
            "warnings":["Rate limited to 5 req/min"],
            "license":"Apache-2.0",
            "schedule":"0 */4 * * *"
        }"#;
        let detail: HubSkillDetail = serde_json::from_str(json).unwrap();
        assert_eq!(detail.steps[0].action_type.as_deref(), Some("navigate"));
        assert_eq!(detail.variables[0].name, "ticker");
        assert_eq!(detail.warnings[0], "Rate limited to 5 req/min");
    }

    #[test]
    fn test_skill_search_result_roundtrip() {
        let orig = SkillSearchResult {
            name: "search-skill".into(),
            description: "Searches things".into(),
            score: 0.95,
            category: Some("search".into()),
            source: Some("hub".into()),
        };
        let json = serde_json::to_string(&orig).unwrap();
        let restored: SkillSearchResult = serde_json::from_str(&json).unwrap();
        assert_eq!(restored.name, "search-skill");
        assert!((restored.score - 0.95).abs() < f64::EPSILON);
        assert_eq!(restored.category.unwrap(), "search");
        assert_eq!(restored.source.unwrap(), "hub");
    }

    #[test]
    fn test_skill_search_result_minimal() {
        let json = r#"{"name":"x","description":"d","score":0.5}"#;
        let r: SkillSearchResult = serde_json::from_str(json).unwrap();
        assert_eq!(r.name, "x");
        assert!(r.category.is_none());
        assert!(r.source.is_none());
    }

    #[test]
    fn test_hub_skill_default_fields() {
        let json = r#"{"name":"s","description":"d"}"#;
        let s: HubSkill = serde_json::from_str(json).unwrap();
        assert_eq!(s.name, "s");
        assert!(s.category.is_empty());
        assert!(s.author.is_empty());
        assert_eq!(s.version, 0);
        assert!(s.trust.is_empty());
    }

    #[test]
    fn test_session_info_null_fields() {
        let json = r#"{"id":1,"task":null,"created_at":null}"#;
        let s: SessionInfo = serde_json::from_str(json).unwrap();
        assert_eq!(s.id, 1);
        assert_eq!(s.task, "");
        assert_eq!(s.created_at, "");
        assert!(s.result.is_none());
    }

    #[test]
    fn test_session_info_missing_fields() {
        let json = r#"{"id":5}"#;
        let s: SessionInfo = serde_json::from_str(json).unwrap();
        assert_eq!(s.id, 5);
        assert_eq!(s.task, "");
    }
}

use serde::{Deserialize, Deserializer, Serialize};

fn null_to_default<'de, D, T>(de: D) -> Result<T, D::Error>
where
    D: Deserializer<'de>,
    T: Default + Deserialize<'de>,
{
    Option::<T>::deserialize(de).map(|v| v.unwrap_or_default())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepEvent {
    #[serde(default)]
    pub phase: String,
    #[serde(default)]
    pub action: String,
    #[serde(default, alias = "observation")]
    pub detail: Option<String>,
    #[serde(default)]
    pub url: Option<String>,
    #[serde(default)]
    pub screenshot: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResult {
    #[serde(default)]
    pub task: String,
    pub result: String,
    #[serde(default)]
    pub success: bool,
    #[serde(default)]
    pub steps: Vec<StepEvent>,
    pub skill_created: Option<String>,
    pub scheduled_job_id: Option<String>,
    #[serde(default)]
    pub elapsed_secs: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillSummary {
    pub name: String,
    pub description: String,
    pub category: Option<String>,
    pub version: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillDetail {
    pub name: String,
    pub description: String,
    pub category: Option<String>,
    pub version: i32,
    pub steps: Vec<SkillStep>,
    pub variables: Vec<SkillVariable>,
    pub when_to_use: Vec<String>,
    pub pitfalls: Vec<String>,
    pub verification: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillStep {
    pub description: String,
    pub action_type: Option<String>,
    pub url: Option<String>,
    pub selector: Option<String>,
    pub text: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillVariable {
    pub name: String,
    pub description: String,
    pub default: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CronJob {
    pub id: String,
    pub task: String,
    pub cron_expr: String,
    pub skill_name: Option<String>,
    pub enabled: bool,
    pub last_run: Option<String>,
    pub next_run: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HubSkill {
    #[serde(default, deserialize_with = "null_to_default")]
    pub name: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub description: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub category: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub author: String,
    #[serde(default)]
    pub version: i32,
    #[serde(default, deserialize_with = "null_to_default")]
    pub trust: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HubSkillDetail {
    #[serde(default, deserialize_with = "null_to_default")]
    pub name: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub description: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub category: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub author: String,
    #[serde(default)]
    pub version: i32,
    #[serde(default, deserialize_with = "null_to_default")]
    pub trust: String,
    #[serde(default)]
    pub steps: Vec<SkillStep>,
    #[serde(default)]
    pub variables: Vec<SkillVariable>,
    #[serde(default)]
    pub warnings: Vec<String>,
    #[serde(default)]
    pub license: Option<String>,
    #[serde(default)]
    pub schedule: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillSearchResult {
    #[serde(default, deserialize_with = "null_to_default")]
    pub name: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub description: String,
    #[serde(default)]
    pub score: f64,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default)]
    pub source: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    #[serde(default)]
    pub id: i64,
    #[serde(default, deserialize_with = "null_to_default")]
    pub task: String,
    #[serde(default, deserialize_with = "null_to_default")]
    pub created_at: String,
    #[serde(default)]
    pub result: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryData {
    pub memory: String,
    pub user: String,
    pub memory_entries: i32,
    pub user_entries: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerStatus {
    pub running: bool,
    pub uptime_secs: u64,
    pub browser_open: bool,
    pub tasks_completed: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WsMessage {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub data: Option<serde_json::Value>,
    pub event: Option<StepEvent>,
    pub result: Option<AgentResult>,
    pub error: Option<String>,
    pub streaming_token: Option<StreamingToken>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamingToken {
    pub token: String,
    #[serde(default = "default_phase")]
    pub phase: String,
}

fn default_phase() -> String {
    "responding".to_string()
}
