from __future__ import annotations

import json
import re

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


def test_selfit_onboarding_includes_the_figma_login_extension() -> None:
    response = client.get("/selfit/demo")

    assert response.status_code == 200
    assert 'data-screen="login"' in response.text
    assert 'data-screen="splash"' in response.text
    assert 'data-screen="phone-login"' in response.text
    assert 'data-screen="invite-login"' in response.text
    assert 'id="phoneLoginForm"' in response.text
    assert 'id="inviteLoginForm"' in response.text
    assert "适我，不适众" in response.text
    assert "Fit yourself, not in." in response.text
    assert "手机号登录" in response.text
    assert "邀请码登录" in response.text
    assert "/static/selfit/assets/login-tagline-curved@2x.png" in response.text
    assert "/static/selfit/assets/login-brand-ornament@2x.png" in response.text
    assert '/static/selfit/selfit-auth.js' in response.text
    assert '"authBase": "/auth"' in response.text


def test_selfit_manual_suit_selection_uses_the_figma_option_order() -> None:
    response = client.get("/selfit/demo")

    assert response.status_code == 200
    assert "冷白</span>" in response.text
    assert "菱型脸</span>" in response.text
    assert "方型脸</span>" in response.text
    assert "鹅蛋脸</span>" in response.text
    assert "/static/selfit/assets/manual-selection/face-diamond@4x.png" in response.text
    assert "/static/selfit/assets/manual-selection/face-square@4x.png" in response.text
    assert "/static/selfit/assets/manual-selection/body-pear@4x.png" in response.text
    assert "face-diamond-card@4x.png" not in response.text
    assert "body-pear@2x.png" not in response.text


def test_selfit_manual_suit_options_follow_latest_figma_geometry() -> None:
    styles = client.get("/static/selfit/selfit.css")

    assert styles.status_code == 200
    assert ".manual-visual-options--face { width: min(343px, 100%); grid-template-columns: repeat(5, 59px); }" in styles.text
    assert ".manual-visual-options--face .manual-art img { width: 39px; height: 60px;" in styles.text
    assert ".manual-visual-options--body { width: min(348px, 100%); grid-template-columns: repeat(5, 60px); }" in styles.text
    assert ".manual-visual-options--body .manual-art img { width: 36px; height: 102px;" in styles.text


def test_selfit_intro_uses_complete_high_density_lace_card_assets() -> None:
    response = client.get("/selfit/demo")
    styles = client.get("/static/selfit/selfit.css")

    assert response.status_code == 200
    assert styles.status_code == 200
    for name in ("suit", "like", "vibe"):
        assert f"/static/selfit/assets/{name}-card-base@2x.png" in response.text
    assert "background-image: url('/static/selfit/assets/onboarding-intro-reference@2x.png')" not in styles.text


def test_selfit_latest_onboarding_geometry_and_loading_brandmark_are_locked() -> None:
    markup = client.get("/selfit/demo")
    styles = client.get("/static/selfit/selfit.css")

    assert markup.status_code == 200
    assert styles.status_code == 200
    assert ".stepper {" in styles.text
    assert "width: 265px;" in styles.text
    assert '.stepper--like::after { width: 102.5px; }' in styles.text
    assert '.stepper--vibe::after { width: 218px; }' in styles.text
    assert '#FFDED7' in markup.text
    assert '#CB956C' in markup.text
    assert '#D3D3D3' in markup.text
    assert '#B1B2D1' in markup.text
    assert '/static/selfit/assets/splash-signature@2x.png' in markup.text
    assert '.loading-art-frame { position: absolute; top: 244px;' in styles.text
    assert '--loading-art-width: 240px; --loading-art-height: 162px;' in styles.text
    assert '.loading-story img[data-stage="75"]' in styles.text
    assert '.loading-brandmark' in styles.text
    assert 'width: 103px; height: 66px;' in styles.text
    assert '.screen[data-screen="suit"] .bottom-action:disabled' in styles.text
    assert 'background: #c2c2c2;' in styles.text


