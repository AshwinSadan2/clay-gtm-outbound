# OpenAI API reference (for the AI-written `{OPENER}`)

Source: https://developers.openai.com/api/docs and its guides (text, models, reasoning, structured outputs,
rate limits, pricing), read 2026-10-28. Key: `OPENAI_API_KEY` in `.env`. Every model below was confirmed
available to our key with a free `GET /v1/models` call on 2026-10-28.

## The call

- **Use the Responses API**, not Chat Completions (OpenAI's recommendation; reasoning models do better on it).
- `POST https://api.openai.com/v1/responses`, headers `Authorization: Bearer <key>` + `Content-Type: application/json`.
- Body:
  - `model`: pin an exact ID (below).
  - `instructions`: the fixed rules (system-level). They outrank `input` and apply to this request only.
  - `input`: a string, or role-tagged messages (`developer` > `user`).
  - `reasoning: {"effort": "..."}`.
  - `text.format`: for structured output (below).
  - `max_output_tokens`.
- Response: an `output` array that can hold several items (reasoning + message). The text is in items of
  `type: "message"` → `content[]` of `type: "output_text"` → `text`. `output_text` is an SDK convenience only,
  not in the raw JSON. Token counts are in `usage`; reasoning tokens are in
  `usage.output_tokens_details.reasoning_tokens`.
- `v1/prompts` (stored prompt objects) shuts down 2026-11-30: keep prompts in our own code/docs.

## Structured output

```json
"text": {"format": {"type": "json_schema", "name": "opener", "strict": true,
  "schema": {"type": "object", "properties": {...}, "required": [...all fields...], "additionalProperties": false}}}
```

- Every property is listed in `required`, and every object sets `additionalProperties: false`.
- A refusal comes back as a content item with `type: "refusal"` (it may not match the schema): handle it separately.

## Reasoning effort

- **Values:** `none` · `minimal` · `low` · `medium` · `high` · `xhigh` · `max`. Each model supports a subset.
- **Default:** `medium`.
- **Per-model limits:** GPT-6 Astra rejects `none` (400). GPT-6.1 Sol rejects `none` and `minimal`.
  Terra and Luna accept `none` to `max`.
- **Billing:** reasoning tokens are billed as output and are invisible.
- **`max_output_tokens`** caps reasoning + visible text together. If it is hit: `status: "incomplete"`,
  `incomplete_details.reason: "max_output_tokens"`, possibly with **no text but still billed**.
  Always check `status` and that text exists.

## Models (per 1M tokens: input / cached input / output, standard)

| Model ID | For | Price |
|---|---|---|
| `gpt-6-astra` | Most capable, hardest work | $10 / $1 / $50 |
| `gpt-6.1-sol` | Near-Astra, complex work | $2 / $0.10 / $10 |
| `gpt-6.1-terra` | Fast, efficient, "natural writing" | $1 / $0.05 / $5 |
| `gpt-6-luna` | Cost-sensitive high volume | $0.10 / $0.01 / $0.50 |
| `gpt-5.6-terra` / `gpt-5.6-luna` | Previous generation | $2/$12 · $0.20/$1.20 |

- Context window: 1.05M tokens. Max output: 128K.
- Batch API and Flex are about 50% cheaper but asynchronous (Batch runs up to a day). For under 200 rows,
  a synchronous run is simpler.

## Limits and errors

- **Limits:** per organisation and project, on RPM / TPM / RPD / TPD, whichever runs out first.
  - Build tier (from $5 of purchases): 5,000 RPM, 1M TPM (Luna: 2M).
  - Response headers: `x-ratelimit-remaining-requests` / `-tokens`, `Retry-After`.
- **Retry only:**
  - `429` (`rate_limit_error` / `slow_down`)
  - `500`
  - `503` (`server_is_overloaded`)

  Wait for `Retry-After` if present (plus jitter), otherwise use exponential backoff, with capped attempts.
- **Never retry** a `429` whose `error.code` is `insufficient_quota`, or one from a hard spend limit. That is
  billing, not speed: log it and stop the run.
- **Never log** the request headers (the key travels in `Authorization`).
