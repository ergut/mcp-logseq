# Embedder `api_key_env` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `vector.embedder` config source the provider API key from a named environment variable (`api_key_env`) so the secret never has to live in `config.json`.

**Architecture:** All logic lives in `load_vector_config()` in `src/mcp_logseq/config.py`. The variable named by `api_key_env` is resolved at config-load time and the value is stored in the existing `EmbedderConfig.api_key` field — the `EmbedderConfig` dataclass, `create_embedder`, and all vector runtime code are untouched.

**Tech Stack:** Python 3, stdlib only (`os.getenv`), pytest with `monkeypatch` for tests.

**Spec:** `docs/superpowers/specs/2026-07-11-embedder-api-key-env-design.md`

## Global Constraints

- `load_vector_config()` never raises — every config error logs a warning and returns `None` (vector tools disabled).
- The resolved API key value must never be logged.
- Existing plaintext `api_key` configs must keep working unchanged (back-compat).
- An env value that is unset or blank (empty/whitespace after `.strip()`) is treated as unset.
- Verification commands: `uv run pytest tests/unit/` and `uv run pyright` — both must pass before each commit.
- Work happens on branch `feat/embedder-api-key-env`.

---

### Task 1: `api_key_env` resolution in `load_vector_config`

**Files:**
- Modify: `src/mcp_logseq/config.py:126-127` (the `api_key_raw` / `api_key` lines)
- Test: `tests/unit/vector/test_config.py`

**Interfaces:**
- Consumes: `load_vector_config() -> VectorConfig | None` (existing), `EmbedderConfig.api_key: str | None` (existing).
- Produces: no new public names. Behavior contract for later tasks/docs: `vector.embedder.api_key_env` (optional str) names an env var; when that var is set and non-blank its value lands in `EmbedderConfig.api_key`, trumping plaintext `api_key`; unset var + plaintext → fallback with warning; unset var + no fallback → `load_vector_config()` returns `None`; invalid `api_key_env` type/empty → returns `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/vector/test_config.py`:

```python
def _openai_config(tmp_path, embedder_extra: dict) -> str:
    return _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "embedder": {"provider": "openai", **embedder_extra},
        },
    })


def test_api_key_env_reads_key_from_environment(monkeypatch, tmp_path):
    # Also proves api_key_env alone satisfies openai's requires-a-key check.
    path = _openai_config(tmp_path, {"api_key_env": "TEST_EMBED_KEY"})
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.setenv("TEST_EMBED_KEY", "env-secret")

    config = load_vector_config()

    assert config is not None
    assert config.embedder.api_key == "env-secret"


def test_api_key_env_takes_precedence_over_plaintext(monkeypatch, tmp_path):
    path = _openai_config(
        tmp_path, {"api_key_env": "TEST_EMBED_KEY", "api_key": "plain-key"}
    )
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.setenv("TEST_EMBED_KEY", "env-secret")

    config = load_vector_config()

    assert config is not None
    assert config.embedder.api_key == "env-secret"


def test_api_key_env_unset_falls_back_to_plaintext(monkeypatch, tmp_path):
    path = _openai_config(
        tmp_path, {"api_key_env": "TEST_EMBED_KEY", "api_key": "plain-key"}
    )
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.delenv("TEST_EMBED_KEY", raising=False)

    config = load_vector_config()

    assert config is not None
    assert config.embedder.api_key == "plain-key"


def test_api_key_env_unset_without_fallback_returns_none_openai(
    monkeypatch, tmp_path
):
    path = _openai_config(tmp_path, {"api_key_env": "TEST_EMBED_KEY"})
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.delenv("TEST_EMBED_KEY", raising=False)

    assert load_vector_config() is None


def test_api_key_env_unset_without_fallback_returns_none_openai_compatible(
    monkeypatch, tmp_path
):
    # openai-compatible allows keyless operation, but naming a variable
    # signals intent to authenticate — do not silently proceed without it.
    path = _write_config(tmp_path, {
        "logseq_graph_path": "/some/path",
        "vector": {
            "enabled": True,
            "embedder": {
                "provider": "openai-compatible",
                "model": "custom-embed-model",
                "base_url": "https://embeddings.example.com/v1",
                "api_key_env": "TEST_EMBED_KEY",
            },
        },
    })
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.delenv("TEST_EMBED_KEY", raising=False)

    assert load_vector_config() is None


def test_api_key_env_blank_value_treated_as_unset(monkeypatch, tmp_path):
    path = _openai_config(tmp_path, {"api_key_env": "TEST_EMBED_KEY"})
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.setenv("TEST_EMBED_KEY", "   ")

    assert load_vector_config() is None


@pytest.mark.parametrize("bad_name", [123, True, "", "   ", ["OPENAI_API_KEY"]])
def test_api_key_env_invalid_returns_none(monkeypatch, tmp_path, bad_name):
    # api_key is present, so failure proves the bad field is treated as a
    # config error rather than falling back to the plaintext key.
    path = _openai_config(
        tmp_path, {"api_key_env": bad_name, "api_key": "plain-key"}
    )
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)

    assert load_vector_config() is None


def test_plaintext_api_key_without_api_key_env_unchanged(monkeypatch, tmp_path):
    # Back-compat regression: no api_key_env means exactly today's behavior.
    path = _openai_config(tmp_path, {"api_key": "plain-key"})
    monkeypatch.setenv("LOGSEQ_CONFIG_FILE", path)
    monkeypatch.delenv("TEST_EMBED_KEY", raising=False)

    config = load_vector_config()

    assert config is not None
    assert config.embedder.api_key == "plain-key"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/unit/vector/test_config.py -v -k "api_key_env or plaintext_api_key"`