def test_selfit_photo_validation_copy_is_centered_as_a_complete_line() -> None:
    styles = client.get("/static/selfit/selfit.css")

    assert styles.status_code == 200
    assert ".photo-status-list { display: flex; width: 100%;" in styles.text
    assert "flex-direction: column; align-items: center;" in styles.text
    assert ".photo-status { display: flex; width: max-content; max-width: 100%;" in styles.text
    assert "justify-content: center;" in styles.text
    assert "text-align: center; white-space: nowrap;" in styles.text


def test_selfit_like_palettes_match_the_latest_figma_color_order() -> None:
    markup = client.get("/selfit/demo")

    assert markup.status_code == 200
    rendered_colors = re.findall(r'--c:(#[0-9A-F]{6})', markup.text)
    assert rendered_colors[:24] == [
        "#D3D3D3", "#A8A8A8", "#656464", "#403F3E",
        "#E8D3B8", "#C08A52", "#8A4B2A", "#4A3428",
        "#9EB5C8", "#506F7E", "#50668D", "#65568D",
        "#A79873", "#6A5D30", "#642218", "#432F1F",
        "#DF4F53", "#ECAE24", "#A9A921", "#91B0D1",
        "#D4B9A5", "#C8D3D0", "#E6D8D7", "#B1B2D1",
    ]


def test_selfit_vibe_form_matches_the_latest_figma_layout() -> None:
    markup = client.get("/selfit/demo")
    styles = client.get("/static/selfit/selfit.css")

    assert markup.status_code == 200
    assert styles.status_code == 200
    assert 'class="vibe-scroll"' in markup.text
    assert 'class="vibe-action-dock"' in markup.text
    assert ".vibe-scroll {" in styles.text
    assert "top: 137px;" in styles.text
    assert "padding: 20px 5px 134px 16px;" in styles.text
    assert ".page-copy--vibe { width: 340px; max-width: 100%; height: 64px; margin: 0; }" in styles.text
    assert ".vibe-questionnaire legend { margin: 0 0 16px;" in styles.text
    assert "height: 42px;" in styles.text
    assert ".vibe-action-dock" in styles.text
    assert "height: 114px;" in styles.text


def test_selfit_back_control_and_stepper_share_the_figma_top_row() -> None:
    styles = client.get("/static/selfit/selfit.css")

    assert styles.status_code == 200
    assert "--onboarding-safe-top: max(54px, env(safe-area-inset-top));" in styles.text
    assert ".screen-header--quiet { position: relative; z-index: 3; top: var(--onboarding-safe-top); height: 46px; padding: 0; }" in styles.text
    assert "top: calc(var(--onboarding-safe-top) + 4px);" in styles.text
    assert "left: 64px;" in styles.text
    assert "width: 265px;" in styles.text
    assert "height: 38px;" in styles.text
    assert ".manual-header .icon-button { position: absolute; top: 1px; left: 20px; width: 44px; height: 44px;" in styles.text
    assert ".page-copy--suit, .page-copy--assessment { margin-top: 111px; }" in styles.text


def test_selfit_suit_keeps_the_manual_selection_entry_above_the_primary_action() -> None:
    markup = client.get("/selfit/demo")
    styles = client.get("/static/selfit/selfit.css")

    assert markup.status_code == 200
    assert styles.status_code == 200
    assert 'class="direct-select" type="button" data-next="suit-manual"' in markup.text
    assert "不方便拍照？直接选" in markup.text
    assert "bottom: calc(max(60px, env(safe-area-inset-bottom)) + 44px);" in styles.text
    assert "min-width: 184px;" in styles.text
    assert "height: 44px;" in styles.text
    assert "top: auto;" in styles.text
    assert "bottom: calc(max(18px, env(safe-area-inset-bottom)) + 44px);" in styles.text


