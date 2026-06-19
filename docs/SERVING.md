# Serving mcp-logseq over HTTP

> **Advanced deployment guide.** For local single-user use you need none of this — the default **stdio** transport (covered in the [README](../README.md)) is spawned by your client as a subprocess. This guide covers running `mcp-logseq` as a networked **HTTP** service for sandboxed or remote clients: the server-side security model, the per-profile multi-instance pattern, the separate vector sync writer, and TLS.

For the namespace/tag access-control env vars themselves (`LOGSEQ_INCLUDE_NAMESPACES`, `LOGSEQ_EXCLUDE_NAMESPACES`, `LOGSEQ_EXCLUDE_TAGS`), see [Privacy & Access Control](../README.md#-privacy--access-control) in the README — they apply to every transport.

## 🔒 Security model

When serving multiple clients over HTTP, isolation rests on a few guarantees:

- **ACL is enforced server-side, before any bytes leave the process.** Blocked pages are filtered out of listings/search and denied on direct read/write — a client never receives content it isn't scoped to. Block-level results from `search` and `query` are resolved back to their owning page and filtered too.
- **Bearer auth.** Every HTTP request must carry `Authorization: Bearer <MCP_HTTP_AUTH_TOKEN>`; unauthenticated requests are rejected.
- **Loopback binding.** Default `--host 127.0.0.1` (loopback). Non-loopback binds are refused over plain HTTP — they require TLS (`--tls-cert`/`--tls-key`) or an explicit `--insecure` (see [Step 3](#step-3--encrypt-anything-past-loopback)).
- **Process-boundary isolation.** Multi-instance means one profile's config (token, namespace scope, excluded tags) is never loaded by another process.
- **Read tools** enforce namespace allow/deny *or* tag exclusion. **Write tools** enforce namespace gating plus tag-on-write checks against the existing page, so a write can't slip into a blocked namespace or onto an excluded page.
- **Tag matching is case-SENSITIVE; namespace matching is case-INSENSITIVE.** Namespaces match regardless of case (`work` matches `Work/Projects`), but `LOGSEQ_EXCLUDE_TAGS` / `vector.exclude_tags` must match the **stored** tag casing exactly. Logseq typically stores tags lowercased, so `LOGSEQ_EXCLUDE_TAGS=Secret` will **not** exclude a page tagged `secret`. Match the casing as stored, or a page you meant to hide stays visible.

## 🌐 Serving over HTTP (multi-profile)

By default the server speaks **stdio** — the local client spawns it as a subprocess. For serving sandboxed or remote clients (each one only allowed to see a slice of your graph), the server can also run as a long-lived **HTTP** process:

```bash
mcp-logseq --transport http --host 127.0.0.1 --port 12320
```

- `--transport {stdio,http}` — default `stdio`.
- `--host` — default `127.0.0.1` (loopback). Binding a non-loopback host over plain HTTP is **refused** unless you supply TLS or pass `--insecure`; see [Step 3 — encrypt anything past loopback](#step-3--encrypt-anything-past-loopback).
- `--port` — default `12320`.
- `--read-only` — unregisters the 8 write tools (see [Security model](#-security-model)); read tools and the vector tools remain.
- `--tls-cert` / `--tls-key` — serve native HTTPS; see [Step 3](#step-3--encrypt-anything-past-loopback).

HTTP mode **requires** `MCP_HTTP_AUTH_TOKEN`; the server exits if it is missing. Clients authenticate with `Authorization: Bearer <token>` and target the MCP endpoint at **`/mcp`**. (A bare POST to `/mcp` issues a `307` redirect to `/mcp/`; point clients at `/mcp` and follow redirects, or use `/mcp/` directly.)

### Step 1 — one instance per profile

A **profile** is one shared data config file + a per-process env block (namespace/tags/token) + its own port. Run **one instance per profile**. Every instance loads the *same* data config file (graph path, vector `db_path`, embedder); what differs is the per-process env block — and that env block **is** the profile.

```bash
# "journal-assistant" — reads your diary and reflects back, but can never edit it.
# Whole-instance read-only: no write tools at all.
LOGSEQ_CONFIG_FILE=~/.logseq/data.json \
LOGSEQ_INCLUDE_NAMESPACES=Journal \
MCP_HTTP_AUTH_TOKEN=$JOURNAL_TOKEN \
mcp-logseq --transport http --port 12320 --read-only

# "work" — full read/write within Work/, and explicitly no diary access.
LOGSEQ_CONFIG_FILE=~/.logseq/data.json \
LOGSEQ_INCLUDE_NAMESPACES=Work \
LOGSEQ_EXCLUDE_NAMESPACES=Journal \
MCP_HTTP_AUTH_TOKEN=$WORK_TOKEN \
mcp-logseq --transport http --port 12321

# "personal" — broad read/write, but credentials stay invisible.
LOGSEQ_CONFIG_FILE=~/.logseq/data.json \
LOGSEQ_EXCLUDE_TAGS=keys,secret \
MCP_HTTP_AUTH_TOKEN=$PERSONAL_TOKEN \
mcp-logseq --transport http --port 12322
```

The `LOGSEQ_CONFIG_FILE` is identical across all three instances; the per-process env block is what makes each one a distinct profile. Because each instance is its own process, one profile's env (token, namespace scope, excluded tags) is never loaded by another — isolation is the process boundary.

### Step 2 — the separate sync writer

The vector DB has exactly **one** writer: a dedicated `logseq-sync` process deployed **outside** every MCP instance. It indexes the whole graph under a single global policy — `vector.exclude_tags` should hold only the secrets/never-store tags. Per-profile differentiation is purely *query-time* on the reader instances above; the index itself is shared.

```bash
# Continuous writer (launchd / systemd unit), owns the DB — same shared data file:
LOGSEQ_CONFIG_FILE=~/.logseq/data.json logseq-sync --watch

# Or scheduled one-shot (cron / launchd StartInterval):
LOGSEQ_CONFIG_FILE=~/.logseq/data.json logseq-sync --once
```

`logseq-sync` reads **no ACL env** — only the `vector` block and graph path from the data file. (`--rebuild` drops and re-indexes from scratch; `--status` prints a staleness report.) The reader profiles open the same `db_path` read-only and never run sync: the MCP `sync_vector_db` tool is inert and simply points operators at this external writer.

### Step 3 — encrypt anything past loopback

> **The bearer token and all content travel as plaintext over plain HTTP.** Anything reachable beyond loopback must be encrypted — either native TLS on the instance, or a TLS-terminating reverse proxy in front of a loopback-bound instance.

To enforce this, the server **refuses to bind a non-loopback host over plain HTTP**. A host outside the loopback set (`127.0.0.1`, `localhost`, `::1`) requires one of:

- **Native TLS** — pass `--tls-cert` and `--tls-key`. TLS is allowed on any host.
- **A TLS-terminating reverse proxy** in front, with the instance bound to a loopback address (recommended — see below).
- **`--insecure`** — consciously accept an unencrypted non-loopback bind. Only sane on a trusted network or already behind a TLS proxy.

Loopback binds over plain HTTP need no opt-in; that remains the default.

**Native TLS** wraps the instance directly in HTTPS (uvicorn's `ssl_certfile`/`ssl_keyfile`):

```bash
mcp-logseq --transport http --port 12320 \
  --tls-cert /path/cert.pem --tls-key /path/key.pem
```

`--tls-cert` and `--tls-key` must be supplied **together** (both or neither, else the server exits), and both files **must exist** at startup. For the certificate itself: use [`mkcert`](https://github.com/FiloSottile/mkcert) or a self-signed cert for host-internal/dev use, or [Let's Encrypt](https://letsencrypt.org/) when the instance is reachable on a public DNS name. The per-profile env blocks from [Step 1](#step-1--one-instance-per-profile) are unchanged — TLS just changes the wire, not the profile.

**Recommended production path — reverse proxy with automatic HTTPS.** Bind the instance to loopback and let a proxy such as [Caddy](https://caddyserver.com/) terminate TLS (it obtains and renews Let's Encrypt certificates automatically):

```caddyfile
# Caddyfile — automatic HTTPS in front of a loopback-bound instance
logseq.example.com {
    reverse_proxy 127.0.0.1:12320
}
```

With the instance running as `mcp-logseq --transport http --port 12320` (loopback default, no `--insecure` needed), clients reach it over HTTPS at `logseq.example.com` while the unencrypted hop stays inside the host.
