use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

use crate::client::{BridgeError, BridgeResult};
use crate::types::*;

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::AsyncReadExt;
    use tokio::net::UnixListener;
    use std::time::Duration;

    async fn spawn_fake_server(sock_path: &str) -> UnixListener {
        let listener = UnixListener::bind(sock_path).unwrap();
        listener
    }

    #[tokio::test]
    async fn test_task_stream_receives_streaming_notifications() {
        let sock_path = format!("/tmp/test_task_stream_{}.sock", std::process::id());
        let _ = std::fs::remove_file(&sock_path);

        let listener = spawn_fake_server(&sock_path).await;

        // Fake server: accept connection, read request, send streaming notifications then result
        let server_handle = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut buf = vec![0u8; 1024];
            let n = stream.read(&mut buf).await.unwrap();
            let _request = String::from_utf8_lossy(&buf[..n]);

            // Send streaming notifications
            for ch in "Hello".chars() {
                let msg = format!(
                    "{{\"jsonrpc\":\"2.0\",\"method\":\"chat.streaming\",\"params\":{{\"token\":\"{}\",\"phase\":\"responding\"}}}}\n",
                    ch
                );
                stream.write_all(msg.as_bytes()).await.unwrap();
            }

            // Small delay to ensure notifications arrive separately
            tokio::time::sleep(Duration::from_millis(50)).await;

            // Send final result
            let result = r#"{"jsonrpc":"2.0","id":1,"result":{"task":"test","result":"Hello","success":true,"steps":[],"elapsed_secs":1}}"#;
            stream.write_all(format!("{}\n", result).as_bytes()).await.unwrap();
            stream.flush().await.unwrap();
        });

        // Client: use TaskStream to connect and receive messages
        let sock = sock_path.clone();
        let client_handle = tokio::spawn(async move {
            let mut stream = TaskStream::submit(&sock, "test task").await.unwrap();

            let mut streaming_msgs = vec![];
            let mut result_msgs = vec![];
            let mut all_msgs = vec![];

            loop {
                tokio::select! {
                    msg = stream.rx.recv() => {
                        match msg {
                            Some(ws_msg) => {
                                let msg_type = ws_msg.msg_type.clone();
                                all_msgs.push(ws_msg.clone());
                                match msg_type.as_str() {
                                    "streaming" => streaming_msgs.push(ws_msg),
                                    "result" => { result_msgs.push(ws_msg); break; }
                                    "error" => break,
                                    _ => {}
                                }
                            }
                            None => break,
                        }
                    }
                    _ = tokio::time::sleep(Duration::from_secs(5)) => {
                        break;
                    }
                }
            }

            (streaming_msgs, result_msgs, all_msgs)
        });

        let _ = server_handle.await;
        let (streaming, results, all) = client_handle.await.unwrap();

        let _ = std::fs::remove_file(&sock_path);

        println!("All messages: {}", all.len());
        println!("Streaming: {}", streaming.len());
        println!("Results: {}", results.len());

        for (i, msg) in all.iter().enumerate() {
            println!("  [{}] type={} token={:?}",
                i, msg.msg_type,
                msg.streaming_token.as_ref().map(|t| &t.token)
            );
        }

        assert!(streaming.len() > 0, "Expected streaming notifications, got {} msgs: {:?}", all.len(), all.iter().map(|m| m.msg_type.clone()).collect::<Vec<_>>());
        assert!(results.len() > 0, "Expected result message");

        // Verify streaming came before result
        let first_streaming_idx = all.iter().position(|m| m.msg_type == "streaming").unwrap();
        let result_idx = all.iter().position(|m| m.msg_type == "result").unwrap();
        assert!(first_streaming_idx < result_idx, "Streaming must arrive before result");

        // Verify content
        let tokens: String = streaming.iter()
            .filter_map(|m| m.streaming_token.as_ref())
            .map(|t| t.token.clone())
            .collect();
        assert_eq!(tokens, "Hello");
    }

    #[tokio::test]
    async fn test_task_stream_receives_step_notifications() {
        let sock_path = format!("/tmp/test_task_stream_step_{}.sock", std::process::id());
        let _ = std::fs::remove_file(&sock_path);

        let listener = spawn_fake_server(&sock_path).await;

        let server_handle = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut buf = vec![0u8; 1024];
            let _ = stream.read(&mut buf).await;

            // Send step notification
            let step = r#"{"jsonrpc":"2.0","method":"chat.progress","params":{"phase":"executing","action":"click","step":1}}"#;
            stream.write_all(format!("{}\n", step).as_bytes()).await.unwrap();

            tokio::time::sleep(Duration::from_millis(50)).await;

            // Send result
            let result = r#"{"jsonrpc":"2.0","id":1,"result":{"task":"t","result":"done","success":true,"steps":[],"elapsed_secs":1}}"#;
            stream.write_all(format!("{}\n", result).as_bytes()).await.unwrap();
            stream.flush().await.unwrap();
        });

        let sock = sock_path.clone();
        let client_handle = tokio::spawn(async move {
            let mut stream = TaskStream::submit(&sock, "test").await.unwrap();
            let mut step_msgs = vec![];
            let mut all_msgs = vec![];

            loop {
                tokio::select! {
                    msg = stream.rx.recv() => {
                        match msg {
                            Some(ws_msg) => {
                                let mt = ws_msg.msg_type.clone();
                                all_msgs.push(ws_msg.clone());
                                if mt == "step" { step_msgs.push(ws_msg); }
                                if mt == "result" { break; }
                                if mt == "error" { break; }
                            }
                            None => break,
                        }
                    }
                    _ = tokio::time::sleep(Duration::from_secs(5)) => break,
                }
            }
            (step_msgs, all_msgs)
        });

        let _ = server_handle.await;
        let (steps, all) = client_handle.await.unwrap();
        let _ = std::fs::remove_file(&sock_path);

        assert!(steps.len() > 0, "Expected step notifications, got: {:?}", all.iter().map(|m| m.msg_type.clone()).collect::<Vec<_>>());
        assert_eq!(steps[0].event.as_ref().unwrap().action, "click");
    }
}