Expected: the precedence/fallback/none tests FAIL (config loads with the wrong key or loads when it should return `None`); `test_api_key_env_reads_key_from_environment` FAILS because `api_key_env` is ignored and openai has no `api_key`. `test_plaintext_api_key_without_api_key_env_unchanged` PASSES (it is the regression control).

- [ ] **Step 3: Implement resolution in `load_vector_config`**

In `src/mcp_logseq/config.py`, replace these two lines (currently 126–127):

```python
    api_key_raw = embedder_raw.get("api_key")
    api_key = str(api_key_raw).strip() if api_key_raw is not None else None
```

with:

```python
    api_key_raw = embedder_raw.get("api_key")
    api_key = str(api_key_raw).strip() if api_key_raw is not None else None
    api_key_env_raw = embedder_raw.get("api_key_env")
    if api_key_env_raw is not None:
        if not isinstance(api_key_env_raw, str) or not api_key_env_raw.strip():
            logger.warning("Embedder 'api_key_env' must be a non-empty string")
            return None
        env_name = api_key_env_raw.strip()
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            api_key = env_value
        elif api_key:
            logger.warning(
                f"Embedder 'api_key_env' variable '{env_name}' is unset — "
                "falling back to plaintext 'api_key' from config"
            )
        else:
            logger.warning(
                f"Embedder 'api_key_env' variable '{env_name}' is unset and no "
                f"'api_key' fallback is configured — set {env_name} to enable "
                "vector search"
            )
            return None
```

No other code changes: the existing `provider == "openai" and not api_key` check at line 136 already runs after this block and now sees the resolved key.

- [ ] **Step 4: Run the unit tests and type check**

Run: `uv run pytest tests/unit/ -v -k "config"` then `uv run pytest tests/unit/` then `uv run pyright`

Expected: all PASS, pyright reports 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/mcp_logseq/config.py tests/unit/vector/test_config.py
git commit -m "feat(vector): support api_key_env for embedder API key (#81)"
```

---

### Task 2: Documentation — `VECTOR_SEARCH.md` and `config.py` docstring

**Files:**
- Modify: `VECTOR_SEARCH.md:92-155` (provider examples, options table, chmod guidance)
- Modify: `src/mcp_logseq/config.py:1-31` (module docstring example)

**Interfaces:**
- Consumes: the behavior contract from Task 1 (`api_key_env` resolution semantics).
- Produces: documentation only, no code symbols.

- [ ] **Step 1: Update the OpenAI example in `VECTOR_SEARCH.md`**

Replace (currently lines 92–101):

```markdown
The example above uses Ollama. To use OpenAI instead, replace the `embedder`
block with:

