use std::time::Duration;

use crossterm::event::{Event, EventStream, KeyEventKind};
use futures::StreamExt;
use tokio::sync::mpsc;

use super::message::AppEvent;

pub struct EventLoop {
    tick_interval: Duration,
    event_tx: mpsc::UnboundedSender<AppEvent>,
    event_rx: mpsc::UnboundedReceiver<AppEvent>,
}

impl EventLoop {
    pub fn new(tick_hz: f64) -> Self {
        let (event_tx, event_rx) = mpsc::unbounded_channel();
        Self {
            tick_interval: Duration::from_secs_f64(1.0 / tick_hz),
            event_tx,
            event_rx,
        }
    }

    pub fn sender(&self) -> mpsc::UnboundedSender<AppEvent> {
        self.event_tx.clone()
    }

    pub async fn run<F, Fut>(mut self, mut on_event: F)
    where
        F: FnMut(AppEvent) -> Fut,
        Fut: std::future::Future<Output = ()>,
    {
        let mut reader = EventStream::new();
        let mut ticker = tokio::time::interval(self.tick_interval);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

        loop {
            tokio::select! {
                _ = ticker.tick() => {
                    on_event(AppEvent::Tick).await;
                }
                Some(Ok(event)) = reader.next() => {
                    match event {
                        Event::Key(key) if key.kind == KeyEventKind::Press => {
                            on_event(AppEvent::Key(key)).await;
                        }
                        Event::Resize(w, h) => {
                            on_event(AppEvent::Resize(w, h)).await;
                        }
                        _ => {}
                    }
                }
                Some(msg) = self.event_rx.recv() => {
                    on_event(msg).await;
                }
                else => break,
            }
        }
    }
}
