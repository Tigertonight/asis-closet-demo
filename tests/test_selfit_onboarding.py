from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_selfit_onboarding_route_serves_the_product_flow() -> None:
    response = client.get("/selfit/demo")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "selfit · 先认识自己，再决定怎么穿" in response.text
    assert 'data-screen="suit"' in response.text
    assert 'data-screen="report"' in response.text


def test_selfit_onboarding_uses_high_resolution_production_assets() -> None:
    for asset_path in (
        "/static/selfit/assets/face-upload-guide@4x.png",
        "/static/selfit/assets/manual-selection/face-shapes-strip@4x.png",
        "/static/selfit/assets/report-style-soft-cool@4x.png",
        "/static/selfit/assets/figma-report/outfit-01@4x.png",
    ):
        response = client.get(asset_path)
        assert response.status_code == 200, asset_path
        assert response.headers["content-type"].startswith("image/"), asset_path
