---
name: venice-embeddings
description: Call POST /embeddings on Venice. Covers request shape (input, model, encoding_format, dimensions, user), OpenAI compatibility, response compression (gzip/br), and practical usage for retrieval, clustering, and RAG.
---

# Venice Embeddings

`POST /api/v1/embeddings` returns vector embeddings for strings. It's OpenAI-compatible: the request and response match `https://api.openai.com/v1/embeddings` closely enough that the OpenAI SDK works out of the box with `baseURL: "https://api.venice.ai/api/v1"`.

## Use when

- You're building retrieval / RAG / similarity search.
- You need text clustering, classification, deduplication, or reranking.
- You want Venice's "no-training, no-retention" stance on inference inputs — embeddings are generated and returned; the API does not publish E2EE semantics on `/embeddings` the way it does on selected chat models.

Text-only. For image/multimodal signals, either run images through a vision chat model and embed the description, or pick a multimodal-capable embedding model from `GET /models?type=embedding` (the catalog changes; inspect `model_spec` on each row).

## Minimal request

```bash
curl https://api.venice.ai/api/v1/embeddings \
  -H "Authorization: Bearer $VENICE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept-Encoding: gzip, br" \
  -d '{
    "model": "text-embedding-bge-m3",
    "input": "Why is the sky blue?"
  }'
```

```json
{
  "object": "list",
  "model": "text-embedding-bge-m3",
  "data": [
    { "object": "embedding", "index": 0, "embedding": [0.0023, -0.0093, 0.0158, ...] }
  ],
  "usage": { "prompt_tokens": 8, "total_tokens": 8 }
}
```

## Request schema

| Field | Type | Notes |
|---|---|---|
| `model` | string | **Required.** Model ID from `GET /models?type=embedding`. |
| `input` | string \| string[] \| number[] \| number[][] | **Required.** Single string, array of strings (≤ 2048 entries), or pre-tokenized arrays. |
| `encoding_format` | `"float"` \| `"base64"` | Default `"float"`. Use `"base64"` for ~4× payload shrinkage; decode client-side. |
| `dimensions` | integer | Optional. Truncate output dimensions. Only meaningful when the model's `model_spec.supportsCustomDimensions === true` — behavior on non-supporting models is model-dependent; test a small call before relying on it. |
| `user` | string | Accepted for OpenAI compat. Discarded by Venice. |

`input` max tokens per string is capped at the model's `model_spec.maxInputTokens` (typically 8192). Batch arrays are capped at **2048 items**. Venice returns one embedding per element, in order, with matching `index`.

## Response headers & compression

Request `Accept-Encoding: gzip, br`. The response will include `Content-Encoding` accordingly. For long batches this matters — vectors are large.

For x402 auth, `X-Balance-Remaining` reports your remaining USDC credits.

## Using the OpenAI SDK

```ts
import OpenAI from 'openai'

const client = new OpenAI({
  apiKey: process.env.VENICE_API_KEY,
  baseURL: 'https://api.venice.ai/api/v1',
})

const res = await client.embeddings.create({
  model: 'text-embedding-bge-m3',
  input: ['first doc', 'second doc'],
})

const vec0 = res.data[0].embedding
```

## Batch-embedding pattern

```ts
async function embedBatch(texts: string[], batchSize = 64) {
  const out: number[][] = []
  for (let i = 0; i < texts.length; i += batchSize) {
    const slice = texts.slice(i, i + batchSize)
    const res = await client.embeddings.create({
      model: 'text-embedding-bge-m3',
      input: slice,
      encoding_format: 'float',
    })
    for (const row of res.data) out[i + row.index] = row.embedding
  }
  return out
}
```

- Keep batches ≤ model context limit total tokens.
- On `429`, back off exponentially and halve the batch — see [`venice-errors`](../venice-errors/SKILL.md).

## Choosing a model

Query `GET /models?type=embedding` for the current catalog. Each entry exposes:

- `model_spec.embeddingDimensions` — native output dimension (e.g. 1024 for BGE-M3).
- `model_spec.maxInputTokens` — max tokens per input string.
- `model_spec.supportsCustomDimensions` — whether `dimensions` can truncate the output.
- `model_spec.pricing.input.usd` / `.diem` — cost per **million** input tokens.

Built-in options include `text-embedding-bge-m3`, `text-embedding-bge-en-icl`, `text-embedding-qwen3-8b`, `text-embedding-qwen3-0-6b`, `text-embedding-multilingual-e5-large-instruct`, `text-embedding-3-small`, `text-embedding-3-large`, `gemini-embedding-2-preview`, `text-embedding-nemotron-embed-vl-1b-v2`.

Always pin the model ID — cosine distances are **not** comparable across different embedding models.

## Error handling

| Code | Meaning |
|---|---|
| `400` | Validation error. Check `details` in the response for the exact field. |
| `401` | Auth / Pro-only model. |
| `402` | Insufficient balance. Bearer → `INSUFFICIENT_BALANCE`. x402 → structured `PAYMENT_REQUIRED`. |
| `415` | Wrong `Content-Type` — must be `application/json`. |
| `429` | Rate limited. |
| `500` | Inference failed; retry with jitter. |
| `503` | Model at capacity; retry later. |

## Gotchas

- `dimensions` is only meaningful when `model_spec.supportsCustomDimensions === true`. Behavior on other models is model-dependent — test with a small request before relying on it.
- `input` must not be empty; Venice rejects empty strings with `400`.
- Whether the returned vectors are L2-normalized depends on the model — verify with `Math.hypot(...v) ≈ 1` before assuming.
- For RAG, store `model` alongside the vector so you can re-embed on upgrade.
