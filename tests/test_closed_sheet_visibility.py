from app import closet


def test_closed_panels_are_hidden_not_only_translated_offscreen():
    html = closet.render_selfit_demo_page()
    assert '.sheet:not(.open), .session-sidebar:not(.open) { visibility: hidden; }' in html
    assert '.sheet.open { transform: translate(-50%, 0); }' in html
