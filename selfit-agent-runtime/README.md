# selfit Agent Runtime

Independent OpenClaw fork workspace for the selfit stylist agent.

This directory is intentionally decoupled from any local Pi/Diga/OpenClaw experiments. The selfit FastAPI app talks to this runtime only through HTTP or the `openclaw agent --json` CLI surface.

## Runtime Boundary

- selfit FastAPI owns closet items, outfits, try-on records, assets, and the Web POC.
- This runtime owns stylist sessions, memory, skills, tool orchestration, and model calls.
- The runtime must call selfit through HTTP tools. It must not read or write `outputs/closet/*.json` directly.
- If model credentials fail, return `ai_unavailable`. Do not invent fallback recommendations.

## Bootstrap Latest OpenClaw

Use the script below when you want a real fork checkout:

```bash
./scripts/bootstrap-openclaw.sh
```

It clones `openclaw/openclaw` into `vendor/openclaw`, records the resolved commit in `openclaw.lock.json`, and leaves this selfit layer outside the vendor checkout so it can be reviewed separately.

Bootstrap the preferred Xiaohongshu MCP sidecar source:

```bash
./scripts/bootstrap-xhs-mcp.sh
```

It clones `xpzouying/xiaohongshu-mcp` into `vendor/xiaohongshu-mcp` and records the resolved commit in `xiaohongshu-mcp.lock.json`. Starting that sidecar requires Go on PATH.

If your machine does not have Go installed, bootstrap a project-local Go runtime:

```bash
python3 scripts/bootstrap-go-runtime.py
```

Then start Xiaohongshu MCP through Go:

```bash
./scripts/start-xhs-mcp-go.sh -headless=true
```

Build the pinned OpenClaw source before using the local bridge:

```bash
PNPM_BIN=/path/to/pnpm NODE_BIN=/path/to/node ./scripts/build-openclaw.sh
```

Start the thin selfit HTTP bridge that FastAPI calls:

```bash
NODE_BIN=/path/to/node ./scripts/start-selfit-openclaw-bridge.sh
```

It exposes:

```text
http://127.0.0.1:18789/health
http://127.0.0.1:18789/api/selfit/chat
http://127.0.0.1:18789/api/selfit/memory/{user_id}
```

The bridge invokes OpenClaw through the CLI surface and does not import OpenClaw internals into FastAPI.

## Local Wiring

Start the selfit FastAPI app first, then configure the runtime tool base URL:

```bash
export SELFIT_TOOL_BASE_URL=http://127.0.0.1:8002
export STYLIST_SELFIT_TOOL_BASE_URL=http://127.0.0.1:8002
```

For FastAPI to call the OpenClaw sidecar over HTTP:

```bash
export STYLIST_OPENCLAW_CHAT_URL=http://127.0.0.1:18789/api/selfit/chat
```

For local CLI fallback during development:

```bash
export STYLIST_ENABLE_OPENCLAW_CLI=1
```

Demo replies are only allowed when explicitly enabled:

```bash
export STYLIST_DEMO_MODE=1
```

## Included selfit Layer

- `agents/selfit-stylist/agent.md`: the stylist agent identity and output contract.
- `skills/*/SKILL.md`: selfit-specific styling skills.
- `tools/selfit-tools.openapi.json`: HTTP tool contract exposed by FastAPI.
- `config/openclaw.example.json`: target OpenClaw agent/tool/skill configuration.
- `config/xiaohongshu-mcp.example.json`: read-only Xiaohongshu MCP sidecar configuration.
- `config/search-mcp.example.json`: anonymous Exa and Parallel Search MCP configuration, plus an optional disabled SearXNG entry.
- `skills/multi-source-search/SKILL.md`: routes general web, Reddit, X, and Xiaohongshu public-index retrieval without confusing it with complete platform search.

## Xiaohongshu MCP Sidecar

Run a Xiaohongshu MCP service separately and expose it to OpenClaw, not to the FastAPI app directly.

Recommended for China site:

```bash
cd vendor/xiaohongshu-mcp
go run . -headless=true
```

Default endpoint:

```text
http://127.0.0.1:18060/mcp
```

If Docker Desktop is available, start the MCP sidecar with:

```bash
./scripts/start-xhs-mcp-docker.sh
```

Recommended environment:

```bash
export SELFIT_XHS_MCP_URL=http://127.0.0.1:18060/mcp
export SELFIT_XHS_MCP_MODE=streamable-http
export SELFIT_XHS_ALLOWED_TOOLS=search_feeds,get_feed_detail
```

## Anonymous public-web search

The default local OpenClaw configuration exposes two read-only remote MCP servers:

- Exa at `https://mcp.exa.ai/mcp` as the primary semantic web search.
- Parallel Search at `https://search.parallel.ai/mcp` as fallback and independent confirmation.

Neither endpoint requires a target-site login or API key for its anonymous tier. Verify both connections and inspect their live tool lists:

```bash
npm run doctor:search
```

The optional `searxng` entry is disabled by default. To use a self-hosted SearXNG MCP adapter, update its URL in `config/openclaw.local.json` and set `enabled` to `true`.

Public social searches use domain-restricted web queries such as `site:reddit.com`, `site:x.com`, or `site:xiaohongshu.com/explore`. These results are partial public-index evidence. Complete Xiaohongshu search still uses the separate read-only sidecar described below.

If the OpenClaw fork cannot directly consume MCP yet, bridge the HTTP MCP endpoint with MCPorter:

```bash
npm i -g mcporter
npx mcporter config add xiaohongshu-mcp http://localhost:18060/mcp
npx mcporter list xiaohongshu-mcp
```

V1 should only allow read tools: login status, search, note detail, and optional feeds. Do not enable publish, like, favorite, or comment tools in the stylist path.
