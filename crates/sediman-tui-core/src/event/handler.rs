use std::time::Duration;

use crossterm::event::{Event, EventStream, KeyEventKind};
use futures::StreamExt;
use tokio::sync::mpsc;

use super::message::AppEvent;

pub struct EventLoop {
    tick_interval: Duration,
    out_tx: mpsc::UnboundedSender<AppEvent>,
}

impl EventLoop {
    pub fn new(tick_hz: f64, out_tx: mpsc::UnboundedSender<AppEvent>) -> Self {
        Self {
            tick_interval: Duration::from_secs_f64(1.0 / tick_hz),
            out_tx,
        }
    }

    pub fn sender(&self) -> mpsc::UnboundedSender<AppEvent> {
        self.out_tx.clone()
    }

    pub async fn run(self) {
        let mut reader = EventStream::new();
        let mut ticker = tokio::time::interval(self.tick_interval);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let tx = self.out_tx;

        loop {
            let event = tokio::select! {
                _ = ticker.tick() => Some(AppEvent::Tick),
                Some(Ok(event)) = reader.next() => {
                    match event {
                        Event::Key(key) if key.kind == KeyEventKind::Press => {
                            Some(AppEvent::Key(key))
                        }
                        Event::Mouse(mouse) => {
                            Some(AppEvent::Mouse(mouse))
                        }
                        Event::Resize(w, h) => {
                            Some(AppEvent::Resize(w, h))
                        }
                        Event::Paste(text) => {
                            Some(AppEvent::Paste(text))
                        }
                        _ => None,
                    }
                }
                else => None,
            };

            if let Some(ev) = event {
                if tx.send(ev).is_err() {
                    break;
                }
            }
        }
    }
}
