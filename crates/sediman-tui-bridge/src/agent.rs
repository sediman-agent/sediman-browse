use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;

use crate::client::{BridgeError, BridgeResult};
use crate::types::*;

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
        writer.shutdown().await.map_err(|e| BridgeError::Io(e))?;

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
                                            if let Some(params) = msg.get("params") {
                                                let ws_msg = WsMessage {
                                                    msg_type: "step".into(),
                                                    data: None,
                                                    event: Some(StepEvent {
                                                        phase: params["phase"].as_str().unwrap_or("").into(),
                                                        action: params["action"].as_str().unwrap_or("").into(),
                                                        detail: params["detail"].as_str().map(String::from),
                                                        url: None,
                                                        screenshot: None,
                                                    }),
                                                    result: None,
                                                    error: None,
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
                                            };
                                            let _ = tx_clone.send(ws_msg);
                                        } else if let Some(result_val) = msg.get("result") {
                                            if let Ok(agent_result) = serde_json::from_value::<AgentResult>(result_val.clone()) {
                                                let ws_msg = WsMessage {
                                                    msg_type: "result".into(),
                                                    data: None,
                                                    event: None,
                                                    result: Some(agent_result),
                                                    error: None,
                                                };
                                                let _ = tx_clone.send(ws_msg);
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