def test_selfit_auth_adapter_and_bearer_wiring_are_available() -> None:
    auth = client.get("/static/selfit/selfit-auth.js")
    api = client.get("/static/selfit/selfit-api.js")
    runtime = client.get("/static/selfit/selfit.js")

    assert auth.status_code == 200
    assert "startPhone(phone)" in auth.text
    assert "verifyPhone(phone, code)" in auth.text
    assert "verifyInvite(inviteCode)" in auth.text
    assert "sessionStorage.setItem(AUTH_STORAGE_KEY" in auth.text
    assert "this.request('/invite/verify'" in auth.text
    assert "headers.Authorization = `Bearer ${accessToken}`" in api.text
    assert "getAccessToken: () => auth.accessToken" in runtime.text
    assert "state.authUser ? 'intro' : 'login'" in runtime.text


def test_selfit_vibe_question_keys_match_backend_contract() -> None:
    response = client.get("/selfit/demo")

    assert response.status_code == 200
    question_keys = re.findall(r'<fieldset data-question="([^"]+)">', response.text)
    assert question_keys == ["occasion", "wardrobe", "expression"]
    assert not {"q1", "q2", "q3"}.intersection(question_keys)


def test_selfit_onboarding_uses_high_resolution_production_assets() -> None:
    for asset_path in (
        "/static/selfit/assets/face-upload-guide@4x.png",
        "/static/selfit/assets/manual-selection/face-diamond@4x.png",
        "/static/selfit/assets/manual-selection/body-pear@4x.png",
        "/static/selfit/assets/onboarding-loading-signature@2x.png",
        "/static/selfit/assets/report-style-soft-cool@4x.png",
        "/static/selfit/assets/figma-report/report-hero-reference.png",
        "/static/selfit/assets/figma-report/outfit-01@4x.png",
    ):
        response = client.get(asset_path)
        assert response.status_code == 200, asset_path
        assert response.headers["content-type"].startswith("image/"), asset_path


def test_selfit_report_typography_matches_the_approved_layout() -> None:
    response = client.get("/static/selfit/selfit.css")

    assert response.status_code == 200
    assert ".report-summary { text-align: center; }" in response.text
    assert ".report-body h2, .report-advice h2" in response.text
    assert ".report-image-grid figcaption, .outfit-list figcaption" in response.text
    assert "font-size: 14px; font-weight: 400; line-height: 20px; text-align: center;" in response.text
    assert "border-radius: 8px; background: var(--c);" in response.text
    assert ".report-advice-list { margin-top: 14px;" in response.text
    assert ".report-signoff-dots" in response.text

    markup = client.get("/selfit/demo")
    assert ">返回重测</button>" in markup.text
    assert '<h2>你的风格解读</h2>' in markup.text

    runtime = client.get("/static/selfit/selfit.js")
    assert "#retakeBtn').addEventListener('click', () => showScreen('vibe'))" in runtime.text


def test_selfit_personality_catalog_keeps_all_colors_but_renders_first_five() -> None:
    response = client.get("/static/selfit/data/personality-report-templates.v1.json")

    assert response.status_code == 200
    catalog = json.loads(response.text)
    assert catalog["templateVersion"] == "2026.08.personality-db-v4"
    assert catalog["renderRules"]["colors"]["limit"] == 5
    assert len(catalog["types"]) == 16
    assert sum(len(item["colors"]["items"]) for item in catalog["types"].values()) == 112
    assert any(len(item["colors"]["items"]) > 5 for item in catalog["types"].values())

    for type_id, template in catalog["types"].items():
        assert template["typeId"] == type_id
        hero = template["hero"]["image"]
        assert hero["placeholder"] is False
        assert hero["src"] == f"/static/selfit/assets/personality/{type_id}/hero.png?v=20260825-final"
        assert (hero["width"], hero["height"]) == (1484, 1072)
        assert len(template["colors"]["items"]) >= 5
        assert len(template["recommendations"]["makeup"]) == 2
        assert len(template["recommendations"]["hair"]) == 2
        assert len(template["recommendations"]["outfits"]["items"]) == 4
        assert all(re.fullmatch(r"#[0-9A-F]{6}", color["value"]) for color in template["colors"]["items"])

    mute_hair = catalog["types"]["mute"]["recommendations"]["hair"]
    assert [item["name"] for item in mute_hair] == ["外翘初恋发", "八字显脸小发"]
    assert all(item["name"] not in {"💇🏻‍♀️显脸小的发型💓", "减龄又显白的发色、米棕色"} for item in mute_hair)

    runtime = client.get("/static/selfit/selfit.js")
    assert runtime.status_code == 200
    assert "template.colors?.renderLimit || personalityCatalog.renderRules?.colors?.limit || 5" in runtime.text
    assert "data.colors.slice(0, personalityCatalog.renderRules?.colors?.limit || 5)" in runtime.text
    assert ".slice(0, personalityCatalog.renderRules?.outfits?.limit || 4)" in runtime.text
    assert "replace(/^\\s*建议\\s*[：:]\\s*/, '')" in runtime.text

    for template in catalog["types"].values():
        assert all(
            not str(point).lstrip().startswith(("建议：", "建议:"))
            for point in template["conclusion"]["points"]
        )


