# Paperplane V2 architecture

V2 is the active stateless API described in [ARCHITECTURE.md](ARCHITECTURE.md).

Its stable public surface is synchronous Parse and Extract. Parse returns reading-order
Markdown, a document/page/block hierarchy, normalized coordinates, line and cell evidence,
warnings, and usage metadata. Fast, Balanced, and Audit aliases select bounded verification
policies while preserving the response shape.

There are no V2 job resources. Clients that need queues, retention, retries across process
restarts, or shared history should add those concerns outside Paperplane and store the
returned contract in their own system.
