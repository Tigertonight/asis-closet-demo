from app import closet
from tests.test_persona_test_mode import run_js


def test_scroll_pages_are_disjoint_exhaustible_and_persona_scoped(monkeypatch):
    outfits = [{"outfit_id": f"loop-{i}", "primary_persona": "LOOP", "items": [], "item_ids": []} for i in range(17)]
    outfits.append({"outfit_id": "mute", "primary_persona": "MUTE"})
    monkeypatch.setattr(closet, "_published_catalog_outfits", lambda: outfits)
    def unexpected():
        raise AssertionError("Preview must not read personal outfits")
    monkeypatch.setattr(closet, "list_outfits", unexpected)
    seen = []
    for size in [6, 6, 5]:
        page = closet.recommend_outfits({"persona": {"typeId": "loop"}, "context": {"persona_preview": True}, "limit": 6, "exclude_outfit_ids": seen})
        ids = [o["outfit_id"] for o in page["outfits"]]
        assert len(ids) == size
        assert not set(ids) & set(seen)
        seen.extend(ids)
        assert page["has_more"] == (len(seen) < 17)
        outfits.reverse()  # Ranking/pool order may change between requests.
    empty = closet.recommend_outfits({"persona": {"typeId": "loop"}, "context": {"persona_preview": True}, "limit": 6, "exclude_outfit_ids": seen})
    assert empty["outfits"] == [] and not empty["has_more"]


def test_append_loading_retry_and_persona_race():
    source = closet.render_selfit_demo_page()
    body = source.split('async function loadRankedOutfits(offset = 0, append = false) {', 1)[1].split('    function renderColorDots', 1)[0]
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
async function loadRankedOutfits(offset = 0, append = false) {""" + body + """
(async()=>{
 let pending = loadRankedOutfits();
 requests[0].resolve({outfits:[{outfit_id:'a'},{outfit_id:'b'}],has_more:true,next_offset:4}); await pending;
 assert.equal(requests[0].payload.limit,6);
 pending = loadRankedOutfits(0,true);
 assert.equal(state.recommendationLoading,false);
 assert.equal(state.recommendationMoreLoading,true);
 assert.equal(await loadRankedOutfits(0,true),false);
 assert.equal(requests.length,2);
 assert.deepEqual(requests[1].payload.exclude_outfit_ids,['a','b']);
 requests[1].reject(new Error('network')); await assert.rejects(pending);
 assert.deepEqual(state.outfits.map(o=>o.outfit_id),['a','b']);
 assert.ok(state.recommendationMoreError);
 pending=loadRankedOutfits(0,true);
 requests[2].resolve({outfits:[{outfit_id:'b'},{outfit_id:'c'}],has_more:true}); await pending;
 assert.deepEqual(state.outfits.map(o=>o.outfit_id),['a','b','c']);
 const stale = loadRankedOutfits(0,true);
 typeId='mute'; const fresh=loadRankedOutfits();
 requests[4].resolve({outfits:[{outfit_id:'mute'}],has_more:false}); await fresh;
 requests[3].resolve({outfits:[{outfit_id:'old-loop'}],has_more:true}); assert.equal(await stale,false);
 assert.deepEqual(state.outfits.map(o=>o.outfit_id),['mute']);
 assert.equal(state.recommendationMoreLoading,false);
 assert.equal(await loadRankedOutfits(0,true),false);
})().catch(e=>{console.error(e);process.exitCode=1});
""")


def test_scroll_listens_to_both_document_and_internal_page_and_appends_dom():
    source = closet.render_selfit_demo_page()
    assert '$("#page-home").addEventListener("scroll", onHomeFeedScroll' in source
    assert 'window.addEventListener("scroll", onHomeFeedScroll' in source
    append = source.split('function appendHomeRecommendationCards()', 1)[1].split('function renderHomeWidgets', 1)[0]
    assert 'insertAdjacentHTML("beforeend"' in append
    assert '.innerHTML =' not in append
    assert 'outfitActionBound' in source


def test_feed_load_requires_visible_home_and_user_intent_without_self_triggering_loop():
    source = closet.render_selfit_demo_page()
    load_more = source.split('async function maybeLoadMoreHomeOutfits(force = false) {', 1)[1].split(
        '    function renderTodayRecommendation', 1
    )[0]
    assert '!homePageIsActive()' in load_more
    assert 'state.homeFeedRestoring' in load_more
    assert '!force && !state.homeFeedUserIntent' in load_more
    assert 'state.homeFeedUserIntent = false;' in load_more
    assert 'state.homeFeedLastIntentPosition' in load_more
    assert 'window.requestAnimationFrame(() => maybeLoadMoreHomeOutfits())' not in source
    assert 'document.visibilityState === "visible"' in source


def test_feed_restores_scroll_and_caps_rendered_cards():
    source = closet.render_selfit_demo_page()
    assert 'const MAX_HOME_FEED_CARDS = 60;' in source
    assert 'state.outfits = nextOutfits.slice(-60);' in source
    assert 'trimHomeRecommendationCards();' in source
    assert 'cards.length - MAX_HOME_FEED_CARDS' in source
    assert 'if (leavingHome) rememberHomeScroll();' in source
    assert 'if (pageId === "page-home") restoreHomeScroll();' in source
    assert 'state.homeFeedRestoring = true;' in source
    assert 'state.homeFeedRestoring = false;' in source
    assert 'position < state.homeFeedLastIntentPosition + 24' in source


def test_feed_tracks_one_cursor_as_consumed_until_a_fresh_session():
    source = closet.render_selfit_demo_page()
    body = source.split('async function loadRankedOutfits(offset = 0, append = false) {', 1)[1].split(
        '    function renderColorDots', 1
    )[0]
    assert 'state.recommendationCursorInFlight === cursorKey' in body
    assert 'state.recommendationConsumedCursorKeys?.has(cursorKey)' in body
    assert 'state.recommendationConsumedCursorKeys?.add(cursorKey)' in body
    assert 'state.recommendationConsumedCursorKeys?.clear()' in body
