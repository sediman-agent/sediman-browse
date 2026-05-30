---
name: venice-image-edit
description: Transform existing images with Venice. Covers POST /image/edit (prompt-driven single-image edit), /image/multi-edit (compose 1-3 images), /image/upscale (2-4x upscale + enhance), and /image/background-remove. Accepts base64, file upload, or HTTPS URL.
---

# Venice Image Editing

Four endpoints, all operating on existing images:

| Endpoint | Purpose |
|---|---|
| `POST /image/edit` | Transform one image with a text prompt. |
| `POST /image/multi-edit` | Composite / layer 2–3 images with a single prompt. Also has a `multipart/form-data` variant. |
| `POST /image/upscale` | Upscale 2–4× and/or enhance quality. |
| `POST /image/background-remove` | Produce a transparent cutout. |

For text-to-image generation, see [`venice-image-generate`](../venice-image-generate/SKILL.md).

## Shared rules

- Input image accepts **base64 string**, **file upload** (multipart for `/image/multi-edit`), or **HTTPS URL** (for edit + multi-edit + background-remove).
- File size < **25 MB**. Image dimensions must be between **65,536** (256×256 equivalent) and **33,177,600** pixels (~5,761×5,761). Upscale caps at **16,777,216** pixels after scaling.
- HTTPS URLs must be publicly reachable from Venice's network.
- All four endpoints return the edited image as **binary `image/png`** — there is no `return_binary` field on edit / multi-edit / upscale / background-remove (that flag only exists on `/image/generate`).

## `/image/edit`

Edit one image with a short, descriptive prompt.

```bash
curl https://api.venice.ai/api/v1/image/edit \
  -H "Authorization: Bearer $VENICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-edit",
    "prompt": "Change the color of the sky to a sunrise",
    "image": "iVBORw0KGgoAAAANSUhEUg...",
    "aspect_ratio": "16:9",
    "safe_mode": true
  }'
```

| Field | Notes |
|---|---|
| `model` | Default `qwen-edit`. See `GET /models?type=inpaint` for edit-capable models. `modelId` is accepted for backwards compatibility but deprecated on `/image/edit` — prefer `model`. |
| `prompt` | Required, ≤ 32 768 chars (usually 1500 is plenty). Short & specific works best. |
| `image` | Required. Base64 string, file upload, or `https://` URL. |
| `aspect_ratio` | Optional: `auto`, `1:1`, `3:2`, `16:9`, `21:9`, `9:16`, `2:3`, `3:4`, `4:5`. Supported values vary per model — check `constraints` on `GET /models`. |
| `safe_mode` | Default `true`; blurs adult content. |

Good prompts: *"remove the tree"*, *"add sunglasses to the cat"*, *"make the sky a vivid orange sunrise"*.

## `/image/multi-edit`

Combine up to 3 images into one with a prompt. The **first image is the base**; the rest are layers / masks / references.

> **Field name:** `/image/multi-edit` takes **`modelId`**, not `model`. This is the only image endpoint that uses `modelId` as the primary field name.

### JSON (base64 or URLs)

```json
{
  "modelId": "qwen-edit",
  "prompt": "Place the person from image 2 onto the beach in image 1",
  "images": [
    "https://example.com/beach.jpg",
    "data:image/png;base64,iVBOR..."
  ],
  "safe_mode": true
}
```

### Multipart (file upload)

```
POST /image/multi-edit
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="modelId"

qwen-edit
--boundary
Content-Disposition: form-data; name="prompt"

Place the person from image 2 onto the beach in image 1
--boundary
Content-Disposition: form-data; name="images"; filename="base.jpg"
Content-Type: image/jpeg

<bytes>
--boundary
Content-Disposition: form-data; name="images"; filename="subject.png"
Content-Type: image/png

<bytes>
--boundary--
```

