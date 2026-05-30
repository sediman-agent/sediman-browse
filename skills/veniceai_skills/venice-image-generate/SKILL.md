---
name: venice-image-generate
description: Generate images with Venice. Covers POST /image/generate (Venice-native), POST /images/generations (OpenAI-compatible), GET /image/styles (style presets), request fields (prompt, dimensions, cfg_scale, seed, variants, style_preset, aspect_ratio, resolution, safe_mode, watermark), and response formats.
---

# Venice Image Generation

Two text-to-image endpoints:

1. **`POST /api/v1/image/generate`** — Venice-native, full control (negative prompts, CFG, seed, up to 4 variants).
2. **`POST /api/v1/images/generations`** — OpenAI-compatible, fewer knobs but drop-in for the OpenAI SDK.

Plus:

- **`GET /api/v1/image/styles`** — list of style preset names for `style_preset`.

For editing / upscaling / multi-image / background removal, see [`venice-image-edit`](../venice-image-edit/SKILL.md).

## Use when

- You need to generate images from text prompts.
- You need multiple variants in one call.
- You're porting from OpenAI's `images.generate` and want a zero-change SDK swap.
- You want to browse style presets before committing to one.

## `/image/generate` — Venice-native

### Request

```bash
curl https://api.venice.ai/api/v1/image/generate \
  -H "Authorization: Bearer $VENICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "z-image-turbo",
    "prompt": "A beautiful sunset over a mountain range",
    "width": 1024,
    "height": 1024,
    "cfg_scale": 7.5,
    "steps": 8,
    "seed": 123456789,
    "variants": 1,
    "format": "webp",
    "style_preset": "3D Model",
    "safe_mode": true
  }'
```

### Fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `model` | string | — | **Required.** Image model ID. `GET /models?type=image`. |
| `prompt` | string | — | **Required.** Max `promptCharacterLimit` from the model's `model_spec.constraints` (typically 1500–7500). |
| `negative_prompt` | string | — | Describe what *not* to show. Same character cap as prompt. |
| `width`, `height` | int | 1024, 1024 | ≤ 1280 each. Must be divisible by `constraints.widthHeightDivisor` on the model's `model_spec`. |
| `aspect_ratio` | string | — | `"1:1"`, `"16:9"`, `"9:16"`, … — used by models like Nano Banana instead of width/height. |
| `resolution` | string | — | `"1K"`, `"2K"`, `"4K"` — used by resolution-driven models. |
| `cfg_scale` | number | model default | 0 < x ≤ 20. Higher = more prompt adherence. |
| `steps` | int | 8 | Inference steps. Some models ignore it (e.g. Turbo). |
| `seed` | int | 0 | `-999999999..999999999`. Use `0`/omit for random. |
| `variants` | int | 1 | 1–4. Only if `return_binary: false`. |
| `lora_strength` | int | — | 0–100 when model uses Loras. |
| `style_preset` | string | — | Value from `GET /image/styles`. |
| `format` | `"webp"`/`"png"`/`"jpeg"` | `webp` | Response image format. |
| `return_binary` | bool | `false` | `true` → binary `image/*` response; `false` → JSON with base64. |
| `embed_exif_metadata` | bool | `false` | Embed prompt info in EXIF. |
| `hide_watermark` | bool | `false` | Venice may still watermark certain content. |
| `safe_mode` | bool | `true` | Blurs adult content. |
| `enable_web_search` | bool | `false` | Only some models. Charges extra. |
| `inpaint` | — | — | **Deprecated** since May 19 2025. A new inpaint API is forthcoming. |

### Response (JSON, `return_binary: false`)

```json
{
  "id": "...",
  "images": ["<base64>", "<base64>"],
  "timing": {...},
  "request": {...}
}
```

With `return_binary: true`, response is raw `image/webp` (or `png`/`jpeg`) with matching `Content-Type`.

## `/images/generations` — OpenAI-compatible

Use this if you're already on the OpenAI SDK. Field names match `openai.images.generate()`.

```ts
import OpenAI from 'openai'

const client = new OpenAI({
  apiKey: process.env.VENICE_API_KEY,
  baseURL: 'https://api.venice.ai/api/v1',
})

const res = await client.images.generate({
  model: 'z-image-turbo',
  prompt: 'A beautiful sunset over mountain ranges',
  size: '1024x1024',
  response_format: 'b64_json',
})

const b64 = res.data[0].b64_json
```

### Mapped fields

