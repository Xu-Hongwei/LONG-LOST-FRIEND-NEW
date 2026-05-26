from __future__ import annotations

from typing import Any

from ...setting_types import SETTING_TYPES, infer_setting_type, normalize_setting_type, setting_guidance


NOVEL_SETTING_PROFILES: dict[str, dict[str, Any]] = {
    "campus": {
        "label": "校园轻伴",
        "places": ["图书馆门口", "教学楼公告栏前", "社团教室外", "校门口小路", "自习室窗边", "操场看台"],
        "titles": ["借来的伞", "公告栏前", "社团教室", "周末之前", "雨停以后", "旧便签"],
        "events": [
            "临时降雨让两人不得不共用一把伞去取被落下的资料。",
            "公告栏上的活动名单出现误会，两人一起确认报名信息。",
            "社团教室临时缺人，两人被同学拉去帮忙整理器材。",
            "原定出行前时间被课程调整打乱，两人需要重新约定。",
            "雨停后路面积水，两人绕路时发现之前提到的小店。",
            "旧便签从书页里滑出来，上面的话让未说完的问题重新出现。",
        ],
        "endings": [
            "伞柄被还回去时，里面夹着一张没写完的借阅单。",
            "名单旁边多出一个陌生名字，让原本简单的计划变得不确定。",
            "灯忽然灭了一下，两人同时停住，没有把刚才的问题问完。",
            "新的时间只剩一个空位，主角第一次主动问对方是否方便。",
            "小店门口挂着暂停营业的牌子，约定被迫留到下一次。",
            "便签背面多了一行字，却没有人立刻问出口。",
        ],
    },
    "xianxia_wuxia": {
        "label": "修仙武侠",
        "places": ["山门药庐", "石阶松林", "雨夜驿站", "秘境入口", "剑冢外", "江边渡口"],
        "titles": ["药庐夜话", "山门试剑", "驿站风雨", "秘境之前", "剑冢旧誓", "渡口回声"],
        "events": [
            "门派急召打断疗伤，两人必须在药效散尽前确认下一段同行路线。",
            "试剑台上旧伤复发，主角被迫在隐瞒和求助之间做选择。",
            "雨夜驿站混入追踪者，两人需要用一场假装疏远避开耳目。",
            "秘境入口的禁制只允许一人先行，对方把选择权交回主角手里。",
            "剑冢旧誓牵出未了因果，两人发现前路与彼此的旧伤有关。",
            "渡口船期提前，未说完的话被钟声和江雾暂时截断。",
        ],
        "endings": [
            "药碗见底时，对方第一次没有立刻离开。",
            "断剑微鸣，像在回应两人都没说出口的疑问。",
            "追踪者离开后，桌上只剩一枚被折过的路引。",
            "禁制亮起时，主角听见对方说：这次你决定。",
            "旧誓背面刻着一个陌生名字，下一段路忽然有了方向。",
            "船离岸前，对方把半张地图塞进主角掌心。",
        ],
    },
    "sci_fi": {
        "label": "科幻赛博",
        "places": ["旧城区事务所", "空轨站台", "数据交易所", "废弃机房", "仿生人诊所", "空间港闸口"],
        "titles": ["雨城盲区", "空轨延误", "伪造证据", "废机房灯火", "仿生回声", "闸口之前"],
        "events": [
            "监控盲区出现新的时间戳，两人需要判断它是真证据还是诱饵。",
            "空轨系统临时封锁，让原本简单的会面变成一次共同脱身。",
            "委托档案里混入伪造记录，主角必须决定是否公开自己的判断。",
            "废弃机房仍有一台终端亮着，里面保存着上一轮对话提过的线索。",
            "仿生人诊所的旧病例暴露伦理风险，两人暂时站在同一侧。",
            "空间港闸口提前关闭，未完成的委托必须被拆成两段执行。",
        ],
        "endings": [
            "雨声盖住警报前，对方关掉了录音。",
            "空轨重启时，屏幕上多出一条匿名留言。",
            "伪造记录被删掉前，有人截走了最后一帧。",
            "终端黑屏后，主角看见玻璃里映出另一个人影。",
            "旧病例编号和对方曾经提过的名字对上了。",
            "闸口落下前，对方把通行码留给主角。",
        ],
    },
    "mystery": {
        "label": "悬疑推理",
        "places": ["旧档案室", "雨夜公交站", "展馆后台", "失物招领处", "旧宅门廊", "河堤路灯下"],
        "titles": ["未归档的信", "雨夜证词", "后台脚印", "失物编号", "旧宅门铃", "河堤目击者"],
        "events": [
            "一封未归档的信改变了旧案时间线，两人需要重新核对证词。",
            "雨夜公交站的目击者只记得一个细节，主角必须决定是否追问。",
            "展馆后台出现不该存在的脚印，原本安全的调查突然变得近身。",
            "失物编号和上一轮提到的物件吻合，两人意识到线索没有断。",
            "旧宅门铃在无人时响起，迫使两人先确认彼此是否安全。",
            "河堤路灯下的目击者改口，让真相和信任同时受到考验。",
        ],
        "endings": [
            "信纸背面还有一行被水洇开的地址。",
            "目击者离开后，座椅下多出一枚旧钥匙。",
            "脚印停在门前，却没有离开的痕迹。",
            "编号尾数正好对应一个被删掉的档案页。",
            "门铃第二次响起时，对方先挡在主角前面。",
            "路灯熄灭前，目击者说出了另一个名字。",
        ],
    },
    "workplace": {
        "label": "职场现实",
        "places": ["会议室", "路演后台", "深夜办公室", "咖啡店角落", "机场休息区", "客户楼下"],
        "titles": ["会议之前", "路演后台", "失误复盘", "凌晨白板", "出差延误", "客户楼下"],
        "events": [
            "关键会议临时提前，两人必须在信息不完整时统一口径。",
            "路演后台设备故障，主角需要决定是否承认准备里的漏洞。",
            "一次失误被放大，双方在复盘里重新划清责任和信任。",
            "凌晨白板上只剩最后一个问题，两人不得不暂停争论先处理人。",
            "出差延误打乱安排，原本被压下的真实顾虑浮上来。",
            "客户楼下的临时变更让合作边界被重新测试。",
        ],
        "endings": [
            "会议门打开前，对方把最难说的那句替主角留了位置。",
            "投屏恢复时，备份文件里多出一页未署名方案。",
            "复盘结束后，责任清楚了，关系反而没被推远。",
            "白板擦掉前，对方圈住了唯一还能补救的点。",
            "航班改签成功，但两人都知道真正要谈的不是行程。",
            "客户转身上楼后，对方第一次问主角想不想停一下。",
        ],
    },
    "modern_daily": {
        "label": "现代日常",
        "places": ["街角咖啡店", "雨后人行道", "社区书店", "地铁换乘口", "便利店门口", "公寓楼下"],
        "titles": ["街角停顿", "雨后同行", "书店错拿", "换乘之前", "便利店灯光", "楼下未完"],
        "events": [
            "一场临时变更打乱原本普通的见面，两人需要重新确认彼此的节奏。",
            "雨后路面积水让同行路线改变，一个旧话题被自然带回来。",
            "书店或便利店里发生一次错拿，两人被迫停下来处理小误会。",
            "地铁延误让时间被拉长，未说完的话有了继续的空隙。",
            "公寓楼下的短暂停留让主角需要决定是否多问一句。",
            "一次普通的帮忙暴露出双方对边界的不同理解。",
        ],
        "endings": [
            "路灯亮起时，对方没有催促主角立刻回答。",
            "伞沿的水落下来，刚好打断那句快说出口的话。",
            "收据背面多出一个没有解释的时间。",
            "地铁进站声盖过答案，只留下下一次再谈的理由。",
            "楼道灯灭了一次，两人同时停住。",
            "那个小误会解决了，但真正的问题刚露出边缘。",
        ],
    },
    "fantasy_adventure": {
        "label": "奇幻冒险",
        "places": ["边境酒馆", "森林小径", "遗迹入口", "篝火旁", "飞空船甲板", "龙骨峡谷"],
        "titles": ["边境地图", "森林迷路", "遗迹门前", "守夜篝火", "飞空船风暴", "龙骨回声"],
        "events": [
            "旧地图缺了一角，两人必须决定先找路还是先避开追兵。",
            "森林小径被魔法雾气改写，主角发现对方记得自己之前的选择。",
            "遗迹门前的契约要求一人说出真实愿望，队伍因此停住。",
            "守夜时远处传来异响，两人要在叫醒同伴和独自确认之间选择。",
            "飞空船遭遇风暴，主角必须把一个旧约定交给对方保管。",
            "龙骨峡谷的回声复述了未说出口的话，让旅途变得不再轻松。",
        ],
        "endings": [
            "地图背面出现一条只有火光下才看得见的路。",
            "雾散开时，对方站在原地，没有先走。",
            "契约没有成立，却留下了新的同行条件。",
            "篝火快灭时，对方把前半夜的守望接了过去。",
            "风暴过去后，旧约定被压在罗盘下面。",
            "回声停止时，峡谷另一端亮起了陌生的灯。",
        ],
    },
    "urban_fantasy": {
        "label": "都市奇幻",
        "places": ["旧城区巷口", "午夜便利店", "异常管理处", "天台水箱旁", "地下换乘层", "封锁线外"],
        "titles": ["巷口异常", "午夜收据", "管理处来电", "天台符痕", "地下回声", "封锁线外"],
        "events": [
            "城市异常短暂出现，两人需要在普通人察觉前处理痕迹。",
            "午夜便利店的收据显示不存在的时间，旧话题被卷入异常。",
            "异常管理处临时来电，迫使双方重新确认是否继续同行。",
            "天台上的符痕回应了主角之前提过的细节。",
            "地下换乘层出现重复广播，让两人被迫暂时分工。",
            "封锁线外有人认出对方，普通生活和隐秘规则开始冲突。",
        ],
        "endings": [
            "符痕熄灭前，留下一个只对主角可见的方向。",
            "收据上的时间跳回正常，却多了一行手写字。",
            "电话挂断后，对方第一次没有隐瞒风险。",
            "天台风声里，有人说出了不该知道的名字。",
            "广播重复第三遍时，出口指示牌换了方向。",
            "封锁线撤开了，但两人的选择还没有结束。",
        ],
    },
    "historical": {
        "label": "历史古风",
        "places": ["官署廊下", "茶楼雅间", "旧宅花厅", "渡口马车旁", "宫门侧道", "市井雨棚下"],
        "titles": ["廊下文书", "茶楼旧约", "花厅试探", "渡口风声", "宫门之前", "雨棚传言"],
        "events": [
            "一份文书被临时调换，两人必须在礼法和真相之间选择说法。",
            "茶楼旧约被旁人提起，主角需要判断是否顺势承认。",
            "旧宅花厅的短暂停留让双方的身份边界变得敏感。",
            "渡口马车误时，未完成的安排被迫重新谈判。",
            "宫门侧道的传话带来风险，对方把决定权留给主角。",
            "市井传言变了方向，两人发现有人在借他们的关系做局。",
        ],
        "endings": [
            "文书合上时，印泥还没有干。",
            "茶盏放下后，对方把最难的一句留到下次。",
            "花厅屏风后传来脚步声。",
            "马车驶离前，帘角露出半封旧信。",
            "宫门落锁，传话的人却没有离开。",
            "雨棚外的传言停了，真正的名字才刚出现。",
        ],
    },
    "custom": {
        "label": "自定义题材",
        "places": ["核心场域一", "核心场域二", "临界地点", "共同任务现场", "安静转折点", "下一阶段入口"],
        "titles": ["初始规则", "共同任务", "第一次偏差", "边界选择", "线索回收", "下一入口"],
        "events": [
            "符合自定义题材规则的外部事件打断原有节奏，两人需要一起处理。",
            "共同任务暴露信息差，主角必须决定是否解释自己的真实顾虑。",
            "一个来自题材规则的限制让双方不能立刻靠近。",
            "旧线索以新的形式出现，迫使两人重新确认边界。",
            "外部压力让对方把选择权交还给主角。",
            "阶段性事件暂时结束，但留下下一轮更具体的问题。",
        ],
        "endings": [
            "关键道具留下了未解释的痕迹。",
            "任务结束了，但真正的问题刚开始。",
            "对方没有追问，只把选择权留下。",
            "旧线索被回收，却打开了新的方向。",
            "场面安静下来时，主角意识到还有一句话没说。",
            "下一阶段入口出现，但两人还没有决定是否进去。",
        ],
    },
}


