from scripts.sync_selfit_personality_database import _common_item


def test_hair_card_uses_calibrated_hair_name_and_keeps_note_title_separate() -> None:
    row = {
        "展示位次": 1,
        "发型名称": "笔记标题被误写进名称列",
        "笔记标题": "显脸小发型分享",
        "笔记ItemID": "note-1",
        "文件名": "hair-1.jpg",
        "博主": "发型作者",
    }

    item = _common_item(
        row,
        type_id="mute",
        kind="hair",
        hair_names={"item:note-1": "外翘初恋发"},
    )

    assert item["name"] == "外翘初恋发"
    assert item["sourceTitle"] == "显脸小发型分享"
    assert item["byline"] == "@发型作者"


def test_hair_card_never_falls_back_to_note_title_when_name_is_missing() -> None:
    item = _common_item(
        {
            "展示位次": 2,
            "发型名称": "",
            "笔记标题": "这不是发型类型",
            "笔记ItemID": "note-2",
            "文件名": "hair-2.jpg",
        },
        type_id="mute",
        kind="hair",
        hair_names={},
    )

    assert item["name"] == "待补充发型名称 02"
    assert item["sourceTitle"] == "这不是发型类型"
