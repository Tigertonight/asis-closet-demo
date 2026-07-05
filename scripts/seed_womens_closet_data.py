from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import closet
from app.storage import storage_context


SEED_SOURCE = "womens_seed"
CTX = storage_context()
LEGACY_SEED_DIR = closet.CLOSET_OUTPUT_DIR / "womens_seed"
SEED_DIR = CTX.closet_output_dir / "womens_seed"
CONTACT_SHEET_DIR = SEED_DIR / "contact_sheets"

CONTACT_SHEETS = [
    "ig_06ba6bfc00fe6438016a489d6f06ac8191a494ecf393bf3536.png",
    "ig_06ba6bfc00fe6438016a489dbb54288191918fe69d5bebfb82.png",
    "ig_06ba6bfc00fe6438016a489df9a0088191ac16d9cf6e6e349a.png",
    "ig_06ba6bfc00fe6438016a489e40a3248191b53ca436674b4ba6.png",
    "ig_06ba6bfc00fe6438016a489ea4f3548191b8873426aba0768a.png",
    "ig_06ba6bfc00fe6438016a489f0bd18c8191869ecc6f3e2172aa.png",
    "ig_06ba6bfc00fe6438016a489f5592ec8191b85ee728175aa7ef.png",
    "ig_06ba6bfc00fe6438016a489f875c7c819191119bd665c9a5fd.png",
    "ig_06ba6bfc00fe6438016a489ffb05dc8191ae15c528efae9e92.png",
    "ig_06ba6bfc00fe6438016a48a052aa688191aa778b923c949779.png",
    "ig_02785c2863b272f2016a48a1381ea881918ef5dd23d9262254.png",
]


def item(
    item_id: str,
    sheet: int,
    cell: int,
    category: str,
    label: str,
    colors: list[str],
    tags: list[str],
    material: list[str] | None = None,
    fit: str = "regular",
    sleeve: str = "unknown",
    neckline: str = "unknown",
    pattern: str = "solid",
    subcategory: str | None = None,
    slot: str | None = None,
) -> dict[str, Any]:
    return {
        "item_id": f"w_{item_id}",
        "sheet": sheet,
        "cell": cell,
        "category": category,
        "label": label,
        "colors": colors,
        "tags": tags,
        "material": material or [],
        "fit": fit,
        "sleeve": sleeve,
        "neckline": neckline,
        "pattern": pattern,
        "subcategory": subcategory,
        "slot": slot,
    }