def _value(source: Any, key: str) -> str:
    if source is None:
        return ""
    if isinstance(source, dict) or hasattr(source, "keys"):
        return str(source[key] if key in source.keys() else "")
    return str(getattr(source, key, "") or "")


def infer_novel_setting_type(project: Any, character: Any | None = None) -> str:
    project_setting = _infer_project_setting_type(project)
    if project_setting:
        return project_setting
    character_setting = _value(character, "setting_type")
    if character_setting:
        return normalize_setting_type(character_setting)
    return infer_setting_type(
        _value(project, "genre"),
        _value(project, "worldview"),
        _value(project, "relationship_setup"),
        _value(project, "outline"),
        fallback="modern_daily",
    )


def _infer_project_setting_type(project: Any) -> str:
    haystack = " ".join(
        _value(project, key)
        for key in ("genre", "worldview", "relationship_setup", "outline")
    )
    best_type = ""
    best_score = 0
    for setting_type, profile in SETTING_TYPES.items():
        if setting_type == "custom":
            continue
        score = sum(1 for token in profile["tokens"] if token and token in haystack)
        if score > best_score:
            best_type = setting_type
            best_score = score
    return normalize_setting_type(best_type) if best_type else ""


def novel_setting_profile(setting_type: str) -> dict[str, Any]:
    return NOVEL_SETTING_PROFILES.get(normalize_setting_type(setting_type), NOVEL_SETTING_PROFILES["modern_daily"])


