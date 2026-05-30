---
name: venice-characters
description: Discover and use Venice public characters (persona-driven system prompts with a bound model). Covers GET /characters (search/filter/sort), /characters/{slug}, /characters/{slug}/reviews, the Character schema, and how to apply a character via venice_parameters.character_slug in chat completions.
---

# Venice Characters

Characters are **published personas** on Venice — each one bundles a system prompt, a backing model, optional web access, and metadata (tags, ratings, adult flag). You apply a character to any chat by passing its `slug` via `venice_parameters.character_slug`.

## Use when

- You want to build a character-selection UI or discovery surface.
- You want to ship an app with a preset persona (e.g. a coding coach, a philosopher, a game NPC).
- You need to adapt a character's underlying model (`modelId`) to match your capability requirements.

Three endpoints, all under `Preview` (API may change):

| Endpoint | Purpose |
|---|---|
| `GET /characters` | Browse/search/filter the catalog. |
| `GET /characters/{slug}` | Fetch one character. |
| `GET /characters/{slug}/reviews` | Paginated public reviews. |

All three endpoints require authentication (Bearer API key or x402 SIWE) — see [`venice-auth`](../venice-auth/SKILL.md). There is no unauthenticated public endpoint.

## `GET /characters`

```bash
curl "https://api.venice.ai/api/v1/characters?search=philosopher&sortBy=highestRating&limit=20" \
  -H "Authorization: Bearer $VENICE_API_KEY"
```

### Query parameters

| Param | Type | Notes |
|---|---|---|
| `search` | string, ≤ 200 | Name, description, or tag match. Hashtag (`#Philosophy`) supported. |
| `categories` | string[], ≤ 20 | Repeat or comma-separate. Character categories (`roleplay`, `philosophy`, …). |
| `tags` | string[], ≤ 20 | Repeat or comma-separate. |
| `modelId` | string[], ≤ 20 | Filter by backing model (`zai-org-glm-5-1`, `kimi-k2-6`, `minimax-m25`, …). |
| `isAdult` | `"true"` / `"false"` | Adult-content flag. |
| `isPro` | `"true"` / `"false"` | Require a Pro model. |
| `isWebEnabled` | `"true"` / `"false"` | Allow web access. |
| `sortBy` | enum | `featured`, `highestRating`, `highlyRated`, `highlyRatedAndRecent`, `imports`, `mostRecent`, `ratingCount`. |
| `sortOrder` | `asc` / `desc` | Default `desc`. |
| `limit` | 1–100 | Default 50. |
| `offset` | integer | Pagination offset. |

### Character object

| Field | Notes |
|---|---|
| `id` | UUID. |
| `slug` | **Use this as `character_slug` in chat**. URL-safe. |
| `name`, `description`, `photoUrl`, `shareUrl` | Presentation. |
| `author` | Anonymized short ID. |
| `tags[]`, `featured`, `adult`, `webEnabled` | Metadata. |
| `modelId` | Backing Venice model ID (e.g. `venice-uncensored`). |
| `stats` | `{averageRating, imports, ratingCount, ratingSum, userRating}`. |
| `createdAt`, `updatedAt` | ISO-8601. |

## `GET /characters/{slug}`

```bash
curl "https://api.venice.ai/api/v1/characters/alan-watts" \
  -H "Authorization: Bearer $VENICE_API_KEY"
```

Returns the same object shape above, wrapped as `{ object: "character", data: { ... } }`. `404` if the slug is unknown or unpublished.

## `GET /characters/{slug}/reviews`

```bash
curl "https://api.venice.ai/api/v1/characters/alan-watts/reviews?page=1&pageSize=20" \
  -H "Authorization: Bearer $VENICE_API_KEY"
```

Response:

```json
{
  "object": "list",
  "pagination": {"page": 1, "pageSize": 20, "total": 87, "totalPages": 5},
  "summary": {"averageRating": 4.7, "totalReviews": 87},
  "data": [
    {
      "id": "...", "characterId": "...", "createdAt": "...",
      "rating": 5, "message": "Thoughtful and grounded.",
      "locale": "en", "username": "product_user_42", "isOwner": false,
      "userAvatarUrl": "https://cdn.venice.ai/..."
    }
  ]
}
```

Also sets `x-pagination-*` response headers (`limit`, `page`, `total`, `total-pages`).

## Using a character in chat

### Minimal

```json
{
  "model": "zai-org-glm-5-1",
  "venice_parameters": { "character_slug": "alan-watts" },
  "messages": [
    { "role": "user", "content": "What's the nature of mind?" }
  ]
}
```

The character's system prompt is injected by Venice. `include_venice_system_prompt` defaults to `true` and adds Venice's curated prelude — set it to `false` for a pure character voice.

### Ignoring the character's backing model

You can override the model — Venice will still apply the character's system prompt:

```json
{
  "model": "kimi-k2-6",
  "venice_parameters": {
    "character_slug": "alan-watts",
    "include_venice_system_prompt": false
  },
  "messages": [...]
}
```

Useful when the character's `modelId` lacks a capability (e.g. function calling, vision) that your app needs.

### Via feature suffix on the `model` string

```json
{ "model": "zai-org-glm-5-1:character_slug=alan-watts", "messages": [...] }
```

Useful when the client library (OpenAI SDK, LangChain, etc.) can't add `venice_parameters`. See [`venice-chat`](../venice-chat/SKILL.md#model-feature-suffixes) for the full suffix grammar.

## Patterns

### Character picker UI

```ts
const res = await fetch(`${base}/characters?sortBy=featured&limit=50`, {
  headers: { Authorization: `Bearer ${process.env.VENICE_API_KEY}` },
})
const { data } = await res.json()
// show data[].photoUrl, data[].name, data[].stats.averageRating
// pick a slug, then pass into chat:
await chat({
  model: pickedModelId,
  venice_parameters: { character_slug: pickedSlug },
  messages: [...]
})
```

### Filter for family-friendly + web

```bash
/characters?isAdult=false&isWebEnabled=true&sortBy=highlyRatedAndRecent
```

### Search by hashtag

```bash
/characters?search=%23Philosophy
```

## Errors

| Code | Meaning |
|---|---|
| `400` | Bad query params (e.g. `limit > 100`). |
| `401` | Missing or invalid auth. All three endpoints require a Bearer key or SIWE header. |
| `404` | Unknown slug. |
| `500` | Transient. Retry. |

## Gotchas

- This is **Preview API** — response shape may change.
- Slugs are the **public ID** on the character's page (`venice.ai/c/<slug>`). They are **not** the internal `id` UUID.
- `photoUrl` / `shareUrl` / `userAvatarUrl` can be `null` — don't assume they exist.
- Character `modelId` may be gated (Pro, beta). If you always reuse the character's `modelId`, handle `401 "only available to Pro users"` gracefully.
- Adult-flagged characters are omitted unless `isAdult=true` is explicitly passed.
