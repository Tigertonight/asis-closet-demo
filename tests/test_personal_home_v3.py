import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.recommendation_profile import resolve_profile, preview_profile, validation_enabled
from app.recommendation_feed import normalize, SEASONS, SCENES, color_score, palette_affinity, rank_candidates, select_sequence, create_feed, continue_feed, validate_feedback
from app.recommendation_visual import attach_visual, valid_observation
from app.recommendation_anchors import P0_SEQUENCE_ROLES
from app.storage import user_storage
from tests.test_persona_test_mode import run_js


def profile(**updates):
    return {"persona_id":"loop","palette":"ocean","palette_source":"onboarding","axes":{},"version":"p1",**updates}


def outfit(n, category="pants", color="#286db3", expression="easy"):
    gid=f"g{n}"
    categories={"pants":"bottom","skirt":"skirt","dress":"dress"}
    return {"outfit_id":f"o{n}","parent_outfit_id":None,"tryon_ready":True,"visual_evidence":"利落线条与可组合的简洁结构",
            "items":[{"item_id":gid,"category":categories[category],"color_evidence":{"swatches":[{"hex":color,"weight":1}]}}],
            "visual":{"structure":category,"expression":expression,"seasons":["秋"],"scenes":["日常"],"persona_scores":{"loop":.8,"mute":.65},"axes":{"shape":30,"energy":25,"trend":40},"conflicts":[]}}


def test_profile_is_account_owned_latest_report_and_linked_preference():
    store={"reports":[{"user_id":"u","session_id":"s","report_id":"r","created_at":"2026-01-01","data":{"typeId":"loop"}},
                      {"user_id":"other","session_id":"s2","created_at":"2027-01-01","data":{"typeId":"mute"}}],
           "sessions":[{"user_id":"u","session_id":"s","preferences":{"palette":"earth","axes":{"shape":20},"private":"no"}}]}
    result=resolve_profile("u",store,{})
    assert result["persona_id"]=="loop" and result["palette"]=="earth"
    assert "private" not in json.dumps(result) and "session_id" not in result
    changed=resolve_profile("u",store,{"recommendation":{"palette":"ocean"}})
    assert changed["palette_source"]=="explicit_preference" and result["version"]!=changed["version"]
    store["sessions"][0]["user_id"]="other"
    assert resolve_profile("u",store,{})["palette"] is None


def test_rollout_requires_both_flag_and_exact_allowlist(monkeypatch):
    monkeypatch.setenv("SELFIT_RECOMMENDATION_V3_ENABLED","1")
    monkeypatch.setenv("SELFIT_RECOMMENDATION_V3_USERS","one,two")
    assert validation_enabled("one") and not validation_enabled("on")
    monkeypatch.setenv("SELFIT_RECOMMENDATION_V3_ENABLED","0")
    assert not validation_enabled("one")


def test_preview_does_not_mutate_formal_and_invalid_values_fail():
    real=profile(); before=copy.deepcopy(real)
    viewed=preview_profile(real,{"palette":"bright"},{"typeId":"mute"})
    assert viewed["persona_id"]=="mute" and viewed["palette"]=="bright" and real==before
    with pytest.raises(HTTPException):preview_profile(real,{"palette":"invalid"},{"typeId":"mute"})


def test_color_is_main_garment_weighted_not_accessory_and_preference_changes_order():
    blue=outfit(1); brown=outfit(2,color="#826039")
    before=color_score(brown,profile())
    brown["items"].append({"item_id":"bag","category":"bag","color_evidence":{"swatches":[{"hex":"#206dc0","weight":1}]}})
    assert color_score(brown,profile())==before
    a,_=rank_candidates([brown,blue],profile(),{"season_tags":["autumn"]})
    b,_=rank_candidates([brown,blue],profile(palette="earth"),{"season_tags":["秋"]})
    assert a[0]["outfit_id"]=="o1" and b[0]["outfit_id"]=="o2"
    assert a[0]["recommendation"]["components"]["axes"] is None
    assert sum(a[0]["recommendation"]["contributions"].values())<=1


def test_recipe_hero_color_outweighs_neutral_support_but_accessory_cannot():
    vivid = {"swatches": [{"hex": "#1555d8", "weight": 1}]}
    neutral = {"swatches": [{"hex": "#eeeeea", "weight": 1}]}
    items = [
        {"item_id": "coat", "category": "top", "slot": "outer", "outfit_role": "hero", "color_evidence": vivid},
        {"item_id": "shirt", "category": "top", "outfit_role": "support", "color_evidence": neutral},
        {"item_id": "pants", "category": "bottom", "outfit_role": "support", "color_evidence": neutral},
    ]
    assert color_score({"items": items}, profile(palette="bright")) >= .3
    items[0] = {"item_id": "bag", "category": "bag", "outfit_role": "hero", "color_evidence": vivid}
    assert color_score({"items": items}, profile(palette="bright")) < .3