```json
"embedder": {
  "provider": "openai",
  "model": "text-embedding-3-small",
  "api_key": "replace-with-your-api-key"
}
```
```

with:

```markdown
The example above uses Ollama. To use OpenAI instead, replace the `embedder`
block with:

```json
"embedder": {
  "provider": "openai",
  "model": "text-embedding-3-small",
  "api_key_env": "OPENAI_API_KEY"
}
```

`api_key_env` names an environment variable to read the API key from at
startup — the recommended way to supply a key, since it never touches disk.
Alternatively, set `"api_key": "your-key"` to embed the key in the config
file (see the file-permissions note below). When the named variable is set,
it takes precedence over `api_key`; if the variable is unset and no
`api_key` fallback is present, vector search is disabled with a warning
naming the missing variable.
```

- [ ] **Step 2: Update the dimensions and openai-compatible examples**

Replace the `dimensions` example block (currently lines 106–113):

```json
"embedder": {
  "provider": "openai",
  "model": "text-embedding-3-small",
  "api_key": "replace-with-your-api-key",
  "dimensions": 512
}
```

with:

```json
"embedder": {
  "provider": "openai",
  "model": "text-embedding-3-small",
  "api_key_env": "OPENAI_API_KEY",
  "dimensions": 512
}
```

Replace the openai-compatible example block (currently lines 117–124):

```json
"embedder": {
  "provider": "openai-compatible",
  "model": "provider-model-name",
  "base_url": "https://embeddings.example.com/v1",
  "api_key": "replace-if-required"
}
```

with:

```json
"embedder": {
  "provider": "openai-compatible",
  "model": "provider-model-name",
  "base_url": "https://embeddings.example.com/v1",
  "api_key_env": "MY_EMBEDDING_API_KEY"
}
```

And replace the sentence after it (currently lines 126–127):

```markdown
`api_key` is optional for `openai-compatible`, which allows an unauthenticated
local service. It is required for `openai`.
```

with:

```markdown
A key (via `api_key_env` or `api_key`) is optional for `openai-compatible`,
which allows an unauthenticated local service — omit both fields for that. It
is required for `openai`. Note that naming a variable in `api_key_env` commits
to it: if the variable is unset and there is no `api_key` fallback, vector
search is disabled rather than proceeding unauthenticated.
```

- [ ] **Step 3: Update the options table and chmod guidance**

In the field table, insert a new row directly above the `vector.embedder.api_key` row:

```markdown
| `vector.embedder.api_key_env` | no | **Recommended for hosted providers** — name of an environment variable holding the API key (e.g. `OPENAI_API_KEY`). Takes precedence over `api_key` when set |
```

And in the same table, replace the `api_key` row description:

```markdown
| `vector.embedder.api_key` | provider-dependent | Plaintext key; prefer `api_key_env`. Required for OpenAI (unless `api_key_env` is set); optional bearer token for `openai-compatible`; ignored by Ollama |
```

Replace the chmod paragraph (currently lines 154–155):

```markdown
If `config.json` contains an API key, do not commit or share it. Restrict it to
your user account, for example with `chmod 600 ~/.logseq-vector/config.json`.
```

with:

```markdown
Prefer `api_key_env` so no key is stored in `config.json`. If you do use a
plaintext `api_key`, do not commit or share the file, and restrict it to your
user account, for example with `chmod 600 ~/.logseq-vector/config.json`.
```

- [ ] **Step 4: Update the `config.py` module docstring**

In `src/mcp_logseq/config.py`, replace the docstring lines (currently 28–30):

```python
Supported embedder providers are "ollama", "openai", and
"openai-compatible". Hosted providers may also use "api_key" and "dimensions"
inside the embedder block.
```

with:

```python
Supported embedder providers are "ollama", "openai", and
"openai-compatible". Hosted providers may also use "api_key_env" (name of an
environment variable holding the API key — recommended), "api_key"
(plaintext fallback), and "dimensions" inside the embedder block. When the
variable named by "api_key_env" is set, it takes precedence over "api_key".
```

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest tests/unit/` then `uv run pyright`

Expected: all PASS (docs-only change; this guards against accidental code edits).

```bash
git add VECTOR_SEARCH.md src/mcp_logseq/config.py
git commit -m "docs(vector): recommend api_key_env over plaintext api_key (#81)"
```
