# Limitations

- Parsing is synchronous. Large documents can exceed reverse-proxy or client timeouts.
- Results are not retained by the server. Refreshing the browser discards the current result.
- There are no background jobs, resume, cancellation, shared history, or multi-worker leases.
- OpenAI access is required for parsing; model latency, quotas, and availability apply.
- Extraction has a provider seam but must be configured by a deployment before `/v2/extract`
  is available.
- Supported inputs are PDF, PNG, JPEG, WebP, and TIFF; office documents and spreadsheets
  are not accepted directly.
- Visual parsing can still misread tiny, rotated, handwritten, damaged, or unusual content.
- Grounding helps review evidence but does not guarantee factual correctness.
- The default deployment is local and single-user. Internet exposure requires TLS, an API
  key, appropriate CORS origins, monitoring, and infrastructure-level controls.
