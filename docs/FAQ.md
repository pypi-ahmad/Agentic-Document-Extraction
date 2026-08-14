# FAQ

### Is Paperplane a Streamlit app?

No. The UI is Next.js/React and the API is FastAPI.

### Where are documents and results stored?

They are not retained by Paperplane. An upload is processed in one request and the browser
holds the latest result in memory. Save the returned JSON or Markdown if you need it later.

### Does it support background jobs or run history?

No. `/v2/parse` is synchronous. External systems may queue requests and save responses.

### Which inputs are accepted?

PDF, PNG, JPEG, WebP, and TIFF.

### Which model should I choose?

Use Balanced by default, Fast for clean high-volume documents, and Audit for dense or
high-risk layouts.

### Is OpenAI required?

Yes for the active V2 parser. `OPENAI_API_KEY` stays in the backend environment.

### Can I expose it on the internet?

Only after adding TLS, setting `API_KEY`, restricting CORS, choosing safe upload limits,
and applying infrastructure monitoring and abuse controls.
