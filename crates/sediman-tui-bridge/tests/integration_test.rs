use serde_json::json;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixListener;

/// Spawns a mock JSON-RPC Unix socket server on a unique temp path.
async fn spawn_test_server() -> (String, tokio::sync::oneshot::Sender<()>) {
    use std::sync::atomic::{AtomicU64, Ordering};
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let dir = std::env::temp_dir();
    let pid = std::process::id();
    let seq = COUNTER.fetch_add(1, Ordering::SeqCst);
    let sock_path = dir.join(format!("sediman-test-{}-{}.sock", pid, seq));
    let _ = std::fs::remove_file(&sock_path);

    let listener = UnixListener::bind(&sock_path).expect("bind");
    let addr = sock_path.to_str().unwrap().to_string();
    let (shutdown_tx, shutdown_rx) = tokio::sync::oneshot::channel::<()>();

    tokio::spawn(async move {
        tokio::select! {
            _ = shutdown_rx => {}
            result = serve(listener) => {
                if let Err(e) = result {
                    eprintln!("Test server error: {}", e);
                }
            }
        }
    });

    // Give the server a moment to start
    tokio::time::sleep(std::time::Duration::from_millis(50)).await;

    (addr, shutdown_tx)
}

async fn serve(
    listener: UnixListener,
) -> Result<(), Box<dyn std::error::Error>> {
    loop {
        let (stream, _) = listener.accept().await?;
        let (reader, mut writer) = stream.into_split();
        let mut buf_reader = BufReader::new(reader);
        let mut line = String::new();

        buf_reader.read_line(&mut line).await?;
        let trimmed = line.trim().to_string();

        if let Ok(req) = serde_json::from_str::<serde_json::Value>(&trimmed) {
            let method = req["method"].as_str().unwrap_or("");
            let id = req.get("id");

            let response = match method {
                "system.status" => json_response(id, json!({"running":true,"uptime_secs":42,"browser_open":true,"tasks_completed":7})),
                "skills.list" => json_response(id, json!([{"name":"test-skill","description":"A test skill","category":"browser","version":1}])),
                "skills.get" => json_response(id, json!({"name":"test-skill","description":"A test skill","category":"browser","version":1,"steps":[{"description":"Go to site"}],"variables":[],"when_to_use":["testing"],"pitfalls":[],"verification":[]})),
                "skills.run" => json_response(id, json!({"task":"test-skill","result":"ok","success":true,"steps":[],"elapsed_secs":1})),
                "hub.browse" => json_response(id, json!([{"name":"hub-skill","description":"From hub","category":"browser","author":"test","version":1,"trust":"community"}])),
                "hub.search" => json_response(id, json!([{"name":"hub-skill","description":"From hub","category":"browser","author":"test","version":1,"trust":"community"}])),
                "hub.info" => json_response(id, json!({"name":"test-skill","description":"Hub skill","category":"browser","author":"hub-author","version":1,"trust":"trusted"})),
                "hub.update_skill" => json_response(id, json!({"updated":true,"message":"Updated to v2"})),
                "hub.remove" => json_response(id, json!({"removed":"test-skill"})),
                "hub.check_update" => json_response(id, json!({"hasUpdate":true,"message":"v2 available"})),
                "hub.publish" => json_response(id, json!({"published":"test-skill","message":"PR created"})),
                "skills.search" => json_response(id, json!([{"name":"result-1","description":"A result","score":0.95,"category":"browser","source":"hub"}])),
                "memory.get" => json_response(id, json!({"memory":"facts","user":"prefs","memory_entries":3,"user_entries":2})),
                "sessions.list" => json_response(id, json!([{"id":1,"task":"test task","created_at":"2024-01-01","result":"ok"}])),
                "schedule.list" => json_response(id, json!([{"id":"job-1","task":"daily task","cron_expr":"0 9 * * *","enabled":true,"last_run":null,"next_run":"2024-01-02"}])),
                "hub.install" => json_response(id, json!({"installed":"test-skill","message":"ok"})),
                _ => json_error(id, -32601, format!("Unknown: {}", method)),
            };

            let mut resp = serde_json::to_string(&response)?;
            resp.push('\n');
            writer.write_all(resp.as_bytes()).await?;
        }
    }
}

fn json_response(
    id: Option<&serde_json::Value>,
    result: serde_json::Value,
) -> serde_json::Value {
    json!({"jsonrpc": "2.0", "id": id, "result": result})
}

fn json_error(
    id: Option<&serde_json::Value>,
    code: i32,
    message: String,
) -> serde_json::Value {
    json!({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
}

#[tokio::test]
async fn test_status() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let status = client.status().await.unwrap();
    assert!(status.running);
    assert_eq!(status.uptime_secs, 42);
}

#[tokio::test]
async fn test_list_skills() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let skills = client.list_skills().await.unwrap();
    assert_eq!(skills.len(), 1);
    assert_eq!(skills[0].name, "test-skill");
}

#[tokio::test]
async fn test_get_skill() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let skill = client.get_skill("test-skill").await.unwrap();
    assert_eq!(skill.name, "test-skill");
}

#[tokio::test]
async fn test_execute_skill() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let result = client.execute_skill("test-skill").await.unwrap();
    assert!(result.success);
}

#[tokio::test]
async fn test_get_memory() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let mem = client.get_memory().await.unwrap();
    assert_eq!(mem.memory_entries, 3);
}

#[tokio::test]
async fn test_hub_browse() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let skills = client.hub_browse(None).await.unwrap();
    assert_eq!(skills.len(), 1);
}

#[tokio::test]
async fn test_hub_search() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let skills = client.hub_search("test").await.unwrap();
    assert_eq!(skills.len(), 1);
}

#[tokio::test]
async fn test_hub_install() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    client.hub_install("test-skill", false).await.unwrap();
}

#[tokio::test]
async fn test_list_schedules() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let jobs = client.list_schedules().await.unwrap();
    assert_eq!(jobs.len(), 1);
}

#[tokio::test]
async fn test_hub_info_detail() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let detail = client.hub_info_detail("test-skill").await.unwrap();
    assert_eq!(detail.name, "test-skill");
    assert_eq!(detail.author, "hub-author");
    assert_eq!(detail.trust, "trusted");
    let basic = client.hub_info_detail("test-skill").await.unwrap();
    assert_eq!(basic.name, "test-skill");
}

#[tokio::test]
async fn test_hub_update() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let msg = client.hub_update("test-skill").await.unwrap();
    assert!(msg.contains("Updated"));
}

#[tokio::test]
async fn test_hub_remove() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    client.hub_remove("test-skill").await.unwrap();
}

#[tokio::test]
async fn test_hub_check_update() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let (has_update, msg) = client.hub_check_update("test-skill").await.unwrap();
    assert!(has_update);
    assert!(msg.contains("v2"));
}

#[tokio::test]
async fn test_hub_publish() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let msg = client.hub_publish("test-skill").await.unwrap();
    assert!(msg.contains("PR"));
}

#[tokio::test]
async fn test_search_skills() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr);
    let results = client.search_skills("test", Some(10)).await.unwrap();
    assert_eq!(results.len(), 1);
    assert_eq!(results[0].name, "result-1");
    assert!((results[0].score - 0.95).abs() < f64::EPSILON);
    assert_eq!(results[0].category.as_deref(), Some("browser"));
    assert_eq!(results[0].source.as_deref(), Some("hub"));
}