ITEM_SPECS = [
    item("top_white_shirt", 0, 0, "top", "白色通勤衬衫", ["白色"], ["通勤", "清爽", "基础款"], ["cotton"], "regular", "long_sleeve", "shirt_collar"),
    item("top_blue_striped_shirt", 0, 1, "top", "蓝白条纹衬衫", ["蓝白"], ["通勤", "学院", "宽松"], ["cotton"], "relaxed", "long_sleeve", "shirt_collar", "stripe"),
    item("top_ivory_knit_tee", 0, 2, "top", "米白针织短袖", ["米白"], ["温柔", "基础款", "显气色"], ["knit"], "slim", "short_sleeve", "crew"),
    item("top_rose_cardigan", 0, 3, "top", "柔粉修身开衫", ["柔粉"], ["约会", "温柔", "针织"], ["knit"], "slim", "long_sleeve", "v_neck"),
    item("top_black_square_tank", 0, 4, "top", "黑色方领背心", ["黑色"], ["显瘦", "内搭", "轻辣"], ["cotton_blend"], "slim", "sleeveless", "square"),
    item("top_denim_cropped_jacket", 0, 5, "top", "浅蓝牛仔短外套", ["浅蓝"], ["周末", "休闲", "短款"], ["denim"], "regular", "long_sleeve", "jacket"),
    item("top_oat_linen_blazer", 0, 6, "top", "燕麦色亚麻西装", ["燕麦色"], ["通勤", "轻熟", "外套"], ["linen"], "regular", "long_sleeve", "blazer"),
    item("top_yellow_short_jacket", 0, 7, "top", "奶黄色短外套", ["奶黄色"], ["春夏", "亮色", "甜酷"], ["cotton_blend"], "regular", "long_sleeve", "jacket"),
    item("top_cream_tie_blouse", 1, 0, "top", "奶油系带法式衫", ["奶油白"], ["约会", "法式", "温柔"], ["chiffon"], "regular", "long_sleeve", "tie_neck"),
    item("top_black_blazer", 1, 1, "top", "黑色利落西装", ["黑色"], ["面试", "通勤", "正式"], ["suiting"], "regular", "long_sleeve", "blazer"),
    item("top_navy_knit_polo", 1, 2, "top", "藏蓝针织 polo", ["藏蓝"], ["学院", "周末", "显瘦"], ["knit"], "regular", "short_sleeve", "polo"),
    item("top_lavender_cardigan", 1, 3, "top", "薰衣草薄开衫", ["薰衣草紫"], ["温柔", "防晒", "春夏"], ["knit"], "regular", "long_sleeve", "v_neck"),
    item("top_coral_blouse", 1, 4, "top", "珊瑚粉短袖衫", ["珊瑚粉"], ["聚会", "显气色", "轻熟"], ["viscose"], "regular", "short_sleeve", "round"),
    item("top_camel_trench_jacket", 1, 5, "top", "驼色短风衣外套", ["驼色"], ["旅行", "通勤", "外套"], ["trench"], "regular", "long_sleeve", "jacket"),
    item("top_white_oversized_tee", 1, 6, "top", "白色宽松 T 恤", ["白色"], ["周末", "休闲", "基础款"], ["cotton"], "relaxed", "short_sleeve", "crew"),
    item("top_mocha_hoodie", 1, 7, "top", "摩卡色软糯卫衣", ["摩卡"], ["居家", "舒适", "休闲"], ["fleece"], "relaxed", "long_sleeve", "hoodie"),
    item("top_sage_linen_vest", 8, 0, "top", "鼠尾草绿亚麻马甲", ["鼠尾草绿"], ["层次", "旅行", "轻熟"], ["linen"], "regular", "sleeveless", "v_neck"),
    item("top_blue_cropped_sweater", 8, 1, "top", "雾蓝短款毛衣", ["雾蓝"], ["周末", "短款", "温柔"], ["knit"], "regular", "long_sleeve", "crew"),
    item("bottom_straight_jeans", 2, 0, "bottom", "直筒牛仔裤", ["牛仔蓝"], ["休闲", "显腿直", "基础款"], ["denim"], "regular"),
    item("bottom_pale_wide_pants", 2, 1, "bottom", "浅蓝阔腿裤", ["浅蓝"], ["通勤", "清爽", "宽松"], ["suiting"], "relaxed"),
    item("bottom_black_suit_pants", 2, 2, "bottom", "黑色西装裤", ["黑色"], ["面试", "通勤", "正式"], ["suiting"], "regular"),
    item("bottom_khaki_bermuda", 2, 3, "bottom", "卡其百慕大短裤", ["卡其"], ["周末", "夏天", "短裤"], ["cotton"], "regular"),
    item("bottom_charcoal_jogger", 2, 4, "bottom", "炭灰运动裤", ["炭灰"], ["运动", "户外", "舒适"], ["jersey"], "relaxed"),
    item("bottom_indigo_flare_jeans", 2, 5, "bottom", "深蓝微喇牛仔裤", ["深蓝"], ["复古", "显腿长", "休闲"], ["denim"], "regular"),
    item("bottom_ivory_pleated_pants", 2, 6, "bottom", "象牙白褶阔腿裤", ["象牙白"], ["旅行", "温柔", "宽松"], ["suiting"], "relaxed"),
    item("bottom_coffee_trousers", 2, 7, "bottom", "咖啡色直筒裤", ["咖啡色"], ["通勤", "秋冬", "基础款"], ["suiting"], "regular"),
    item("bottom_olive_cargo", 8, 5, "bottom", "橄榄绿工装裤", ["橄榄绿"], ["户外", "旅行", "休闲"], ["cotton"], "relaxed"),
    item("bottom_pink_pleated_pants", 9, 5, "bottom", "浅粉褶裥长裤", ["浅粉"], ["温柔", "聚会", "宽松"], ["suiting"], "relaxed"),
    item("skirt_black_a_line", 3, 0, "skirt", "黑色 A 字短裙", ["黑色"], ["显瘦", "甜酷", "短裙"], ["suiting"], "regular"),
    item("skirt_navy_pleated", 3, 1, "skirt", "藏蓝百褶半裙", ["藏蓝"], ["学院", "显瘦", "半身裙"], ["polyester"], "regular"),
    item("skirt_champagne_satin", 3, 2, "skirt", "香槟缎面半裙", ["香槟色"], ["约会", "轻熟", "垂坠"], ["satin"], "regular"),
    item("skirt_denim_midi", 3, 3, "skirt", "蓝色牛仔中裙", ["牛仔蓝"], ["周末", "休闲", "中裙"], ["denim"], "regular"),
    item("skirt_charcoal_pencil", 3, 4, "skirt", "炭灰包臀半裙", ["炭灰"], ["通勤", "正式", "显瘦"], ["suiting"], "slim"),
    item("skirt_cream_circle", 3, 5, "skirt", "奶油伞裙", ["奶油白"], ["温柔", "约会", "大裙摆"], ["cotton_blend"], "regular"),
    item("skirt_rose_floral", 3, 6, "skirt", "玫瑰碎花雪纺裙", ["玫瑰粉"], ["旅行", "度假", "碎花"], ["chiffon"], "regular", pattern="floral"),
    item("skirt_camel_wrap", 3, 7, "skirt", "驼色裹身半裙", ["驼色"], ["轻熟", "通勤", "法式"], ["suiting"], "regular"),
    item("dress_little_black", 4, 0, "dress", "小黑无袖连衣裙", ["黑色"], ["约会", "显瘦", "宴会"], ["crepe"], "slim", "sleeveless"),
    item("dress_cream_shirt", 4, 1, "dress", "奶油衬衫裙", ["奶油白"], ["通勤", "旅行", "清爽"], ["cotton"], "regular", "short_sleeve", "shirt_collar"),
    item("dress_rose_floral", 4, 2, "dress", "玫瑰碎花中长裙", ["玫瑰粉"], ["约会", "度假", "碎花"], ["chiffon"], "regular", "short_sleeve", pattern="floral"),
    item("dress_taupe_knit", 4, 3, "dress", "灰棕针织直筒裙", ["灰棕"], ["居家", "温柔", "显身形"], ["knit"], "slim", "sleeveless"),
    item("dress_navy_office", 4, 4, "dress", "藏蓝通勤连衣裙", ["藏蓝"], ["通勤", "面试", "正式"], ["suiting"], "regular", "sleeveless"),
    item("dress_champagne_guest", 4, 5, "dress", "香槟宾客吊带裙", ["香槟色"], ["婚礼", "宴会", "轻礼服"], ["satin"], "slim", "sleeveless"),
    item("dress_sea_vacation", 4, 6, "dress", "海蓝度假吊带裙", ["海蓝"], ["旅行", "度假", "清爽"], ["cotton_blend"], "regular", "sleeveless"),
    item("dress_white_eyelet", 4, 7, "dress", "白色镂空夏日裙", ["白色"], ["周末", "度假", "甜美"], ["cotton"], "regular", "sleeveless", pattern="eyelet"),
    item("dress_black_wrap", 10, 0, "dress", "黑色长袖裹身裙", ["黑色"], ["约会", "显瘦", "轻熟"], ["jersey"], "slim", "long_sleeve", "v_neck"),
    item("dress_blue_formal", 10, 1, "dress", "浅蓝正式中长裙", ["浅蓝"], ["婚礼", "汇报", "优雅"], ["crepe"], "regular", "short_sleeve"),
    item("shoes_black_loafers", 5, 0, "shoes", "黑色乐福鞋", ["黑色"], ["通勤", "舒适", "皮鞋"], ["leather"], "regular"),
    item("shoes_ivory_mary_jane", 5, 1, "shoes", "象牙白玛丽珍", ["象牙白"], ["约会", "温柔", "平底"], ["leather"], "regular"),
    item("shoes_black_pointed_heels", 5, 2, "shoes", "黑色尖头低跟鞋", ["黑色"], ["面试", "通勤", "精致"], ["leather"], "regular"),
    item("shoes_white_sneakers", 5, 3, "shoes", "白色小白鞋", ["白色"], ["周末", "旅行", "轻便"], ["leather"], "regular"),
    item("shoes_silver_sneakers", 5, 4, "shoes", "银色运动鞋", ["银色"], ["运动", "户外", "休闲"], ["mesh"], "regular"),
    item("shoes_tan_sandals", 5, 5, "shoes", "棕色绑带凉鞋", ["棕色"], ["度假", "夏天", "轻便"], ["leather"], "regular"),
    item("shoes_black_ankle_boots", 5, 6, "shoes", "黑色短靴", ["黑色"], ["秋冬", "甜酷", "显高"], ["leather"], "regular"),
    item("shoes_blush_ballet", 5, 7, "shoes", "腮红粉芭蕾鞋", ["腮红粉"], ["温柔", "约会", "平底"], ["leather"], "regular"),
    item("shoes_cream_slingback", 10, 2, "shoes", "奶油色后空低跟", ["奶油白"], ["婚礼", "通勤", "精致"], ["leather"], "regular"),
    item("shoes_silver_party_heels", 10, 3, "shoes", "银色派对高跟", ["银色"], ["宴会", "聚会", "亮色"], ["metallic"], "regular"),
    item("bag_cream_tote", 6, 0, "bag", "奶油帆布托特", ["奶油白"], ["通勤", "大包", "轻便"], ["canvas"], "regular"),
    item("bag_black_work", 6, 1, "bag", "黑色结构通勤包", ["黑色"], ["通勤", "面试", "正式"], ["leather"], "regular"),
    item("bag_burgundy_shoulder", 6, 2, "bag", "酒红腋下包", ["酒红"], ["约会", "复古", "亮点"], ["leather"], "regular"),
    item("bag_ivory_chain", 6, 3, "bag", "象牙白链条小包", ["象牙白"], ["婚礼", "宴会", "精致"], ["leather"], "regular"),
    item("bag_tan_crossbody", 6, 4, "bag", "棕色小方包", ["棕色"], ["旅行", "周末", "斜挎"], ["leather"], "regular"),
    item("bag_straw_vacation", 6, 5, "bag", "草编度假托特", ["草编色"], ["旅行", "度假", "大包"], ["straw"], "regular"),
    item("bag_silver_evening", 6, 6, "bag", "银色迷你晚宴包", ["银色"], ["宴会", "聚会", "亮色"], ["metallic"], "regular"),
    item("bag_yellow_tote", 6, 7, "bag", "柔黄小托特", ["柔黄"], ["周末", "亮色", "可爱"], ["leather"], "regular"),
    item("acc_cream_beret", 7, 0, "accessory", "奶油色贝雷帽", ["奶油白"], ["帽子", "法式", "约会"], ["wool"], subcategory="hat", slot="hat"),
    item("acc_navy_cap", 7, 1, "accessory", "藏蓝棒球帽", ["藏蓝"], ["帽子", "运动", "周末"], ["cotton"], subcategory="hat", slot="hat"),
    item("acc_straw_hat", 7, 2, "accessory", "自然色草帽", ["草编色"], ["帽子", "旅行", "防晒"], ["straw"], subcategory="hat", slot="hat"),
    item("acc_rose_silk_scarf", 7, 3, "accessory", "玫瑰色真丝方巾", ["玫瑰粉"], ["丝巾", "精致", "通勤"], ["silk"], subcategory="scarf", slot="scarf"),
    item("acc_black_belt", 7, 4, "accessory", "黑色细腰带", ["黑色"], ["腰带", "显腰线", "通勤"], ["leather"], subcategory="belt", slot="accessory"),
    item("acc_black_sunglasses", 7, 5, "accessory", "黑色墨镜", ["黑色"], ["墨镜", "旅行", "氛围"], ["acetate"], subcategory="sunglasses", slot="accessory"),
    item("acc_cream_socks", 7, 6, "accessory", "奶油色短袜", ["奶油白"], ["袜子", "学院", "细节"], ["cotton"], subcategory="socks", slot="socks"),
    item("acc_gold_necklace", 7, 7, "accessory", "金色细项链", ["金色"], ["项链", "精致", "日常"], ["metal"], subcategory="necklace", slot="accessory"),
]