/// A streaming task execution via Unix socket JSON-RPC.
///
/// Opens a Unix socket to the Python backend, sends a single
/// `agent.run` JSON-RPC request, then reads newline-delimited
/// responses.  Notifications (no ``id``) are forwarded as progress
/// events.  The final response (with matching ``id``) completes
/// the stream.
pub struct TaskStream {
    pub rx: tokio::sync::mpsc::UnboundedReceiver<WsMessage>,
    cancel_tx: Option<tokio::sync::oneshot::Sender<()>>,
    handle: tokio::task::JoinHandle<()>,
}

impl Drop for TaskStream {
    fn drop(&mut self) {
        if let Some(tx) = self.cancel_tx.take() {
            let _ = tx.send(());
        }
        self.handle.abort();
    }
}

impl TaskStream {
    pub async fn submit(socket_path: &str, task: &str) -> BridgeResult<Self> {
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "agent.run",
            "params": {"task": task},
        });

        let stream = UnixStream::connect(socket_path)
            .await
            .map_err(|e| BridgeError::Connection(e.to_string()))?;
        let (reader, mut writer) = stream.into_split();

        // Send the request
        let mut raw = serde_json::to_string(&request)?;
        raw.push('\n');
        writer
            .write_all(raw.as_bytes())
            .await
            .map_err(|e| BridgeError::Connection(e.to_string()))?;
        writer.shutdown().await.map_err(BridgeError::Io)?;

        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        let (cancel_tx, mut cancel_rx) = tokio::sync::oneshot::channel::<()>();
        let tx_clone = tx.clone();

        let handle = tokio::spawn(async move {
            let mut buf_reader = BufReader::new(reader);
            let mut line = String::new();

            loop {
                let read_result = tokio::time::timeout(
                    std::time::Duration::from_secs(120),
                    buf_reader.read_line(&mut line),
                ).await;

                tokio::select! {
                    _ = &mut cancel_rx => {
                        break;
                    }
                    result = async { read_result } => {
                        match result {
                            Ok(Ok(0)) => break,
                            Ok(Ok(_)) => {
                                let trimmed = line.trim().to_string();
                                line.clear();
                                if trimmed.is_empty() {
                                    continue;
                                }
                                match serde_json::from_str::<serde_json::Value>(&trimmed) {
                                    Ok(msg) => {
                                        if msg.get("id").is_none() {
                                            let method = msg.get("method").and_then(|m| m.as_str()).unwrap_or("");
                                            let params = msg.get("params").cloned().unwrap_or(serde_json::Value::Null);

                                            if method == "chat.streaming" {
                                                let token = params.get("token").and_then(|t| t.as_str()).unwrap_or("");
                                                let phase = params.get("phase").and_then(|p| p.as_str()).unwrap_or("responding");
                                                let ws_msg = WsMessage {
                                                    msg_type: "streaming".into(),
                                                    data: None,
                                                    event: None,
                                                    result: None,
                                                    error: None,
                                                    streaming_token: Some(StreamingToken {
                                                        token: token.into(),
                                                        phase: phase.into(),
                                                    }),
                                                };
                                                let _ = tx_clone.send(ws_msg);
                                            } else {
                                                let ws_msg = WsMessage {
                                                    msg_type: "step".into(),
                                                    data: None,
                                                    event: Some(StepEvent {
                                                        phase: params.get("phase").and_then(|p| p.as_str()).unwrap_or("").into(),
                                                        action: params.get("action").and_then(|a| a.as_str()).unwrap_or("").into(),
                                                        detail: params.get("detail").and_then(|d| d.as_str()).map(String::from),
                                                        url: None,
                                                        screenshot: None,
                                                    }),
                                                    result: None,
                                                    error: None,
                                                    streaming_token: None,
                                                };
                                                let _ = tx_clone.send(ws_msg);
                                            }
                                            continue;
                                        }

                                        if let Some(err) = msg.get("error") {
                                            let ws_msg = WsMessage {
                                                msg_type: "error".into(),
                                                data: None,
                                                event: None,
                                                result: None,
                                                error: Some(
                                                    err["message"].as_str().unwrap_or("RPC error").into()
                                                ),
                                                streaming_token: None,
                                            };
                                            let _ = tx_clone.send(ws_msg);
                                        } else if let Some(result_val) = msg.get("result") {
                                            match serde_json::from_value::<AgentResult>(result_val.clone()) {
                                                Ok(agent_result) => {
                                                    let ws_msg = WsMessage {
                                                        msg_type: "result".into(),
                                                        data: None,
                                                        event: None,
                                                        result: Some(agent_result),
                                                        error: None,
                                                        streaming_token: None,
                                                    };
                                                    let _ = tx_clone.send(ws_msg);
                                                }
                                                Err(e) => {
                                                    let ws_msg = WsMessage {
                                                        msg_type: "error".into(),
                                                        data: None,
                                                        event: None,
                                                        result: None,
                                                        error: Some(format!("Result parse error: {}", e)),
                                                        streaming_token: None,
                                                    };
                                                    let _ = tx_clone.send(ws_msg);
                                                }
                                            }
                                        }
                                        break;
                                    }
                                    Err(e) => {
                                        let ws_msg = WsMessage {
                                            msg_type: "error".into(),
                                            data: None,
                                            event: None,
                                            result: None,
                                            error: Some(format!("JSON parse: {}", e)),
                                            streaming_token: None,
                                        };
                                        let _ = tx_clone.send(ws_msg);
                                        break;
                                    }
                                }
                            }
                            Ok(Err(e)) => {
                                let ws_msg = WsMessage {
                                    msg_type: "error".into(),
                                    data: None,
                                    event: None,
                                    result: None,
                                    error: Some(e.to_string()),
                                    streaming_token: None,
                                };
                                let _ = tx_clone.send(ws_msg);
                                break;
                            }
                            Err(_) => {
                                let ws_msg = WsMessage {
                                    msg_type: "error".into(),
                                    data: None,
                                    event: None,
                                    result: None,
                                    error: Some("Read timeout (120s)".into()),
                                    streaming_token: None,
                                };
                                let _ = tx_clone.send(ws_msg);
                                break;
                            }
                        }
                    }
                }
            }
        });

        Ok(Self {
            rx,
            cancel_tx: Some(cancel_tx),
            handle,
        })
    }

    pub fn cancel(mut self) {
        if let Some(tx) = self.cancel_tx.take() {
            let _ = tx.send(());
        }
        self.handle.abort();
    }
}
