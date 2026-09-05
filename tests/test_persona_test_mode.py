import json
import subprocess
from pathlib import Path

from app import closet

ROOT = Path(__file__).resolve().parents[1]


def run_js(code):
    result = subprocess.run(["node", "-"], input=code, text=True, capture_output=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr


def test_five_taps_toggle_and_restore_without_changing_real_persona():
    run_js("""
const assert = require('node:assert/strict');
const {create} = require('./app/static/selfit-app/persona-test-mode.js');
const test = create(['loop','mute','noir']);
const real = {typeId:'loop'};
for (let i=0;i<4;i++) assert.equal(test.tap('me',i*200,real.typeId),false);
assert.equal(test.enabled,false);
assert.equal(test.tap('me',800,real.typeId),true);
assert.equal(test.typeId,'loop');
assert.equal(test.select('invalid'),false);
assert.equal(test.select('noir'),true);
assert.equal(real.typeId,'loop');
const refreshed = create(['loop','mute','noir']);
refreshed.restore(JSON.parse(JSON.stringify(test.snapshot())));
assert.equal(refreshed.typeId,'noir');
for (let i=0;i<5;i++) refreshed.tap('me',1000+i*200,real.typeId);
assert.equal(refreshed.enabled,false);
assert.equal(refreshed.typeId,'');
assert.equal(refreshed.select('mute'),false);
refreshed.restore({enabled:true,typeId:'unknown'});
assert.equal(refreshed.enabled,false);
const timeout = create(['loop']);
for (let i=0;i<4;i++) timeout.tap('me',i*100,'loop');
assert.equal(timeout.tap('me',7000,'loop'),false);
timeout.tap('home',7050,'loop');
for (let i=0;i<4;i++) assert.equal(timeout.tap('me',7100+i*100,'loop'),false);
assert.equal(timeout.tap('me',7500,'loop'),true);
""")


def test_out_of_order_recommendations_cannot_replace_selected_persona():
    source = closet.render_selfit_demo_page()
    function = source.split("    async function loadRankedOutfits(offset = 0, append = false) {", 1)[1].split("    function renderColorDots", 1)[0]
    run_js("""
const assert = require('node:assert/strict');
const state = {recommendationRequest:0,outfits:[],aiBrief:''};
const personaTestMode = {enabled:true};
let typeId = 'loop';
const personaRecommendationPayload = () => ({typeId});
const renderPersonaTestPanel = () => {};
const $ = () => ({textContent:''});
const requests = [];
const fetchJSON = (url, options) => new Promise((resolve,reject) => requests.push({resolve,reject,payload:JSON.parse(options.body)}));
async function loadRankedOutfits(offset = 0, append = false) {""" + function + """
(async () => {
 const first = loadRankedOutfits();
 typeId = 'noir';
 const second = loadRankedOutfits();
 assert.equal(requests[0].payload.persona.typeId,'loop');
 assert.equal(requests[1].payload.persona.typeId,'noir');
 assert.equal(requests[1].payload.context.persona_preview,true);
 requests[1].resolve({outfits:[{outfit_id:'noir'}],next_offset:4});
 await second;
 requests[0].resolve({outfits:[{outfit_id:'loop'}],next_offset:8});
 assert.equal(await first,false);
 assert.equal(state.outfits[0].outfit_id,'noir');
 assert.equal(state.recommendationOffset,4);
 const failed = loadRankedOutfits();
 requests[2].reject(new Error('network'));
 await assert.rejects(failed);
 assert.equal(state.recommendationLoading,false);
 assert.ok(state.recommendationError);
 personaTestMode.enabled = false;
 typeId = 'loop';
 const formal = loadRankedOutfits();
 assert.equal(requests[3].payload.context.persona_preview,false);
 assert.equal(requests[3].payload.persona.typeId,'loop');
 requests[3].resolve({outfits:[],next_offset:0}); await formal;
})().catch(error => { console.error(error); process.exitCode=1; });
""")


def test_all_16_preview_personas_use_recommendation_ranking_without_feedback(monkeypatch):
    templates = json.loads((ROOT / "app/static/selfit/data/personality-report-templates.v1.json").read_text())["types"]
    outfits = [{"outfit_id": code, "primary_persona": code.upper(), "items": [], "item_ids": []} for code in templates]
    monkeypatch.setattr(closet, "_published_catalog_outfits", lambda: outfits)
    def unexpected(*args):
        raise AssertionError("Preview must not consume real recommendation feedback")
    monkeypatch.setattr(closet, "_ensure_recommendation_feedback", unexpected)
    monkeypatch.setattr(closet, "_feedback_profile", unexpected)
    monkeypatch.setattr(closet, "list_outfits", unexpected)
    assert len(templates) == 16
    for code in templates:
        result = closet.recommend_outfits({"persona": {"typeId": code}, "context": {"persona_preview": True}})
        assert result["outfits"][0]["outfit_id"] == code
        assert result["total"] == 1


def test_formal_recommendations_still_use_feedback(monkeypatch):
    outfits = [{"outfit_id": code, "primary_persona": code, "items": [], "item_ids": []} for code in ["loop", "mute"]]
    monkeypatch.setattr(closet, "list_outfits", lambda: {"outfits": outfits})
    monkeypatch.setattr(closet, "_published_catalog_outfits", lambda: outfits)
    monkeypatch.setattr(closet, "_ensure_recommendation_feedback", lambda: {"events": []})
    monkeypatch.setattr(closet, "_feedback_profile", lambda key: {"counts": {"like": 10 if key == "mute" else 0}})
    assert closet.recommend_outfits({"persona": {"typeId": "loop"}})["outfits"][0]["outfit_id"] == "mute"
    assert closet.recommend_outfits({"persona": {"typeId": "loop"}, "context": {"persona_preview": True}})["outfits"][0]["outfit_id"] == "loop"


def test_hydrated_demo_does_not_reserve_personal_priority(monkeypatch):
    demo = {"outfit_id": "w_outfit_commute_01", "user_id": "user", "rank": 1}
    personal = {"outfit_id": "my-own-outfit", "user_id": "user", "rank": 0}
    catalog = {"outfit_id": "outfit_loop_master_01", "primary_persona": "LOOP", "rank": 100}
    monkeypatch.setattr(closet, "list_outfits", lambda: {"outfits": [demo, personal]})
    monkeypatch.setattr(closet, "_published_catalog_outfits", lambda: [catalog])
    monkeypatch.setattr(closet, "_ensure_recommendation_feedback", lambda: {"events": []})
    monkeypatch.setattr(closet, "_feedback_profile", lambda key: {})
    monkeypatch.setattr(closet, "_score_outfit_for_persona", lambda o, *args: {"score": o["rank"]})
    assert [o["outfit_id"] for o in closet.recommend_outfits({"limit": 2})["outfits"]] == ["my-own-outfit", "outfit_loop_master_01"]
    preview = {"persona": {"typeId": "loop"}, "context": {"persona_preview": True}}
    assert [o["outfit_id"] for o in closet.recommend_outfits(preview)["outfits"]] == ["outfit_loop_master_01"]
    preview["persona"]["typeId"] = "missing"
    assert closet.recommend_outfits(preview)["outfits"] == []


def test_preview_empty_state_never_falls_back_to_demo_or_reference_photos():
    source = closet.render_selfit_demo_page()
    assert 'visibleCards.length || personaTestMode.enabled || state.recommendationValidation ? visibleCards : buildSyntheticOutfits()' in source
    today = source.split('function renderTodayRecommendation(cards)', 1)[1].split('function todayCardHTML', 1)[0]
    assert today.index('if (personaTestMode.enabled || state.recommendationValidation)') < today.index('const inspiration =')


def test_preview_controls_hidden_and_feedback_not_persisted():
    source = closet.render_selfit_demo_page()
    assert 'id="personaTestPanel" class="persona-test-panel" hidden' in source
    assert '<dialog id="personaTestDialog"' in source
    feedback_function = source.split('async function recordRecommendationEvent(',1)[1].split('function openRecommendationFeedback',1)[0]
    assert feedback_function.index('if (personaTestMode.enabled) return true') < feedback_function.index('await fetchJSON')
    preview_functions = source.split('function recommendationPersona()',1)[1].split('function stylePersonaOutfits()',1)[0]
    assert 'state.stylePersona =' not in preview_functions
    assert 'stylePersonaStoreKey' not in preview_functions
    assert 'history.' not in preview_functions
