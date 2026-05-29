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
}

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepEvent {
    pub phase: String,
    pub action: String,
    pub detail: Option<String>,
    pub url: Option<String>,
    pub screenshot: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResult {
    pub task: String,
    pub result: String,
    pub success: bool,
    pub steps: Vec<StepEvent>,
    pub skill_created: Option<String>,
    pub scheduled_job_id: Option<String>,
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
    pub name: String,
    pub description: String,
    pub category: String,
    pub author: String,
    pub version: i32,
    pub trust: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: i64,
    pub task: String,
    pub created_at: String,
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
}
