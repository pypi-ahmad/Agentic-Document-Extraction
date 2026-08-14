# Model catalog

Cloud AI exposes six configured models. Ollama ADE separately lists every installed local
model and checks its live `vision` capability.

| UI name | API model ID | Input/1M | Output/1M | Required environment variable |
|---|---|---:|---:|---|
| Grok 4.6 | `grok-4.6` | $2.00 | $6.00 | `XAI_API_KEY` |
| GPT-5.6 Luna | `gpt-5.6-luna` | $0.20 | $1.20 | `OPENAI_API_KEY` |
| Gemini 3.5 Flash-Lite | `gemini-3.5-flash-lite` | $0.30 | $2.50 | `GEMINI_API_KEY` |
| Gemini 3.6 Flash | `gemini-3.6-flash` | $1.50 | $7.50 | `GEMINI_API_KEY` |
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

## Gemini 3.7 correction

Google's current official model catalog does not contain a model named “Gemini Flash
3.7” or an API ID named `gemini-3.7-flash`. The current stable Flash model is Gemini 3.6
Flash, with the API ID `gemini-3.6-flash`. Paperplane uses that real ID instead of sending
requests to an unverified model name.

The Gemini 3.6 estimate is derived from the supplied pricing statement that the proposed
$0.75/$3.75 Gemini 3.7 promotion is half the Gemini 3.6 rate. GPT-5.6 Terra is not in the
supported catalog, so its supplied rate is not used.

## Cost estimates

After a parse, the UI displays provider-reported input and output tokens and calculates:

```text
input cost + output cost
= input tokens × input rate / 1,000,000
+ output tokens × output rate / 1,000,000
```

GPT-5.6 Luna cached input tokens use the supplied $0.02/1M rate. Paperplane applies the
listed standard rates only. It does not infer Batch API discounts, promotional Gemini 3.7
pricing, Grok fast/long-context surcharges, or other account-specific adjustments. The
displayed amount is an estimate; the provider invoice is authoritative.

## Official references

- [xAI models](https://docs.x.ai/developers/models)
- [OpenAI latest models](https://developers.openai.com/api/docs/guides/latest-model)
- [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Agnes AI model catalog](https://github.com/AgnesAI-Labs/AgnesAI-Models/blob/main/MODEL_CATALOG.md)
- [Ollama API](https://docs.ollama.com/api/introduction)

Provider credentials are read at runtime from Windows user environment variables, `.env`,
or local Streamlit secrets. Never commit real keys.
