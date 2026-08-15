# Model catalog

Cloud AI exposes six configured models. Ollama ADE separately lists every installed local
model and checks its live `vision` capability.

| UI name | API model ID | Input/1M | Output/1M | Required environment variable |
|---|---|---:|---:|---|
| Grok 4.6 | `grok-4.6` | $2.00 | $6.00 | `XAI_API_KEY` |
| GPT-5.6 Luna | `gpt-5.6-luna` | $0.20 | $1.20 | `OPENAI_API_KEY` |
| Gemini 3.5 Flash-Lite | `gemini-3.5-flash-lite` | $0.30 | $2.50 | `GOOGLE_API_KEY` |
| Gemini 3.7 Flash | `gemini-3.7-flash` | $0.75 | $3.75 | `GOOGLE_API_KEY` |
| Claude Sonnet 5 | `claude-sonnet-5` | $2.00 | $10.00 | `ANTHROPIC_API_KEY` |
| Agnes 2.5 Flash | `agnes-2.5-flash` | Free | Free | `AGNES_API_KEY` |

`GPT-5.6 Luna` is the default. `OPENAI_BASE_URL` is an optional OpenAI-only override; it
does not change the endpoints for other providers.

Agnes uses its current configured $0 rate, while still recording tokens and pricing
entitlement. Paperplane sends private visual inputs inline as PNG data URLs, enabling Parse
and enhancement without publishing uploaded images. Paperplane requests schema-shaped tool
calls and accepts Agnes's JSON content fallback. It normalizes equivalent 0–1000 boxes and
omitted nullable chunk fields before strict local validation and one bounded correction attempt. Missing, out-of-range, or reversed geometry therefore
cannot silently reach the annotated-PDF renderer.

## Ollama models

`OLLAMA_BASE_URL` defaults to `http://127.0.0.1:11434`. Paperplane queries `/api/tags` and
`/api/show`; non-vision models remain visible but cannot start Parse. The initial benchmark
and calibration targets are `glm-ocr:latest` and
`AuditAid/PaddleOCR-VL-1.6-0.9B:latest`. Other installed vision models run with raw,
explicitly uncalibrated confidence until a matching profile is checked in.

GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR use a layout-first path. The local
`PaddlePaddle/PP-DocLayoutV3_safetensors` detector finds page regions on CPU, then the
selected Ollama model receives each crop with its native OCR prompt. Detector boxes ground
the assembled blocks; RapidOCR is used only for final word-box alignment.

DeepSeek-OCR retries an empty text crop once with a strict transcription-only prompt and
retries transient transport, malformed-response, HTTP 408/429, and server failures once
after 500 ms. It skips an isolated exhausted crop with a page warning, but stops after
three consecutive exhausted regions. Empty detected figures remain grounded. GLM-OCR and
PaddleOCR-VL keep their existing prompt and failure behavior.

## Gemini credentials and 3.7 pricing

Paperplane uses `GOOGLE_API_KEY` for both Gemini models. The launcher, ignored `.env`, and
Streamlit secrets accept that canonical name. Existing `GEMINI_API_KEY` configurations
remain a fallback only when `GOOGLE_API_KEY` is absent.

Gemini 3.7 Flash uses the supplied promotional standard rate of $0.75/1M input tokens and
$3.75/1M output tokens through December 31, 2026. GPT-5.6 Terra is not in the supported
catalog, so its supplied rate is not used.

## Cost estimates

After a parse, the UI displays provider-reported input and output tokens and calculates:

```text
input cost + output cost
= input tokens × input rate / 1,000,000
+ output tokens × output rate / 1,000,000
```

GPT-5.6 Luna cached input tokens use the supplied $0.02/1M rate. Paperplane applies the
listed synchronous base rates only. It does not infer Batch API discounts, Grok
fast/long-context surcharges, Claude Batch discounts, or other account-specific
adjustments. The displayed amount is an estimate; the provider invoice is authoritative.

The supplied non-default rates remain informational: Claude Sonnet 5 Batch is 50% off;
Gemini 3.5 Flash-Lite Batch is $0.15/$1.25; Grok 4.6 fast mode or prompts above 200k tokens
use $4/$12. Paperplane does not invoke Batch or Grok fast mode, and aggregate document usage
cannot determine whether one individual request crossed a long-context threshold, so these
modifiers are not applied to the UI estimate.

The Cost page accumulates provider-reported usage for successful parses in the current
browser session and groups it by actual model. Ollama-plus-cloud enhancement is split into
separate local and cloud rows. Free and local models retain their token counts at $0 API
cost; **New parse** keeps the ledger, while **Stop and clear** or session end removes it.

## Official references

- [xAI models](https://docs.x.ai/developers/models)
- [OpenAI latest models](https://developers.openai.com/api/docs/guides/latest-model)
- [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Agnes AI model catalog](https://github.com/AgnesAI-Labs/AgnesAI-Models/blob/main/MODEL_CATALOG.md)
- [Ollama API](https://docs.ollama.com/api/introduction)

Provider credentials are read at runtime from Windows user environment variables, `.env`,
or local Streamlit secrets. Never commit real keys.
