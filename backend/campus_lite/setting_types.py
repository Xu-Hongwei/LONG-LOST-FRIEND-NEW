from __future__ import annotations

from typing import Any


SETTING_TYPES = {
    "campus": {
        "label": "校园轻伴",
        "guidance": "校园、社团、图书馆、课程、操场等日常场域；关系推进克制、轻量、贴近现实。",
        "tokens": ("校园", "社团", "图书馆", "课程", "操场", "campus"),
    },
    "modern_daily": {
        "label": "现代日常",
        "guidance": "现代生活、城市日常、咖啡店、通勤、邻里和私人计划；避免自动写成校园。",
        "tokens": ("现代", "日常", "生活", "都市日常"),
    },
    "workplace": {
        "label": "职场现实",
        "guidance": "职场、项目、会议、合作、商业压力和成年人的边界；避免校园社团化。",
        "tokens": ("职场", "公司", "合伙", "项目", "会议", "商业"),
    },
    "xianxia_wuxia": {
        "label": "武侠修仙",
        "guidance": "山门、江湖、医修、剑修、秘境、门派规矩和修行代价；称呼和行动要符合古风/修仙语境。",
        "tokens": ("修仙", "仙侠", "武侠", "玄幻", "医修", "剑修", "江湖", "门派"),
    },
    "urban_fantasy": {
        "label": "都市奇幻",
        "guidance": "现代城市中的异常、秘术、异能、隐秘组织和日常秩序冲突；现实感与奇幻规则并存。",
        "tokens": ("都市奇幻", "异能", "秘术", "异常", "怪谈"),
    },
    "mystery": {
        "label": "悬疑推理",
        "guidance": "案件、线索、证词、档案、误导和真相边界；关系推进要通过调查协作体现。",
        "tokens": ("悬疑", "推理", "案件", "侦探", "档案", "线索"),
    },
    "sci_fi": {
        "label": "科幻赛博",
        "guidance": "数据、仿生人、空间站、网络城市、义体、算法和技术伦理；避免自动套用无关地点。",
        "tokens": ("科幻", "赛博", "仿生", "空间站", "数据", "义体", "未来"),
    },
    "historical": {
        "label": "历史古风",
        "guidance": "古代秩序、官署、家族、礼法、朝堂或市井；语言和边界要符合时代语境。",
        "tokens": ("历史", "古风", "朝堂", "古代", "市井", "官署"),
    },
    "fantasy_adventure": {
        "label": "奇幻冒险",
        "guidance": "异世界、旅队、遗迹、契约、魔法、怪物和旅途选择；关系通过共同冒险累积。",
        "tokens": ("奇幻", "冒险", "异世界", "魔法", "遗迹", "旅伴"),
    },
    "custom": {
        "label": "自定义",
        "guidance": "遵循用户提供的自定义题材说明，不套用校园默认事件池。",
        "tokens": (),
    },
}

DEFAULT_SETTING_TYPE = "modern_daily"


def normalize_setting_type(value: Any, default: str = DEFAULT_SETTING_TYPE) -> str:
    text = str(value or "").strip()
    return text if text in SETTING_TYPES else default


def setting_label(value: Any) -> str:
    setting_type = normalize_setting_type(value)
    return SETTING_TYPES[setting_type]["label"]


def setting_guidance(value: Any, notes: str = "") -> str:
    setting_type = normalize_setting_type(value)
    profile = SETTING_TYPES[setting_type]
    extra = str(notes or "").strip()
    return f"{profile['label']}：{profile['guidance']}" + (f" 补充：{extra}" if extra else "")


def infer_setting_type(*texts: str, fallback: str = DEFAULT_SETTING_TYPE) -> str:
    haystack = " ".join(str(item or "") for item in texts)
    best_type = ""
    best_score = 0
    for setting_type, profile in SETTING_TYPES.items():
        if setting_type == "custom":
            continue
        score = sum(1 for token in profile["tokens"] if token and token in haystack)
        if score > best_score:
            best_type = setting_type
            best_score = score
    if best_type:
        return best_type
    return normalize_setting_type(fallback)
