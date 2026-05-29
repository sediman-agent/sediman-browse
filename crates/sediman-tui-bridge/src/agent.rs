use futures_util::{SinkExt, StreamExt};
use tokio_tungstenite::{connect_async, tungstenite::Message};
use url::Url;

use crate::types::*;

pub struct TaskStream {
    pub rx: tokio::sync::mpsc::UnboundedReceiver<WsMessage>,
    cancel_tx: tokio::sync::oneshot::Sender<()>,
    #[allow(dead_code)]
    handle: tokio::task::JoinHandle<()>,
}

impl TaskStream {
    pub async fn submit(base_url: &str, task: &str) -> crate::client::BridgeResult<Self> {
        let ws_url = Url::parse(base_url)?
            .join("/ws/chat")?;

        let (ws, _) = connect_async(ws_url.as_str()).await?;
        let (mut write, read) = ws.split();

        let init_msg = serde_json::json!({
            "type": "submit",
            "task": task,
        });
        write
            .send(Message::Text(init_msg.to_string().into()))
            .await?;

        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        let (cancel_tx, mut cancel_rx) = tokio::sync::oneshot::channel::<()>();
        let tx_clone = tx.clone();

        let handle = tokio::spawn(async move {
            let mut read = read;
            loop {
                tokio::select! {
                    msg = read.next() => {
                        match msg {
                            Some(Ok(Message::Text(text))) => {
                                if let Ok(ws_msg) = serde_json::from_str::<WsMessage>(&text) {
                                    let _ = tx_clone.send(ws_msg);
                                    if text.contains("\"type\":\"result\"") {
                                        break;
                                    }
                                }
                            }
                            Some(Ok(Message::Close(_))) => break,
                            Some(Err(e)) => {
                                let _ = tx_clone.send(WsMessage {
                                    msg_type: "error".to_string(),
                                    data: None,
                                    event: None,
                                    result: None,
                                    error: Some(e.to_string()),
                                });
                                break;
                            }
                            None => break,
                            _ => {}
                        }
                    }
                    _ = &mut cancel_rx => {
                        let _ = write.send(Message::Close(None)).await;
                        break;
                    }
                }
            }
        });

        Ok(Self {
            rx,
            cancel_tx,
            handle,
        })
    }

    pub fn cancel(self) {
        let _ = self.cancel_tx.send(());
    }
}
