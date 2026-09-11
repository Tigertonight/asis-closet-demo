from scripts.batch_female_nano_presets import garment_only_context, prompt_for


def test_outfit_pose_notes_cannot_override_fixed_selfie_pose():
    items = [{"name": "白色半身裙", "wearing_method": "高腰穿着，双手插入前侧贴袋。",
              "visible_details": ["双手插入前侧贴袋", "裙身直筒垂落至膝下", "贴袋朝外"]},
             {"name": "白色手套", "wearing_method": "手套佩戴至前臂，袖口盖住手套上缘。"},
             {"name": "手提包", "wearing_method": "用下垂手提握包柄"}]
    cleaned = garment_only_context(items)
    assert "双手插入" not in str(cleaned)
    assert cleaned[0]["visible_details"] == ["裙身直筒垂落至膝下", "贴袋朝外"]
    assert "高腰穿着" in cleaned[0]["wearing_method"]
    assert cleaned[1:] == items[1:]
    assert "双手插入" in str(items), "Source descriptions must remain intact"
    prompt = prompt_for({"plan": {"title": "测试"}, "itemContext": items})
    assert "双手插入" not in prompt
    assert prompt.index("FINAL POSE LOCK") > prompt.index("白色半身裙")


def test_seated_and_two_hand_source_pose_preserves_garment_structure():
    items = [{"name": "针织长裙", "wearing_method": "单穿贴身长裙，坐姿下裙摆铺在腿部与地面"},
             {"name": "风衣", "visible_details": ["双手置于侧袋", "翻领自然展开"]},
             {"name": "交叠针织衫", "visible_details": ["前身交叉边线", "V 形领口"]},
             {"name": "托特包", "wearing_method": "双手提拎于身前"},
             {"name": "凉鞋", "visible_details": ["足背交叉细带", "踝带扣合"]}]
    cleaned = garment_only_context(items)
    assert cleaned[0]["wearing_method"] == "单穿贴身长裙，"
    assert cleaned[1]["visible_details"] == ["翻领自然展开"]
    assert cleaned[2] == items[2]
    assert cleaned[3]["wearing_method"] == "由原本下垂的非持手机手提握包柄"
    assert cleaned[4] == items[4]
    assert items[0]["wearing_method"].endswith("坐姿下裙摆铺在腿部与地面")
