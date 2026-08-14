# Migration guide: stateless V2

This version removes the persistence and background-worker layer.

## Breaking changes

- Use `POST /v2/parse` instead of job creation, polling, event, cancellation, and artifact
  routes.
- The parse response is returned when processing completes.
- Saved schema, review, curation, evaluation-run, batch, and reprocessing APIs are removed.
- Persistence connection settings and migration commands are removed.
- The frontend displays only the current local upload and response.

## Client migration

Replace create-and-poll logic with one multipart request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/v2/parse `
  -F "file=@sample.pdf" `
  -F "model=paperplane-ade-latest" `
  -o result.json
```

If your product needs durable history or async execution, queue this request in your own
platform and retain `result.json` there. Old local application data is not read by this
version and can be archived or removed according to your retention policy.
