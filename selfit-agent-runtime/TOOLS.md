# selfit Tool Boundary

The selfit product service is the source of truth for closet, outfit, try-on, Xiaohongshu, and style knowledge data. Use the HTTP tool surface described in `tools/selfit-tools.openapi.json`.

## Allowed Tool Families

- `selfit_closet_search`: search the user's closet items.
- `selfit_get_item`: inspect one closet item.
- `selfit_compose_outfit`: propose a deduplicated outfit from closet items.
- `selfit_save_outfit`: save a user-approved outfit.
- `selfit_tryon_from_outfit`: start try-on from an outfit.
- `selfit_xhs_search`: search Xiaohongshu trend notes.
- `selfit_xhs_fetch_note`: fetch one Xiaohongshu note's usable text/images.
- `selfit_style_kb_search`: retrieve internal styling knowledge.

## Data Rules

- Do not read local manifest files directly.
- Do not infer that a closet item exists unless a tool result returned it.
- Do not use Xiaohongshu claims without evidence source metadata.
- Do not silently downgrade to mock data when a tool, model, provider, or key is unavailable.

## Local Base URL

The product service base URL is provided by `SELFIT_TOOL_BASE_URL`. Default local development value:

```text
http://127.0.0.1:8002
```
