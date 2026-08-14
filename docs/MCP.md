# MCP integration

The active application does not mount an MCP server. Agents can call the documented HTTP
API directly: multipart `POST /v2/parse`, JSON `POST /v2/extract`, and the invoice contract
preset.

An MCP adapter can be built as a thin external wrapper around those endpoints. It should
pass only server-side credentials, enforce the same upload limits, and return the response
without inventing job or persistence semantics.
