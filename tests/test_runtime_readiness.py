from scripts.check_runtime_readiness import readiness
from app.main import app
from fastapi.testclient import TestClient


def test_runtime_readiness_reports_missing_optional_runtime(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("STYLIST_DEMO_MODE=0\n", encoding="utf-8")

    report = readiness(env_path)

    assert report["status"] in {"missing_runtime_dependencies", "ready_for_full_user_trial"}
    assert "modules" in report
    assert "ready" in report
    assert "missing_actions" in report
    assert "sidecars" in report
    assert "openclaw" in report["sidecars"]


def test_runtime_readiness_reads_env_file_keys(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "STYLIST_OPENCLAW_CHAT_URL=http://127.0.0.1:18789/api/selfit/chat",
                "STYLIST_OPENCLAW_MEMORY_URL=http://127.0.0.1:18789/api/selfit/memory",
                "SELFIT_XHS_MCP_URL=http://127.0.0.1:18060/mcp",
                "TRYON_RUNWAY_GOOGLE_URL=http://127.0.0.1:18090/v1:generateContent",
                "TRYON_RUNWAY_GOOGLE_API_KEY=test-key",
                "STYLIST_DEMO_MODE=0",
            ]
        ),
        encoding="utf-8",
    )

    report = readiness(env_path)

    assert report["env"]["stylist"]["chat_url"] is True
    assert report["env"]["stylist"]["memory_url"] is True
    assert report["env"]["xiaohongshu"]["mcp_url"] is True
    assert "stylist_bridge_health" in report["endpoints"]
    assert report["ready"]["real_tryon"] is True


def test_runtime_readiness_requires_stylist_key_to_match_model_provider(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "STYLIST_OPENCLAW_CHAT_URL=http://127.0.0.1:18789/api/selfit/chat",
                "STYLIST_OPENCLAW_MEMORY_URL=http://127.0.0.1:18789/api/selfit/memory",
                "STYLIST_OPENCLAW_MODEL=openai/gpt-5.5",
                "GOOGLE_API_KEY=test-key",
                "STYLIST_DEMO_MODE=0",
            ]
        ),
        encoding="utf-8",
    )

    report = readiness(env_path)

    assert report["env"]["stylist"]["model_provider"] == "openai"
    assert report["env"]["stylist"]["model_key_present"] is True
    assert report["env"]["stylist"]["model_key_matches_provider"] is False
    assert any("STYLIST_OPENCLAW_MODEL" in action for action in report["missing_actions"])


def test_runtime_readiness_accepts_google_key_when_model_routes_google(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "STYLIST_OPENCLAW_MODEL=google/gemini-2.5-flash",
                "GOOGLE_API_KEY=test-key",
                "STYLIST_DEMO_MODE=0",
            ]
        ),
        encoding="utf-8",
    )

    report = readiness(env_path)

    assert report["env"]["stylist"]["model_provider"] == "google"
    assert report["env"]["stylist"]["model_key_present"] is True
    assert report["env"]["stylist"]["model_key_matches_provider"] is True


def test_runtime_readiness_accepts_minimax_key_when_model_routes_minimax(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "STYLIST_OPENCLAW_MODEL=minimax/MiniMax-M3",
                "MINIMAX_API_KEY=test-key",
                "STYLIST_DEMO_MODE=0",
            ]
        ),
        encoding="utf-8",
    )

    report = readiness(env_path)

    assert report["env"]["stylist"]["model_provider"] == "minimax"
    assert report["env"]["stylist"]["accepted_model_key_env"] == ["MINIMAX_API_KEY"]
    assert report["env"]["stylist"]["model_key_present"] is True
    assert report["env"]["stylist"]["model_key_matches_provider"] is True


def test_runtime_readiness_endpoint_returns_user_trial_summary() -> None:
    client = TestClient(app)

    response = client.get("/selfit/runtime-readiness")

    assert response.status_code == 200
    data = response.json()
    assert "ready" in data
    assert "multi_category_closet" in data["ready"]
    assert "sidecars" in data
    assert "missing_actions" in data


def test_runtime_smoke_script_exists() -> None:
    from pathlib import Path

    script = Path("scripts/selfit_runtime_smoke.py")
    assert script.exists()
    assert "selfit/runtime-readiness" in script.read_text(encoding="utf-8")


def test_full_stack_acceptance_script_exists() -> None:
    from pathlib import Path

    script = Path("scripts/selfit_full_stack_acceptance.py")
    text = script.read_text(encoding="utf-8")
    assert script.exists()
    assert "--strict" in text
    assert "start_selfit_full_stack.sh" in text
    assert "/stylist/chat" in text
    assert "strict_ai_stylist_chat" in text


def test_search_mcp_configuration_and_router_skill_exist() -> None:
    import json
    from pathlib import Path

    runtime = Path("selfit-agent-runtime")
    config = json.loads((runtime / "config/search-mcp.example.json").read_text(encoding="utf-8"))
    servers = config["mcp"]["servers"]

    assert servers["exa"]["url"] == "https://mcp.exa.ai/mcp"
    assert servers["exa"]["toolFilter"]["include"] == ["web_search_exa", "web_fetch_exa"]
    assert servers["parallel-search"]["url"] == "https://search.parallel.ai/mcp"
    assert servers["parallel-search"]["toolFilter"]["include"] == ["web_search", "web_fetch"]
    assert servers["searxng"]["enabled"] is False

    skill = (runtime / "skills/multi-source-search/SKILL.md").read_text(encoding="utf-8")
    assert "site:reddit.com" in skill
    assert "site:x.com" in skill
    assert "site:xiaohongshu.com/explore" in skill
    assert (runtime / "scripts/probe-search-mcp.mjs").exists()


def test_sync_selfit_env_appends_without_overwriting(tmp_path) -> None:
    from scripts.sync_selfit_env import sync_env

    env_path = tmp_path / ".env"
    env_path.write_text("STYLIST_DEMO_MODE=custom\nOPENAI_API_KEY=secret\n", encoding="utf-8")

    result = sync_env(env_path)
    text = env_path.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY=secret" in text
    assert "STYLIST_DEMO_MODE=custom" in text
    assert "STYLIST_OPENCLAW_CHAT_URL=http://127.0.0.1:18789/api/selfit/chat" in text
    assert "STYLIST_DEMO_MODE" not in result["added"]