| Field | Notes |
|---|---|
| `modelId` | **Required field name** (multi-edit does not accept `model`). Default `qwen-edit`. |
| `prompt` | Required, ≤ 32 768 chars. |
| `images` | Required. 1–3 items. JSON variant accepts base64 or HTTPS URLs; multipart variant accepts raw file parts. |
| `safe_mode` | Default `true`. |

## `/image/upscale`

Upscale by 1–4×, optionally running Venice's enhancer. Set `enhance: true` + `scale: 1` to enhance without scaling.

```bash
curl https://api.venice.ai/api/v1/image/upscale \
  -H "Authorization: Bearer $VENICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "image": "iVBORw0KGgo...",
    "scale": 2,
    "enhance": true,
    "enhanceCreativity": 0.5,
    "enhancePrompt": "gold",
    "replication": 0.35
  }'
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `image` | base64 or file | — | Required. Must be ≥ 65 536 px² to start. |
| `scale` | 1..4 | 2 | `1` requires `enhance: true`. `4` on large images auto-scales down to stay within 16 MP. |
| `enhance` | bool / `"true"` / `"false"` | `"false"` | Turn on Venice's enhancer. Required when `scale === 1`. |
| `enhanceCreativity` | 0..1 | 0.5 | Higher = more AI reinterpretation. `1` essentially produces a new image. |
| `enhancePrompt` | string, ≤ 1500 | — | Short stylistic cue: *"gold"*, *"marble"*, *"angry, menacing"*. |
| `replication` | 0..1 | 0.35 | Preserve original lines/noise. Higher = less plastic / less AI-feel. |

Response is the upscaled image as binary (`image/png` typically).

## `/image/background-remove`

Produce a transparent PNG cutout.

```bash
# With base64
curl https://api.venice.ai/api/v1/image/background-remove \
  -H "Authorization: Bearer $VENICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"image": "iVBOR..."}'

# With a URL
curl https://api.venice.ai/api/v1/image/background-remove \
  -H "Authorization: Bearer $VENICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/photo.jpg"}'
```

Send **either** `image` (base64 / file) **or** `image_url`. Response is `image/png` with alpha channel.

## Error behavior (all four endpoints)

| Code | Cause |
|---|---|
| `400` | Bad params — image dims out of range, file too large, unknown model, unsupported aspect ratio for the model, content-policy refusal. |
| `401` | Auth failed. (Pro-gating on these paths surfaces as `400` / `402` depending on condition.) |
| `402` | Insufficient balance. Bearer: plain `{ "error": "Insufficient balance" }`. x402: `PAYMENT_REQUIRED` body + `PAYMENT-REQUIRED` header. |
| `415` | Wrong `Content-Type` (e.g. JSON sent to a multipart endpoint, or vice versa). |
| `429` | Rate limited. |
| `500` / `503` | Inference / capacity issue — retry with jitter. |

(`413` and `422` are **not** documented for these image paths in the OpenAPI spec — a `413` from the platform may still appear if you exceed ingress limits, but treat `400` / `415` as the primary failure surface.)

## Gotchas

- `/image/multi-edit` `images[]` explicitly accepts `data:image/...;base64,...` URLs or plain base64. For `/image/edit` and `/image/upscale`, send base64 as a plain string unless the docs say otherwise — if your client adds a `data:` prefix and you get a `400`, strip it.
- For multipart `/image/multi-edit`, the field name is `images` and you send **multiple parts with the same field name** — order matters (base first).
- Field-name asymmetry: `/image/edit` prefers **`model`** (`modelId` is a deprecated alias). `/image/multi-edit` accepts **only `modelId`**. Get the name right per endpoint — sending the wrong one is a `400`.
- `/image/upscale` with `scale=4` on a large input is silently clamped to stay under 16 MP.
- `safe_mode: true` can blur otherwise valid inputs if the source image trips content classifiers; switch to `false` (and handle the legal/ToS consequences yourself) when you control the input.
- `/image/background-remove` takes **either** `image` **or** `image_url`, not both.
