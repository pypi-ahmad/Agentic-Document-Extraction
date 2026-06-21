# ADR 0004 — Security headers and SSRF guard are secure-by-default

## Status

Accepted (2026-06-22).

## Context

The v0.2.x service was local-first and trust-on-first-use. The
v0.3.0 modernization wants to remain usable as a local service
while making the path to a networked deployment obvious and safe.

## Decision

The defaults for the security controls are:

- **Magic-byte upload validation** rejects any file whose bytes
  do not match the declared extension. There is no opt-out.
- **`OLLAMA_BASE_URL`** must be a loopback or local address. An
  explicit `OLLAMA_ALLOW_PRIVATE_HOSTS=true` opt-out is required
  to talk to a remote host.
- **Security headers** are sent on every response, unconditionally.
  Layered CSP / HSTS lives at the reverse proxy.
- **Rate limiting** is in-process by default at 60 req/min/IP
  with the global SlowAPI middleware. Disabled when `TESTING=1`.

## Rationale

- **Defense in depth.** Even a local service ends up behind a
  reverse proxy once the user wants HTTPS; every layer should
  default to the safe choice.
- **No silent footguns.** A user pointing `OLLAMA_BASE_URL` at an
  attacker-controlled host today is a real risk; the default
  behaviour is to refuse and log.
- **Opt-out is auditable.** When someone needs to disable a check
  (e.g. to point at a remote Ollama in development), the env var
  is the single toggle and it is grep-able in logs.

## Consequences

- The reverse proxy / TLS terminator is still required for
  production (HSTS, CSP, frame-ancestors).
- The rate limiter is in-process. Multi-replica deployments need
  a Redis-backed limiter; the SlowAPI config supports this with
  a small adapter that we have not yet built.
- `OLLAMA_ALLOW_PRIVATE_HOSTS=true` should be set explicitly in
  the env, not hidden in a default. Operators see what they are
  opting into.