def test_personality_hero_uses_the_final_artwork_ratio_without_a_fallback_background() -> None:
    selfit_css = client.get("/static/selfit/selfit.css")
    preview_css = client.get("/static/report-builder/preview.css")

    assert selfit_css.status_code == 200
    assert preview_css.status_code == 200
    for stylesheet in (selfit_css.text, preview_css.text):
        assert "aspect-ratio: 1484 / 1072" in stylesheet or "aspect-ratio:1484/1072" in stylesheet
        assert "background: transparent" in stylesheet or "background:transparent" in stylesheet
        assert "box-shadow: none" in stylesheet or "box-shadow:none" in stylesheet
        assert "object-position: center" in stylesheet or "object-position:center" in stylesheet
        assert "translateX(-2.39%)" not in stylesheet


def test_selfit_personality_assets_and_runtime_catalog_are_available() -> None:
    for asset_path in (
        "/static/selfit/personality-report-templates.js",
        "/static/selfit/assets/personality/placeholder-hero.svg",
        "/static/selfit/assets/personality/mute/hero.png",
        "/static/selfit/assets/personality/flou/hero.png",
        "/static/selfit/assets/personality/oops/hero.png",
        "/static/selfit/assets/personality/flou/color-card.png",
        "/static/selfit/assets/personality/flou/makeup-01.webp",
        "/static/selfit/assets/personality/flou/hair-01.webp",
        "/static/selfit/assets/personality/flou/outfits-04.webp",
        "/static/selfit/assets/personality/oops/outfits-04.webp",
    ):
        response = client.get(asset_path)
        assert response.status_code == 200, asset_path


def test_selfit_mirror_route_serves_the_capture_flow() -> None:
    response = client.get("/selfit/mirror")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "selfit 智能镜子" in response.text
    assert 'id="startCapture"' in response.text
    assert 'data-screen="countdown"' in response.text
    assert 'data-screen="confirm"' in response.text
    assert 'data-screen="processing"' in response.text
    assert 'data-screen="result"' in response.text
    assert 'id="processingArt"' in response.text
    assert "看见你本来的样子" in response.text
    assert "正在分析中" not in response.text


def test_selfit_mirror_assets_are_available() -> None:
    for asset_path in (
        "/static/selfit/assets/mirror-demo-full-body.webp",
        "/static/selfit/assets/mirror-home-manifesto@2x.png",
        "/static/selfit/assets/mirror-loading-ornament@2x.png",
        "/static/selfit/assets/mirror-loading-stage-25@2x.png",
        "/static/selfit/assets/mirror-loading-stage-50@2x.png",
        "/static/selfit/assets/mirror-loading-stage-75@2x.png",
        "/static/selfit/assets/mirror-signature-know-yourself@2x.png",
        "/static/selfit/assets/mirror-report-qr.png",
    ):
        response = client.get(asset_path)
        assert response.status_code == 200, asset_path
        assert response.headers["content-type"].startswith("image/"), asset_path
