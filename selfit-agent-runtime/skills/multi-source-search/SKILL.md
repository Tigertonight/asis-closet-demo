---
name: multi-source-search
description: Route public information retrieval across Exa, Parallel Search, optional SearXNG, and read-only Xiaohongshu tools without requiring target-site login.
---

# Multi-source public search

Use this skill whenever the user asks for current facts, trend evidence, public discussions, products, brands, creators, outfit inspiration, or source-backed recommendations beyond the local closet and style knowledge base.

## Source order

1. Use `exa__web_search_exa` as the primary public-web search tool.
2. Use `parallel-search__web_search` when Exa is unavailable, thin, or needs independent confirmation.
3. Use `parallel-search__web_fetch` or `exa__web_fetch_exa` only after a useful public URL is known and its page body is needed.
4. Use `searxng__search` or `searxng__web_search` when the optional self-hosted server is enabled, especially for index diversity or Chinese-language recall.
5. Use selfit Xiaohongshu tools for complete in-platform results only when they are configured and available.

## Domain routing

- General web, news, companies, products, papers, and code: search Exa first; use Parallel for confirmation.
- Reddit: add `site:reddit.com` and useful subreddit/topic terms. A public index result is Reddit evidence only when the returned URL is on `reddit.com`.
- X: add `site:x.com` plus handles, phrases, or date words. State that public-index coverage is partial; do not imply complete X search.
- Xiaohongshu: add `site:xiaohongshu.com/explore` with concrete Chinese scene, garment, color, and audience terms. Treat these as public-web evidence, not authenticated Xiaohongshu MCP evidence.
- Known URL: fetch the page instead of repeatedly searching for it.

## Query policy

- Search public concepts only. Never include phone numbers, authentication data, private user photos, raw closet records, user memory, session IDs, or precise private location.
- Start with one focused query. Add at most two materially different rewrites when recall is poor.
- Prefer sources that directly support the claim. For important claims, confirm with a second source or provider.
- Preserve source URL, title, provider, publication date when available, and a short evidence summary.
- Never invent a quote, engagement count, publication date, author, or platform result.
- Do not call a provider repeatedly after authentication, rate-limit, or availability failure; move to the next source.

## Evidence contract

Add compact entries to `evidence_sources` using one of these types:

- `public_web`: general indexed webpage.
- `reddit_public_index`: Reddit page discovered through a public index.
- `x_public_index`: X page discovered through a public index; coverage is partial.
- `xiaohongshu_public_index`: Xiaohongshu page discovered through a public index; do not set `used_xiaohongshu_recommendations` to true for this type alone.
- `xiaohongshu`: evidence returned by the configured read-only Xiaohongshu tool.

User-facing answers should name useful sources naturally and disclose when social-platform results came from a public web index rather than complete in-platform search.