def character_story_seed_pool(character: Any | None) -> dict[str, list[str]]:
    if character is None:
        return {}
    raw = _value(character, "story_seed_pool")
    if isinstance(character, dict) or hasattr(character, "keys"):
        raw = character["story_seed_pool"] if "story_seed_pool" in character.keys() else {}
    else:
        raw = getattr(character, "story_seed_pool", {}) or {}
    if not isinstance(raw, dict):
        return {}

    def clean_value(key: str, value: str) -> str:
        text = str(value or "").strip()
        if key == "places":
            if len(text) > 34 or any(token in text for token in ["。", "！", "？", "；", "生活在", "性格", "名字"]):
                return ""
        if key == "motifs" and (len(text) > 24 or any(token in text for token in ["。", "！", "？", "；"])):
            return ""
        return text

    def values(key: str, limit: int = 8) -> list[str]:
        items = raw.get(key)
        if not isinstance(items, list):
            return []
        result: list[str] = []
        for item in items:
            text = clean_value(key, str(item or ""))
            if text:
                result.append(text)
            if len(result) >= limit:
                break
        return result

    pool = {
        "places": values("places"),
        "event_seeds": values("event_seeds"),
        "hook_seeds": values("hook_seeds"),
        "motifs": values("motifs"),
        "forbidden_defaults": values("forbidden_defaults"),
    }
    return pool if any(pool.values()) else {}


def project_story_seed_pool(character: Any | None, setting_type: str) -> tuple[dict[str, list[str]], str]:
    seed_pool = character_story_seed_pool(character)
    if not seed_pool:
        return {}, "setting_profile"
    character_setting = normalize_setting_type(_value(character, "setting_type") if character is not None else "")
    project_setting = normalize_setting_type(setting_type)
    if not character_setting or character_setting == project_setting:
        return seed_pool, "character_seed"
    translated = {
        "places": [],
        "event_seeds": [],
        "hook_seeds": [],
        "motifs": seed_pool.get("motifs", []),
        "forbidden_defaults": seed_pool.get("forbidden_defaults", []),
    }
    return translated if any(translated.values()) else {}, "character_seed_translatable"


def novel_setting_guidance(setting_type: str, notes: str = "") -> str:
    profile = novel_setting_profile(setting_type)
    places = "、".join(profile["places"][:6])
    events = "；".join(profile["events"][:3])
    return f"{setting_guidance(setting_type, notes)} 可用场域：{places}。可见事件方向：{events}"
