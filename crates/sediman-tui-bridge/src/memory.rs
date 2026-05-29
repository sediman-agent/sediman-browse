use crate::client::{ApiClient, BridgeResult};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct ChangelogEntry {
    pub action: String,
    pub target: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    pub timestamp: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ChangelogResult {
    changes: Vec<ChangelogEntry>,
}

impl ApiClient {
    pub async fn memory_add(&self, target: &str, content: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "memory.add",
            serde_json::json!({"target": target, "content": content}),
        )
        .await?;
        Ok(())
    }

    pub async fn memory_remove(&self, target: &str, content: &str) -> BridgeResult<()> {
        self.call::<serde_json::Value>(
            "memory.remove",
            serde_json::json!({"target": target, "content": content}),
        )
        .await?;
        Ok(())
    }

    pub async fn memory_search(
        &self,
        query: &str,
        limit: usize,
    ) -> BridgeResult<Vec<String>> {
        let result: serde_json::Value = self
            .call(
                "memory.search",
                serde_json::json!({"query": query, "limit": limit}),
            )
            .await?;
        let results = result
            .get("results")
            .and_then(|r| r.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        Ok(results)
    }

    pub async fn memory_changelog(
        &self,
        target: Option<&str>,
        limit: usize,
    ) -> BridgeResult<Vec<ChangelogEntry>> {
        let result: ChangelogResult = self
            .call(
                "memory.changelog",
                serde_json::json!({
                    "target": target,
                    "limit": limit,
                }),
            )
            .await?;
        Ok(result.changes)
    }

    pub async fn remember(&self, text: &str) -> BridgeResult<()> {
        self.memory_add("memory", text).await
    }
}
