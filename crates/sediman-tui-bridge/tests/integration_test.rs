use serde_json::json;

/// Integration tests for the bridge client.
/// Each test spawns its own in-process mock server on a random port.
async fn spawn_test_server() -> (String, tokio::sync::oneshot::Sender<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind");
    let port = listener.local_addr().unwrap().port();
    let addr = format!("http://127.0.0.1:{}", port);
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

    (addr, shutdown_tx)
}

async fn serve(listener: tokio::net::TcpListener) -> Result<(), Box<dyn std::error::Error>> {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

    loop {
        let (mut stream, _) = listener.accept().await?;
        let mut reader = BufReader::new(&mut stream);
        let mut request_line = String::new();
        reader.read_line(&mut request_line).await?;

        let mut content_length = 0usize;
        let path = request_line
            .split_whitespace()
            .nth(1)
            .unwrap_or("")
            .to_string();

        loop {
            let mut header = String::new();
            reader.read_line(&mut header).await?;
            if header.trim().is_empty() {
                break;
            }
            if let Some(len_str) = header.trim().to_lowercase().strip_prefix("content-length:") {
                content_length = len_str.trim().parse().unwrap_or(0);
            }
        }

        let mut body = vec![0u8; content_length];
        if content_length > 0 {
            use tokio::io::AsyncReadExt;
            reader.read_exact(&mut body).await?;
        }

        let response: serde_json::Value = match path.as_str() {
            "/api/status" => json!({"running":true,"uptime_secs":42,"browser_open":true,"tasks_completed":7}),
            "/api/skills" => json!([{"name":"test-skill","description":"A test skill","category":"browser","version":1}]),
            "/api/skills/test-skill" => json!({"name":"test-skill","description":"A test skill","category":"browser","version":1,"steps":[{"description":"Go to site","url":"https://example.com"}],"variables":[],"when_to_use":["testing"],"pitfalls":[],"verification":[]}),
            "/api/skills/test-skill/run" => json!({"task":"test-skill","result":"ok","success":true,"steps":[],"elapsed_secs":1}),
            "/api/hub/browse" => json!([{"name":"hub-skill","description":"From hub","category":"browser","author":"test","version":1,"trust":"community"}]),
            "/api/hub/search?q=test" => json!([{"name":"hub-skill","description":"From hub","category":"browser","author":"test","version":1,"trust":"community"}]),
            "/api/hub/test-skill" => json!({"name":"test-skill","description":"Hub skill","category":"browser","author":"hub-author","version":1,"trust":"trusted"}),
            "/api/memory" => json!({"memory":"facts","user":"prefs","memory_entries":3,"user_entries":2}),
            "/api/sessions" => json!([{"id":1,"task":"test task","created_at":"2024-01-01","result":"ok"}]),
            "/api/schedule" => json!([{"id":"job-1","task":"daily task","cron_expr":"0 9 * * *","enabled":true,"last_run":null,"next_run":"2024-01-02"}]),
            _ if path.starts_with("/api/hub/install") => json!({"status":"ok"}),
            _ => json!({"error":"not found"}),
        };

        let body_str = serde_json::to_string(&response).unwrap();
        let resp = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nContent-Type: application/json\r\n\r\n{}",
            body_str.len(),
            body_str
        );
        stream.write_all(resp.as_bytes()).await?;
    }
}

#[tokio::test]
async fn test_status() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let status = client.status().await.unwrap();
    assert!(status.running);
    assert_eq!(status.uptime_secs, 42);
}

#[tokio::test]
async fn test_list_skills() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let skills = client.list_skills().await.unwrap();
    assert_eq!(skills.len(), 1);
    assert_eq!(skills[0].name, "test-skill");
}

#[tokio::test]
async fn test_get_skill() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let skill = client.get_skill("test-skill").await.unwrap();
    assert_eq!(skill.name, "test-skill");
}

#[tokio::test]
async fn test_execute_skill() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let result = client.execute_skill("test-skill").await.unwrap();
    assert!(result.success);
}

#[tokio::test]
async fn test_get_memory() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let mem = client.get_memory().await.unwrap();
    assert_eq!(mem.memory_entries, 3);
}

#[tokio::test]
async fn test_hub_browse() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let skills = client.hub_browse(None).await.unwrap();
    assert_eq!(skills.len(), 1);
}

#[tokio::test]
async fn test_hub_search() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let skills = client.hub_search("test").await.unwrap();
    assert_eq!(skills.len(), 1);
}

#[tokio::test]
async fn test_hub_install() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    client.hub_install("test-skill", false).await.unwrap();
}

#[tokio::test]
async fn test_list_schedules() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let jobs = client.list_schedules().await.unwrap();
    assert_eq!(jobs.len(), 1);
}

#[tokio::test]
async fn test_hub_info() {
    let (addr, _shutdown) = spawn_test_server().await;
    let client = sediman_tui_bridge::ApiClient::new(&addr).unwrap();
    let skill = client.hub_info("test-skill").await.unwrap();
    assert_eq!(skill.name, "test-skill");
}