def test_deep_saturated_purple_is_jewel_not_bright():
    jewel = palette_affinity("#301633", "jewel")
    bright = palette_affinity("#301633", "bright")
    assert jewel >= .5 and jewel > bright * 3


def test_season_scene_unknown_and_explicit_exclusions():
    assert normalize(["秋","autumn"],SEASONS)=={"autumn"}
    assert normalize("四季",SEASONS)=={"spring","summer","autumn","winter"}
    assert normalize("上班",SCENES)=={"commute"}
    row=outfit(1)
    assert rank_candidates([row],profile(),{"season_tags":["summer"]})[0]==[]
    row["visual"]["seasons"]=[]
    assert rank_candidates([row],profile(),{"season_tags":["summer"]})[0]
    assert rank_candidates([row],profile(excluded_categories=["bottom"]),{})[0]==[]
    row["items"][0]["laundry_status"]="laundry"
    assert rank_candidates([row],profile(),{})[0]==[]


def test_first_ten_structure_and_expression_quota():
    rows=[outfit(i,category=["pants","skirt","dress"][i%3],expression=["easy","typical","explore"][(i//3)%3]) for i in range(90)]
    selected,gaps=select_sequence(rows,30)
    assert len(selected)==30
    assert len({o["outfit_id"] for o in selected[:10]})==10
    from collections import Counter
    assert Counter(o["visual"]["expression"] for o in selected[:4])=={"easy":3,"typical":1}
    assert Counter(o["visual"]["expression"] for o in selected[4:10])=={"easy":4,"typical":1,"explore":1}
    counts=Counter(o["visual"]["structure"] for o in selected[:10])
    assert len(counts)==3 and max(counts.values())<=5


def test_p0_anchor_sequence_consumes_exact_four_four_two_mix():
    expressions = ["easy"] * 4 + ["typical"] * 4 + ["explore"] * 2
    rows = [outfit(i, category=["pants", "skirt", "dress"][i % 3], expression=expression)
            for i, expression in enumerate(expressions)]
    selected, gaps = select_sequence(rows, 10, expression_roles=P0_SEQUENCE_ROLES)
    from collections import Counter
    assert not gaps and len(selected) == 10
    assert Counter(row["visual"]["expression"] for row in selected) == {
        "easy": 4, "typical": 4, "explore": 2,
    }
    assert set(row["visual"]["structure"] for row in selected) == {"pants", "skirt", "dress"}


def test_expression_sequence_rejects_invalid_release_contract():
    with pytest.raises(ValueError):
        select_sequence([], expression_roles=["easy"] * 9)


def test_recent_hero_and_feedback_are_bounded_and_decayed():
    rows=[outfit(i) for i in range(4)]
    assert select_sequence(rows,1,recent_hero={"o0"})[0][0]["outfit_id"]=="o1"
    now=datetime.now(timezone.utc)
    events=[{"entity_id":"o0","event_type":"dislike","created_at":now.isoformat()}]*100
    result,_=rank_candidates(rows,profile(),{},events,now)
    assert next(o for o in result if o["outfit_id"]=="o0")["recommendation"]["components"]["behavior"]==0
    for e in events:e["created_at"]=(now-timedelta(days=40)).isoformat()
    result,_=rank_candidates(rows,profile(),{},events,now)
    assert all(o["recommendation"]["components"]["behavior"] is None for o in result)


def test_snapshot_retry_profile_change_account_isolation_and_feedback(tmp_path,monkeypatch):
    import app.storage as storage
    monkeypatch.setattr(storage,"ROOT_DIR",tmp_path)
    rows=[outfit(i,category=["pants","skirt","dress"][i%3],expression=["easy","typical","explore"][(i//3)%3]) for i in range(90)]
    with user_storage("u"):
        first=create_feed(profile(),rows,{})
        assert len(first["carousel"])==4 and len(first["outfits"])==6
        second=continue_feed(first["session_id"],first["next_cursor"],profile())
        assert len(second["outfits"])==6
        assert second==continue_feed(first["session_id"],first["next_cursor"],profile())
        with pytest.raises(HTTPException):continue_feed(first["session_id"],first["next_cursor"],profile(version="changed"))
        with pytest.raises(HTTPException):continue_feed(first["session_id"],"11:fake",profile())
        payload={"entity_id":first["carousel"][0]["outfit_id"],"event_type":"impression","context":{"recommendation_session":first["session_id"],"visible_ratio":.5,"visible_ms":999}}
        with pytest.raises(HTTPException):validate_feedback(payload)
        payload["context"]["visible_ms"]=1000
        assert "style_family_ids" in validate_feedback(payload)["context"]
        preview=create_feed(profile(preview=True),rows,{})
        payload["context"]["recommendation_session"]=preview["session_id"]
        with pytest.raises(HTTPException):validate_feedback(payload)
    with user_storage("other"):
        with pytest.raises(HTTPException):continue_feed(first["session_id"],first["next_cursor"],profile())


def test_dislike_suppresses_later_related_family_in_same_snapshot(tmp_path, monkeypatch):
    import app.storage as storage
    from app.recommendation_feed import _read_snapshot, _write_snapshot
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    rows = [outfit(i, category=["pants", "skirt", "dress"][i % 3], expression=["easy", "typical", "explore"][(i // 3) % 3]) for i in range(90)]
    with user_storage("u"):
        first = create_feed(profile(), rows, {})
        snapshot = _read_snapshot(first["session_id"])
        target, related = snapshot["rows"][0], snapshot["rows"][10]
        target["items"][0]["style_family_id"] = "family:disliked"
        related["items"][0]["style_family_id"] = "family:disliked"
        _write_snapshot(snapshot)
        validate_feedback({
            "entity_id": target["outfit_id"],
            "event_type": "dislike",
            "reason": "repeated",
            "context": {"recommendation_session": first["session_id"]},
        })
        next_page = continue_feed(first["session_id"], first["next_cursor"], profile())
        assert related["outfit_id"] not in {row["outfit_id"] for row in next_page["outfits"]}


def test_home_dislike_immediately_requests_a_reviewed_replacement_page():
    from app import closet
    source = closet.render_selfit_demo_page()
    handler = source.split('$all("[data-feedback-reason]")', 1)[1].split('$("#confirmTryonBack")', 1)[0]
    assert 'state.outfits = state.outfits.filter' in handler
    assert 'await maybeLoadMoreHomeOutfits(true)' in handler


def test_missing_visual_evidence_is_not_auto_approved():
    rows,held=attach_visual([{"outfit_id":"a","items":[]}],[],[{"id":"a"}],{})
    assert rows==[] and held["a"]=="outfit_visual_pending_or_stale"


def test_experimental_review_is_valid_but_not_daily_or_light_exploration():
    from app.closet import selfit_content_pool
    from app.recommendation_visual import load_visual
    pool = selfit_content_pool()
    audit = load_visual()
    records = {row["id"]: row for row in pool.outfits}
    oid, reviewed = next((oid, row) for oid, row in audit["outfits"].items() if row["token"] == "o0821")
    assert reviewed["observations"]["expression"] == "experimental"
    assert valid_observation(records[oid], reviewed, reviewed["image_url"], "outfits")
    changed = copy.deepcopy(reviewed)
    changed["observations"]["expression"] = "unrecognized"
    assert not valid_observation(records[oid], changed, changed["image_url"], "outfits")
    changed["observations"]["expression"] = "experimental"
    changed["asset_sha256"] = "changed"
    assert not valid_observation(records[oid], changed, changed["image_url"], "outfits")
    row = outfit(100, expression="experimental")
    for scenes in (None, ["daily"], ["creative"], ["daily", "creative"]):
        row["visual"]["scenes"] = scenes
        ranked, rejected = rank_candidates([row], profile(), {})
        assert not ranked
        assert rejected["experimental_requires_confirmed_nondaily_scene"] == 1
    row["visual"]["scenes"] = ["creative"]
    assert rank_candidates([row], profile(), {"scene_tags": ["creative"]})[0]
    row["visual"]["scenes"] = None
    assert not rank_candidates([row], profile(), {"scene_tags": ["creative"]})[0]
    # Neither a first-screen typical slot nor the light-explore slot accepts it.
    assert select_sequence([row], 10)[0] == []


@pytest.mark.parametrize("confidence", [None, "0.9", float("nan"), float("inf"), True, -1, 2])
def test_malformed_visual_confidence_is_never_approved(confidence):
    assert not valid_observation({}, {"confidence": confidence, "observations": {}}, None)


def test_native_audit_is_revision_bound_and_does_not_approve_first_pass():
    from app.closet import selfit_content_pool, _published_catalog_outfits
    from app.recommendation_visual import load_visual
    pool = selfit_content_pool()
    audit = load_visual()
    assert len(audit["garments"]) == 600 and len(audit["outfits"]) == 1169
    assert audit["human_reviewed"] is False and audit["publish_approval"] is False
    assert audit["counts"]["outfits"]["ai_candidate"] >= 15
    accepted, held = attach_visual(_published_catalog_outfits(), pool.garments, pool.outfits, audit)
    assert len(accepted) >= 15 and len(accepted) + len(held) == 1169
    changed = copy.deepcopy(audit)
    changed["outfits"][accepted[0]["outfit_id"]]["asset_sha256"] = "changed"
    assert len(attach_visual(_published_catalog_outfits(), pool.garments, pool.outfits, changed)[0]) == len(accepted) - 1
    assert all(o["visual"]["axes"] == {} for o in accepted)


def test_invalid_feedback_payload_and_nonfinite_exposure(tmp_path, monkeypatch):
    import app.storage as storage
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    with pytest.raises(HTTPException): validate_feedback([])
    with pytest.raises(HTTPException): validate_feedback({"context": []})
    with user_storage("audit-test"):
        page = create_feed(profile(), [outfit(1)], {})
        for value in (float("nan"), float("inf"), "1", 2, True):
            with pytest.raises(HTTPException):
                validate_feedback({"entity_id": "o1", "event_type": "impression", "context": {
                    "recommendation_session": page["session_id"], "visible_ratio": value, "visible_ms": 1000}})


def test_home_exposure_reads_the_article_itself():
    from pathlib import Path
    source = Path("app/closet.py").read_text()
    assert "node.dataset.todayOutfit || node.dataset.openOutfit" in source


def test_recommendation_api_keeps_formal_identity_server_owned(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    import app.storage as storage
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    real = profile(persona_id="mute", validation_enabled=False)
    monkeypatch.setattr(main, "resolve_profile", lambda uid: copy.deepcopy(real))
    monkeypatch.setattr(main, "recommend_outfits", lambda payload: {"persona_received": payload["persona"]["typeId"], "outfits": []})
    prior = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[main.get_current_user] = lambda: {"user_id": "internal-test"}
    try:
        with TestClient(main.app) as client:
            assert client.get("/closet/recommendations/profile").json()["persona_id"] == "mute"
            assert client.post("/closet/recommendations/outfits", json=[]).status_code == 422
            formal = client.post("/closet/recommendations/outfits", json={"persona": {"typeId": "loop"}})
            assert formal.status_code == 200 and formal.json()["persona_received"] == "mute"
            preview = client.post("/closet/recommendations/outfits", json={"persona": {"typeId": "loop"}, "context": {"persona_preview": True}})
            assert preview.status_code == 200 and preview.json()["persona_received"] == "loop"
            assert real["persona_id"] == "mute"
            real["persona_id"] = None
            monkeypatch.setattr(main, "recommend_outfits", lambda payload: {"persona_received": payload["persona"], "outfits": []})
            fallback = client.post("/closet/recommendations/outfits", json={"persona": {"typeId": "loop"}}).json()
            assert fallback["personalized"] is False and fallback["persona_received"] == {}
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(prior)


def test_internal_api_groups_and_cursor_contract(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    import app.storage as storage
    import app.closet as closet
    monkeypatch.setattr(storage, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(main, "resolve_profile", lambda uid: profile(validation_enabled=True))
    rows = [outfit(i, category=["pants", "skirt", "dress"][i%3], expression=["easy", "typical", "explore"][(i//3)%3]) for i in range(90)]
    monkeypatch.setattr(main, "attach_visual", lambda *args: (rows, {}))
    monkeypatch.setattr(closet, "_ensure_recommendation_feedback", lambda: {"events": []})
    prior = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[main.get_current_user] = lambda: {"user_id": "internal-test"}
    try:
        with TestClient(main.app) as client:
            first = client.post("/closet/recommendations/outfits", json={}).json()
            assert first["validation"] and len(first["carousel"]) == 4 and len(first["outfits"]) == 6
            ids = [o["outfit_id"] for o in first["carousel"] + first["outfits"]]
            assert len(set(ids)) == 10
            page_request = {"session_id": first["session_id"], "cursor": first["next_cursor"]}
            second = client.post("/closet/recommendations/outfits", json=page_request).json()
            assert len(second["outfits"]) == 6 and not set(ids) & {o["outfit_id"] for o in second["outfits"]}
            assert second == client.post("/closet/recommendations/outfits", json=page_request).json()
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(prior)


def test_visible_exposure_timer_cancels_on_exit_and_hidden_tab():
    run_js("""
const assert=require('node:assert/strict');
const {create}=require('./app/static/selfit-app/feed-exposure.js');
let notify, visibility, tick, events=0;
class Observer {constructor(fn){notify=fn;} observe(){} disconnect(){}}
const clock={setTimeout(fn){tick=fn;return 1;},clearTimeout(){tick=null;}};
const document={hidden:false,addEventListener(n,fn){visibility=fn;},removeEventListener(){}};
const node={isConnected:true};
const tracker=create({onExposure:()=>{events++;return true;},Observer,clock,document});
tracker.observe(node);
notify([{target:node,isIntersecting:true,intersectionRatio:.8}]); assert.ok(tick);
notify([{target:node,isIntersecting:true,intersectionRatio:.4}]); assert.equal(tick,null);
notify([{target:node,isIntersecting:true,intersectionRatio:.8}]);document.hidden=true;visibility();assert.equal(tick,null);
document.hidden=false;visibility();tick();assert.equal(events,1);tracker.disconnect();
""")
