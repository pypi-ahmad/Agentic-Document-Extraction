# Model catalog

Cloud AI exposes six configured models. Ollama ADE separately lists every installed local
model and checks its live `vision` capability.

| UI name | API model ID | Input/1M | Output/1M | Required environment variable |
|---|---|---:|---:|---|
| Grok 4.6 | `grok-4.6` | $2.00 | $6.00 | `XAI_API_KEY` |
| GPT-6 Sol | `gpt-6-sol` | $2.00 | $10.00 | `OPENAI_API_KEY` |
| Gemini 3.5 Flash-Lite | `gemini-3.5-flash-lite` | $0.30 | $2.50 | `GOOGLE_API_KEY` |
| Gemini 3.7 Flash | `gemini-3.7-flash` | $0.75 | $3.75 | `GOOGLE_API_KEY` |
| Claude Sonnet 5 | `claude-sonnet-5` | $2.00 | $10.00 | `ANTHROPIC_API_KEY` |
| Agnes 2.5 Flash | `agnes-2.5-flash` | Free | Free | `AGNES_API_KEY` |

`GPT-6 Sol` is the default. `OPENAI_BASE_URL` is an optional OpenAI-only override; it
does not change the endpoints for other providers. GPT-6 Sol uses medium reasoning for
every request, including drafts, verification, repairs, figure descriptions, and cloud
enhancement. Fast, Balanced, and Audit still control image resolution, verification scope,
and repair limits; other providers keep their existing reasoning policies.

If GPT-6 Sol's content filter interrupts schema output, Paperplane retries once. For forms with
personal or health data, the retry asks the model to replace those values with
`[CONTENT OMITTED]` while keeping their labels and the rest of the page. A successful retry adds
`content_filter_retry_used` to the page warnings. A second interruption stops the cloud request
instead of reporting malformed JSON. For a PDF with a native text layer, Paperplane then returns
locally extracted text with
`openai_content_filter_native_pdf_fallback`. For scans and images, it uses the bundled local OCR
and adds `openai_content_filter_local_ocr_fallback`. If neither path finds text, Paperplane keeps
the content-filter error.

For scan pages with at least 500 model-output tokens, Paperplane compares output volume with
locally observed OCR words. If GPT-6 Sol returns more than four times the observed word count,
Paperplane replaces the overgenerated page with grounded local text lines and adds
`model_output_overgeneration_local_text_fallback`.

Agnes uses its current configured $0 rate, while still recording tokens and pricing
entitlement. Paperplane sends private visual inputs inline as PNG data URLs, enabling Parse
and enhancement without publishing uploaded images. Paperplane requests schema-shaped tool
calls and accepts Agnes's JSON content fallback. It normalizes equivalent 0-1000 boxes and
omitted nullable chunk fields before strict local validation and one bounded correction attempt. Missing, out-of-range, or reversed geometry therefore
cannot silently reach the annotated-PDF renderer.

All model-facing prompts are Markdown files in `paperplane/prompts/`. Python code loads those
files and supplies only runtime values such as document context, quality findings, and candidate
text. Update the Markdown source when changing extraction behavior; do not embed prompts in code.

Table cells remain separate grounded child chunks in structured output. Page Markdown renders the
parent HTML table and omits its child-cell Markdown, so each value appears once.

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
$3.75/1M output tokens through December 31, 2026.

## Cost estimates

After a parse, the UI displays provider-reported usage and estimates cost with `Decimal`.
GPT-6 Sol uses these standard rates per million tokens:

| Token category | USD/1M |
|---|---:|
| Ordinary input | $2.00 |
| Cached input reads | $0.20 |
| Cache writes | $2.50 |
| Output | $10.00 |

```text
ordinary input = total input - cached input reads - cache writes
cost = (ordinary input × 2.00 + cached input reads × 0.20
        + cache writes × 2.50 + output × 10.00) / 1,000,000
```

Cache writes are part of total input, so they are charged once at the cache-write rate.
For example, 1,000 input tokens including 200 cached reads and 300 writes, plus 100 output
tokens, cost $0.00279. Both the Parse page and session Cost page include cache writes.
Providers without a configured cache-write rate retain their existing cost calculation.

Paperplane applies synchronous short-context base rates only. For GPT-6 Sol, requests
above 272K input tokens have higher rates, but aggregate document usage cannot identify
which individual request crossed that threshold. Long-context, Batch, Flex, Fast, regional,
and account-specific adjustments are not applied. The displayed amount is an estimate;
the provider invoice is authoritative.

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
- [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol)
- [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI prompt caching and usage accounting](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Agnes AI model catalog](https://github.com/AgnesAI-Labs/AgnesAI-Models/blob/main/MODEL_CATALOG.md)
- [Ollama API](https://docs.ollama.com/api/introduction)

Provider credentials are read at runtime from Windows user environment variables, `.env`,
or local Streamlit secrets. Never commit real keys.
