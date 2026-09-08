"""Consumer suit summary; classification remains in resolve_suit_profile."""
from app.selfit_recommend import resolve_suit_profile

DESCRIPTIONS = {
    '椭圆脸': ('额头与颧骨宽度接近，下颌收窄，轮廓连接较圆润。', '领口选择比较灵活，可以从方领、V 领试起。'),
    '圆脸': ('面部长宽较接近，脸颊线条柔和。', '可以试试 V 领或纵向耳饰，给轮廓增加延伸感。'),
    '方脸': ('额头和下颌宽度较接近，下颌线条清晰。', '圆领、弧形耳饰能与清晰的下颌线形成柔和呼应。'),
    '心形脸': ('上庭相对舒展，下颌逐渐收窄。', '可以试试圆领或下端稍宽的耳饰，让上下比例更平衡。'),
    '菱形脸': ('颧骨相对突出，额头和下颌较窄。', '可以用柔和领口、蓬松发型呼应轮廓。'),
    '冷白肤': ('肤色较明亮，底调偏冷。', '可以从冷调浅色、蓝灰色和柔和粉色开始试穿。'),
    '暖白肤': ('肤色较明亮，底调偏暖。', '可以试试奶油白、浅杏和温暖的浅棕色。'),
    '中性自然肤': ('肤色明度自然，冷暖倾向较平衡。', '从柔和中性色开始，比较不同配色在自然光下的效果。'),
    '暖黄肤': ('肤色呈现自然暖调。', '可以试试米白、暖棕和柔和的大地色。'),
    '橄榄肤': ('肤色带有橄榄底调。', '可以试试柔和米色、橄榄绿和深棕。'),
    '小麦色': ('肤色较深，呈现自然的小麦色调。', '可以试试奶油白、陶土色，用明暗对比突出气色。'),
    '梨型': ('胯部相对肩部更宽。', '可以用有结构的上装搭配自然垂坠的下装。'),
    '倒三角型': ('肩部相对胯部更宽。', '试试简洁上装与略有量感的下装，平衡整体比例。'),
    '矩型': ('肩、腰、胯的宽度变化较小。', '用腰线、叠穿和不同材质增加轮廓层次。'),
    '沙漏型': ('肩胯比例较接近，腰线相对明显。', '可以试试顺着腰线的剪裁，让原有比例自然呈现。'),
    '苹果型': ('身体量感较集中在腰腹，上下肢相对轻盈。', '试试有垂感的面料和清晰纵向线条，保留舒适空间。'),
}

def _photo_analysis(record, kind, attribute_name):
    """Original photo inference, independent of any later manual correction."""
    photo = (record.get('photos') or {}).get(kind) or {}
    attribute = (photo.get('attributes') or {}).get(attribute_name)
    if photo.get('status') != 'accepted' or not attribute:
        return None
    analysis = {'label': attribute.get('label'), 'confidence': attribute.get('confidence')}
    evidence = attribute.get('evidence') or {}
    if attribute_name == 'face_shape':
        analysis['candidates'] = [
            {'label': candidate['label'], 'score': candidate['score']}
            for candidate in (attribute.get('candidates') or [])
        ]
        measurements = evidence.get('features') or {}
        analysis['metrics'] = {
            'lengthWidthRatio': measurements.get('length_width_ratio'),
            'jawCheekRatio': measurements.get('jaw_cheek_ratio'),
            'foreheadCheekRatio': measurements.get('forehead_cheek_ratio'),
        }
    elif attribute_name == 'skin_tone':
        analysis['metrics'] = {'lStar': evidence.get('l_star'), 'itaDegrees': evidence.get('ita_deg')}
    return analysis


def suit_summary(record):
    resolved = resolve_suit_profile(record)
    fields = [('skin', 'skin', '肤色'), ('faceShape', 'face_shape', '脸型'), ('bodyShape', 'body_shape', '身材比例')]
    features = []
    for key, source_key, title in fields:
        value = resolved.get(source_key)
        description, advice = DESCRIPTIONS.get(value, ('照片中还看不清这项特点，你可以手动选择。', '选择更接近自己的特点，帮助我们完善推荐。'))
        features.append(dict(key=key, title=title, value=value, description=description, advice=advice,
                             source='manual' if (record.get('manual') or {}).get(key) else ('photo' if value else 'unknown'),
                             photoAnalysis=_photo_analysis(record, 'body' if key == 'bodyShape' else 'face',
                                                           'skin_tone' if key == 'skin' else source_key)))
    return {'revision': record.get('revision', 1), 'features': features,
            'photos': {kind: bool((record.get('photos', {}).get(kind) or {}).get('status') == 'accepted') for kind in ('face', 'body')}}