OUTFITS = [
    ("w_outfit_commute_01", "周一清爽通勤", ["w_top_white_shirt", "w_bottom_pale_wide_pants", "w_shoes_black_loafers", "w_bag_cream_tote"], ["通勤"]),
    ("w_outfit_commute_02", "正式会议黑白套装", ["w_top_black_blazer", "w_top_ivory_knit_tee", "w_bottom_black_suit_pants", "w_shoes_black_pointed_heels", "w_bag_black_work"], ["通勤", "会议"]),
    ("w_outfit_commute_03", "轻熟燕麦办公室", ["w_top_oat_linen_blazer", "w_top_black_square_tank", "w_bottom_coffee_trousers", "w_shoes_cream_slingback", "w_bag_tan_crossbody"], ["通勤", "轻熟"]),
    ("w_outfit_commute_04", "周五条纹牛仔通勤", ["w_top_blue_striped_shirt", "w_bottom_straight_jeans", "w_shoes_white_sneakers", "w_bag_cream_tote"], ["通勤", "周五"]),
    ("w_outfit_commute_05", "雨天短风衣通勤", ["w_top_camel_trench_jacket", "w_bottom_black_suit_pants", "w_shoes_black_ankle_boots", "w_bag_black_work"], ["通勤", "雨天"]),
    ("w_outfit_commute_06", "柔粉不费力上班", ["w_top_rose_cardigan", "w_skirt_charcoal_pencil", "w_shoes_ivory_mary_jane", "w_bag_ivory_chain"], ["通勤", "温柔"]),
    ("w_outfit_commute_07", "藏蓝针织学院通勤", ["w_top_navy_knit_polo", "w_skirt_navy_pleated", "w_shoes_black_loafers", "w_bag_black_work"], ["通勤", "学院"]),
    ("w_outfit_commute_08", "丝巾点睛通勤", ["w_top_cream_tie_blouse", "w_bottom_ivory_pleated_pants", "w_shoes_black_pointed_heels", "w_bag_burgundy_shoulder", "w_acc_rose_silk_scarf"], ["通勤", "精致"]),
    ("w_outfit_date_01", "晚餐约会小黑裙", ["w_dress_little_black", "w_shoes_silver_party_heels", "w_bag_silver_evening", "w_acc_gold_necklace"], ["约会", "晚餐"]),
    ("w_outfit_date_02", "展览咖啡法式感", ["w_top_cream_tie_blouse", "w_skirt_champagne_satin", "w_shoes_blush_ballet", "w_bag_burgundy_shoulder", "w_acc_cream_beret"], ["约会", "看展"]),
    ("w_outfit_date_03", "温柔碎花午后", ["w_dress_rose_floral", "w_shoes_ivory_mary_jane", "w_bag_yellow_tote", "w_acc_gold_necklace"], ["约会", "周末"]),
    ("w_outfit_date_04", "生日聚会珊瑚粉", ["w_top_coral_blouse", "w_skirt_black_a_line", "w_shoes_silver_party_heels", "w_bag_silver_evening"], ["聚会", "生日派对"]),
    ("w_outfit_date_05", "二人世界针织裙", ["w_dress_taupe_knit", "w_shoes_blush_ballet", "w_bag_ivory_chain", "w_acc_gold_necklace"], ["约会", "温柔"]),
    ("w_outfit_date_06", "黑色裹身轻熟约会", ["w_dress_black_wrap", "w_shoes_black_pointed_heels", "w_bag_burgundy_shoulder"], ["约会", "轻熟"]),
    ("w_outfit_weekend_01", "城市漫游牛仔外套", ["w_top_denim_cropped_jacket", "w_top_white_oversized_tee", "w_skirt_denim_midi", "w_shoes_white_sneakers", "w_bag_tan_crossbody"], ["周末", "City walk"]),
    ("w_outfit_weekend_02", "Brunch 奶黄短外套", ["w_top_yellow_short_jacket", "w_skirt_cream_circle", "w_shoes_ivory_mary_jane", "w_bag_yellow_tote"], ["周末", "Brunch"]),
    ("w_outfit_weekend_03", "棒球帽轻运动", ["w_top_white_oversized_tee", "w_bottom_khaki_bermuda", "w_shoes_silver_sneakers", "w_bag_cream_tote", "w_acc_navy_cap"], ["周末", "轻运动"]),
    ("w_outfit_weekend_04", "雾蓝短毛衣逛街", ["w_top_blue_cropped_sweater", "w_bottom_indigo_flare_jeans", "w_shoes_blush_ballet", "w_bag_tan_crossbody"], ["周末", "逛街"]),
    ("w_outfit_weekend_05", "薰衣草温柔看展", ["w_top_lavender_cardigan", "w_skirt_champagne_satin", "w_shoes_ivory_mary_jane", "w_bag_ivory_chain"], ["周末", "看展"]),
    ("w_outfit_travel_01", "海边度假蓝裙", ["w_dress_sea_vacation", "w_shoes_tan_sandals", "w_bag_straw_vacation", "w_acc_straw_hat"], ["旅行", "度假"]),
    ("w_outfit_travel_02", "机场舒适卫衣", ["w_top_mocha_hoodie", "w_bottom_charcoal_jogger", "w_shoes_silver_sneakers", "w_bag_cream_tote", "w_acc_navy_cap"], ["旅行", "机场"]),
    ("w_outfit_travel_03", "城市旅行亚麻马甲", ["w_top_sage_linen_vest", "w_bottom_ivory_pleated_pants", "w_shoes_white_sneakers", "w_bag_tan_crossbody"], ["旅行", "城市漫游"]),
    ("w_outfit_travel_04", "周边短途工装", ["w_top_camel_trench_jacket", "w_bottom_olive_cargo", "w_shoes_black_ankle_boots", "w_bag_cream_tote"], ["旅行", "周边游"]),
    ("w_outfit_travel_05", "夏日白裙草帽", ["w_dress_white_eyelet", "w_shoes_tan_sandals", "w_bag_straw_vacation", "w_acc_straw_hat"], ["旅行", "夏天"]),
    ("w_outfit_interview_01", "互联网面试清爽", ["w_top_white_shirt", "w_bottom_black_suit_pants", "w_shoes_black_loafers", "w_bag_black_work"], ["面试"]),
    ("w_outfit_interview_02", "商务面试黑西装", ["w_top_black_blazer", "w_skirt_charcoal_pencil", "w_shoes_black_pointed_heels", "w_bag_black_work"], ["面试", "正式"]),
    ("w_outfit_interview_03", "汇报浅蓝连衣裙", ["w_dress_blue_formal", "w_shoes_cream_slingback", "w_bag_ivory_chain"], ["汇报", "正式"]),
    ("w_outfit_interview_04", "藏蓝通勤连衣裙", ["w_dress_navy_office", "w_shoes_black_pointed_heels", "w_bag_black_work", "w_acc_rose_silk_scarf"], ["面试", "通勤"]),
    ("w_outfit_wedding_01", "草坪婚礼香槟裙", ["w_dress_champagne_guest", "w_shoes_cream_slingback", "w_bag_ivory_chain", "w_acc_gold_necklace"], ["婚礼", "宴会"]),
    ("w_outfit_wedding_02", "户外婚礼衬衫裙", ["w_dress_cream_shirt", "w_shoes_silver_party_heels", "w_bag_silver_evening"], ["婚礼", "宾客"]),
    ("w_outfit_wedding_03", "玫瑰半裙婚礼宾客", ["w_top_lavender_cardigan", "w_skirt_rose_floral", "w_shoes_blush_ballet", "w_bag_ivory_chain", "w_acc_cream_beret"], ["婚礼", "温柔"]),
    ("w_outfit_wedding_04", "晚宴缎面黑金", ["w_top_black_square_tank", "w_skirt_champagne_satin", "w_shoes_black_pointed_heels", "w_bag_silver_evening", "w_acc_gold_necklace"], ["宴会", "婚礼"]),
    ("w_outfit_sport_01", "轻运动银色球鞋", ["w_top_white_oversized_tee", "w_bottom_charcoal_jogger", "w_shoes_silver_sneakers", "w_bag_cream_tote", "w_acc_navy_cap"], ["运动户外", "轻运动"]),
    ("w_outfit_sport_02", "户外工装 City walk", ["w_top_sage_linen_vest", "w_bottom_olive_cargo", "w_shoes_white_sneakers", "w_bag_tan_crossbody", "w_acc_black_sunglasses"], ["运动户外", "City walk"]),
    ("w_outfit_home_01", "居家咖啡软糯", ["w_top_mocha_hoodie", "w_bottom_pink_pleated_pants", "w_shoes_blush_ballet", "w_bag_yellow_tote"], ["居家轻社交", "楼下咖啡"]),
    ("w_outfit_home_02", "居家拍照针织感", ["w_top_ivory_knit_tee", "w_bottom_pink_pleated_pants", "w_shoes_ivory_mary_jane", "w_bag_tan_crossbody", "w_acc_gold_necklace"], ["居家轻社交", "拍照"]),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return fallback


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _public(path: Path) -> str:
    return closet._public_closet_path(path) or str(path)


def _contact_sheet_path(sheet_index: int) -> Path:
    return CONTACT_SHEET_DIR / CONTACT_SHEETS[sheet_index]


def _ensure_contact_sheets() -> None:
    CONTACT_SHEET_DIR.mkdir(parents=True, exist_ok=True)
    for name in CONTACT_SHEETS:
        target = CONTACT_SHEET_DIR / name
        if target.exists():
            continue
        legacy = LEGACY_SEED_DIR / "contact_sheets" / name
        if legacy.exists():
            shutil.copy2(legacy, target)


def _crop_contact_cell(sheet: Image.Image, cell: int) -> Image.Image:
    cols = 4
    rows = 2
    cell_w = sheet.width // cols
    cell_h = sheet.height // rows
    left = (cell % cols) * cell_w
    top = (cell // cols) * cell_h
    return sheet.crop((left, top, left + cell_w, top + cell_h))


def _detect_key_color(image: Image.Image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    w, h = rgb.size
    points = [(3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4), (w // 2, 3), (w // 2, h - 4)]
    colors = [rgb.getpixel(point) for point in points]
    return max(set(colors), key=colors.count)


def _remove_chroma_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    key = _detect_key_color(rgba)
    key_layer = Image.new("RGB", rgba.size, key)
    diff = ImageChops.difference(rgba.convert("RGB"), key_layer).convert("L")
    alpha = diff.point(lambda value: 0 if value < 70 else 255)
    alpha = alpha.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.GaussianBlur(radius=0.45))
    rgba.putalpha(alpha)
    return rgba


def _trim_alpha(image: Image.Image) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        return image
    left, top, right, bottom = bbox
    pad_x = max(10, int((right - left) * 0.08))
    pad_y = max(10, int((bottom - top) * 0.08))
    return image.crop((max(0, left - pad_x), max(0, top - pad_y), min(image.width, right + pad_x), min(image.height, bottom + pad_y)))


def _fit_canvas(image: Image.Image, size: int = 900, max_side: int = 780) -> Image.Image:
    item = image.copy()
    item.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    canvas.alpha_composite(item, ((size - item.width) // 2, (size - item.height) // 2))
    return canvas


def _prepare_item_assets() -> list[dict[str, Any]]:
    sheets = {index: Image.open(_contact_sheet_path(index)).convert("RGB") for index in range(len(CONTACT_SHEETS))}
    now = _now_iso()
    prepared = []
    for spec in ITEM_SPECS:
        item_dir = CTX.closet_item_dir / spec["item_id"]
        item_dir.mkdir(parents=True, exist_ok=True)
        sheet = sheets[spec["sheet"]]
        cropped = _crop_contact_cell(sheet, spec["cell"])
        transparent = _trim_alpha(_remove_chroma_background(cropped))
        cutout = _fit_canvas(transparent)
        preview = Image.new("RGBA", cutout.size, (255, 255, 255, 255))
        preview.alpha_composite(cutout)

        cutout_path = item_dir / "cutout.png"
        preview_path = item_dir / "preview.png"
        mask_path = item_dir / "mask.png"
        cutout.save(cutout_path)
        preview.convert("RGB").save(preview_path)
        cutout.getchannel("A").save(mask_path)

        alpha_bbox = cutout.getchannel("A").getbbox()
        area_ratio = 0.0
        if alpha_bbox:
            alpha = cutout.getchannel("A")
            transparentish = sum(alpha.histogram()[:11])
            area_ratio = (alpha.width * alpha.height - transparentish) / float(alpha.width * alpha.height)
        min_area_ratio = 0.003 if spec["category"] == "accessory" else 0.015
        quality_status = "usable" if min_area_ratio <= area_ratio <= 0.72 else "review"
        source_path = _contact_sheet_path(spec["sheet"])
        row = {
            "item_id": spec["item_id"],
            "category": spec["category"],
            "category_label": spec["label"],
            "subcategory": spec.get("subcategory"),
            "slot": spec.get("slot") or closet._category_to_layout_slot(spec["category"]),
            "source": {
                "type": SEED_SOURCE,
                "filename": source_path.name,
                "image_index": spec["cell"],
                "source_path": _public(source_path),
                "width": sheet.width,
                "height": sheet.height,
                "crop_box": {
                    "x": (spec["cell"] % 4) * (sheet.width // 4),
                    "y": (spec["cell"] // 4) * (sheet.height // 2),
                    "width": sheet.width // 4,
                    "height": sheet.height // 2,
                },
            },
            "assets": {
                "cutout_path": _public(cutout_path),
                "mask_path": _public(mask_path),
                "preview_path": _public(preview_path),
            },
            "attributes": {
                "colors": spec["colors"],
                "material": spec["material"],
                "fit": spec["fit"],
                "sleeve": spec["sleeve"],
                "neckline": spec["neckline"],
                "pattern": spec["pattern"],
                "details": ["imagegen_seed"],
                "style_tags": spec["tags"],
            },
            "quality": {
                "status": quality_status,
                "score": 0.92 if quality_status == "usable" else 0.62,
                "reasons": [SEED_SOURCE] if quality_status == "usable" else [SEED_SOURCE, "alpha_area_review"],
            },
            "pipeline": {
                "detector": {"provider": "imagegen_contact_sheet", "status": "generated"},
                "clean_reference": {"provider": "local_chroma_key", "status": "pass"},
                "segmentation": {"provider": "local_alpha_mask", "status": quality_status},
            },
            "favorite": False,
            "note": "23-29 岁女性场景化衣橱扩充种子单品",
            "created_at": now,
            "updated_at": now,
            "user_edits": {},
            "deleted": False,
        }
        prepared.append(row)
    return prepared


def _upsert_items(items: list[dict[str, Any]]) -> None:
    manifest = _read_json(CTX.closet_manifest_path, {"version": 1, "items": []})
    seed_ids = {row["item_id"] for row in items}
    now = _now_iso()
    for existing in manifest.setdefault("items", []):
        if existing.get("source", {}).get("type") == SEED_SOURCE and existing.get("item_id") not in seed_ids:
            existing["deleted"] = True
            existing["updated_at"] = now
    index_by_id = {row.get("item_id"): index for index, row in enumerate(manifest["items"])}
    for row in items:
        index = index_by_id.get(row["item_id"])
        if index is None:
            manifest["items"].append(row)
        else:
            created_at = manifest["items"][index].get("created_at") or row["created_at"]
            manifest["items"][index] = {**row, "created_at": created_at}
    _write_json(CTX.closet_manifest_path, manifest)


def _upsert_outfits(item_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    manifest = _read_json(CTX.outfit_manifest_path, {"version": 1, "outfits": [], "plans": []})
    seed_outfit_ids = {entry[0] for entry in OUTFITS}
    now = _now_iso()
    for existing in manifest.setdefault("outfits", []):
        if existing.get("source") == SEED_SOURCE and existing.get("outfit_id") not in seed_outfit_ids:
            existing["deleted"] = True
            existing["updated_at"] = now
    index_by_id = {row.get("outfit_id"): index for index, row in enumerate(manifest["outfits"])}
    created: list[dict[str, Any]] = []
    for offset, (outfit_id, title, item_ids, scene_tags) in enumerate(OUTFITS):
        items = [item_by_id[item_id] for item_id in item_ids]
        layout = closet._build_outfit_cover(outfit_id, items)
        row = {
            "outfit_id": outfit_id,
            "title": title,
            "item_ids": item_ids,
            "scene_tags": scene_tags,
            "source": SEED_SOURCE,
            "favorite_count": 34 + (offset * 7) % 29,
            "cover_path": _public(layout["path"]),
            "layout_snapshot_path": _public(layout["path"]),
            "layout_version": layout["layout_version"],
            "layout_slots": layout["layout_slots"],
            "display_item_ids": layout["display_item_ids"],
            "overflow_items": layout["overflow_items"],
            "warnings": layout["warnings"],
            "created_at": now,
            "updated_at": now,
            "deleted": False,
        }
        index = index_by_id.get(outfit_id)
        if index is None:
            manifest["outfits"].append(row)
        else:
            created_at = manifest["outfits"][index].get("created_at") or row["created_at"]
            manifest["outfits"][index] = {**row, "created_at": created_at}
        created.append(row)
    manifest.setdefault("plans", [])
    _write_json(CTX.outfit_manifest_path, manifest)
    return created


def seed() -> dict[str, Any]:
    _ensure_contact_sheets()
    missing = [name for name in CONTACT_SHEETS if not (CONTACT_SHEET_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing womens closet contact sheets: {missing}")
    CTX.closet_output_dir.mkdir(parents=True, exist_ok=True)
    CTX.closet_item_dir.mkdir(parents=True, exist_ok=True)
    CTX.outfit_dir.mkdir(parents=True, exist_ok=True)

    items = _prepare_item_assets()
    _upsert_items(items)
    item_by_id = {row["item_id"]: row for row in items if row.get("quality", {}).get("status") == "usable"}
    outfits = _upsert_outfits(item_by_id)
    category_counts: dict[str, int] = {}
    for row in items:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    return {
        "status": "seeded",
        "source": SEED_SOURCE,
        "items": len(items),
        "outfits": len(outfits),
        "category_counts": category_counts,
        "contact_sheets": len(CONTACT_SHEETS),
        "active_contact_sheets": len({row["source"]["filename"] for row in items}),
        "user_id": CTX.user_id,
        "manifest_path": str(CTX.closet_manifest_path),
        "outfit_manifest_path": str(CTX.outfit_manifest_path),
        "fingerprint": hashlib.sha256(json.dumps([row["item_id"] for row in items]).encode("utf-8")).hexdigest()[:12],
    }


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