| Field | Values | Notes |
|---|---|---|
| `model` | string, default `"default"` | Unknown model IDs fall back to Venice's default. |
| `prompt` | string, ≤ 1500 chars | Required. |
| `size` | `auto`, `256x256`, `512x512`, `1024x1024`, `1536x1024`, `1024x1536`, `1792x1024`, `1024x1792` | — |
| `output_format` | `jpeg` / `png` / `webp` | Defaults to `png`. |
| `response_format` | `b64_json` / `url` | `url` returns a `data:` URL (not a hosted URL). |
| `moderation` | `auto` (safe mode on) / `low` (safe mode off) | — |
| `n` | `1` | Venice only supports a single image per call here. |
| `quality`, `style` (`vivid`/`natural`), `background`, `output_compression`, `user` | — | Accepted for OpenAI compat, not used by Venice. |

If you need `variants`, `seed`, `negative_prompt`, `cfg_scale`, or `style_preset`, switch to `/image/generate`.

## `/image/styles` — list presets

```bash
curl https://api.venice.ai/api/v1/image/styles \
  -H "Authorization: Bearer $VENICE_API_KEY"
```

Returns a list of `styles[]`, each with a `name` you can pass to `style_preset`. Cache this — it's small and stable.

## Choosing a model

```bash
curl "https://api.venice.ai/api/v1/models?type=image" \
  -H "Authorization: Bearer $VENICE_API_KEY"
```

Inspect per-model `model_spec`:

- `constraints.widthHeightDivisor` — `width` and `height` must both be divisible by this.
- `constraints.aspectRatios[]` + `defaultAspectRatio` — if present, the model supports aspect-ratio-driven sizing.
- `constraints.resolutions[]` + `defaultResolution` — if present, the model supports `resolution` (`1K`/`2K`/`4K`).
- `constraints.steps.{default,max}` — step bounds (some models ignore `steps` entirely).
- `constraints.promptCharacterLimit` — max prompt length (also applies to `negative_prompt`).
- `pricing.generation.usd` — flat USD per image, or `pricing.resolutions[].usd` for resolution-tiered models.

Pick a model that matches the **feature + size combo** you plan to use.

## Common patterns

### Fixed-seed A/B test

```json
{"model": "z-image-turbo", "prompt": "...", "seed": 42, "variants": 4}
```

### Aspect-ratio-driven model (Nano Banana family)

```json
{"model": "nano-banana-2", "prompt": "...", "aspect_ratio": "16:9", "resolution": "2K"}
```

(Other nano-banana variants: `nano-banana-pro`. Always verify the current ID via `GET /models?type=image`.)

### Style preset + negative

```json
{
  "model": "z-image-turbo",
  "prompt": "a red sports car in a parking lot",
  "negative_prompt": "blurry, people, clouds",
  "style_preset": "3D Model"
}
```

### Stream binary to disk (Node)

```ts
const res = await fetch('https://api.venice.ai/api/v1/image/generate', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.VENICE_API_KEY}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ model: 'z-image-turbo', prompt: '...', return_binary: true }),
})
if (!res.ok) throw new Error(await res.text())
const buf = Buffer.from(await res.arrayBuffer())
await fs.writeFile('out.webp', buf)
```

## Errors

| Code | Meaning |
|---|---|
| `400` | Bad params (e.g. dimensions not divisible by `widthHeightDivisor`, prompt too long, `variants>1` with `return_binary`). |
| `401` | Auth or Pro-only model. |
| `402` | Insufficient balance. Bearer: plain `{ "error": "Insufficient balance" }`; x402: `PAYMENT_REQUIRED` body + `PAYMENT-REQUIRED` header. |
| `415` | Wrong `Content-Type` (send `application/json` for this endpoint). |
| `429` | Rate limited. |
| `500` / `503` | Inference or capacity issue — retry with jitter. |

(Content-policy violations on `/image/generate` come back as `400` with an error string, not `422` — the `422` shape is specific to audio generation paths.)

## Gotchas

- Each model picks one sizing idiom: either `width`/`height`, `aspect_ratio` + `resolution`, or (OpenAI-compat) `size`. Match the model's `constraints`.
- `variants > 1` requires `return_binary: false` (JSON with base64 array).
- `steps` is ignored by fast/turbo models; they hardcode step count internally.
- `hide_watermark: true` is advisory — Venice may still watermark content flagged by safety classifiers.
- Old `inpaint` field is deprecated; don't use it.
- For OpenAI-compat, `response_format: "url"` returns a **data URL**, not a hosted URL — plan for that if you're saving to storage.
