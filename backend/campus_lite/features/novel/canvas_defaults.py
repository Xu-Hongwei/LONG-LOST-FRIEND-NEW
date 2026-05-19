from __future__ import annotations

from typing import Any

from ...schemas import StoryItem


class NovelCanvasDefaultMixin:
    def _default_story_canvas(
        self,
        title: str,
        genre: str,
        tone: str,
        protagonist: str,
        story_bible: dict[str, Any],
        story_items: list[StoryItem],
    ) -> dict[str, Any]:
        lead = protagonist or title or "主角"
        inspirations = [item.content for item in story_items if item.kind in {"story_beat", "relationship_texture"}][:3]
        unresolved = [
            item.content
            for item in story_items
            if item.kind in {"open_thread", "motif"} and item.status in {"seed", "active"}
        ][:3]
        facts = [str(item).strip() for item in story_bible.get("confirmed_facts", []) if str(item).strip()][:3]
        boundaries = [str(item).strip() for item in story_bible.get("boundaries", []) if str(item).strip()][:3]
        hook = unresolved[0] if unresolved else "一次没有说满的普通回应，在下一次见面时变得更具体。"
        acts = [
            {"id": "act_1", "order": 1, "title": "初识与日常接触", "purpose": "用可见事件建立人物第一印象。", "chapter_ids": ["canvas_ch_1"]},
            {"id": "act_2", "order": 2, "title": "共同事件与小误会", "purpose": "让关系在共同处理问题时产生张力。", "chapter_ids": ["canvas_ch_2"]},
            {"id": "act_3", "order": 3, "title": "犹豫与选择", "purpose": "把未说出口的情绪转化为一次具体选择。", "chapter_ids": ["canvas_ch_3"]},
            {"id": "act_4", "order": 4, "title": "伏笔回收与情绪落点", "purpose": "回收前文线索，完成克制但明确的情绪变化。", "chapter_ids": ["canvas_ch_4"]},
        ]
        chapters = [
            {
                "id": "canvas_ch_1",
                "act_id": "act_1",
                "chapter_order": 1,
                "title": "第一章 校园初识",
                "goal": "傍晚图书馆门口，林晚栀的书本和便签被风吹落，对方帮她捡起却没有追问便签内容；她在礼貌停顿里第一次问出对方名字，让第一印象从路人一面变成会被记住的人。",
                "external_event": "林晚栀在图书馆门口掉落书本，对方帮她捡起，两人因此第一次正式说话。",
                "trigger_event": "傍晚风从图书馆门口穿过，林晚栀怀里的书和便签一起散落。",
                "immediate_reaction": "她急忙蹲下去捡，先遮住便签，声音比平时轻。",
                "obstacle_escalation": "对方已经看见便签露出一角，但没有立刻问。",
                "counterpart_reaction": "对方把书脊理正递还给她，只提醒她夹页快掉了。",
                "character_choice": "林晚栀原本可以立刻走开，却停下来问了对方的名字。",
                "scene_consequence": "两人没有变熟，但彼此从路人变成了会被记住的人。",
                "relationship_shift": "从陌生到记住彼此名字。",
                "ending_hook": "分别后，林晚栀意识到自己记住了对方说话时的停顿。",
                "target_length": 1800,
                "status": "planned",
                "emotion_curve": "轻微紧张 -> 礼貌试探 -> 留下印象",
                "scene_ids": ["scene_1"],
            },
            {
                "id": "canvas_ch_2",
                "act_id": "act_2",
                "chapter_order": 2,
                "title": "第二章 共同的麻烦",
                "goal": "公告栏前的通知被贴错位置，两人被临时卷入同一件校园小事；林晚栀想按规则处理，却因旁人催促和对方先安抚现场产生误会，留下下一次解释的理由。",
                "external_event": "两人被同一件校园小事牵连，需要一起处理。",
                "trigger_event": "校园公告栏前的一张通知被贴错位置，两人都被临时叫去处理。",
                "immediate_reaction": "林晚栀想按规则重贴，对方却先去安抚等在旁边的人。",
                "obstacle_escalation": "旁人催促让两人的处理方式显得不一致，误会被放大。",
                "counterpart_reaction": "对方替她挡下一句玩笑，却让她误以为自己拖累了对方。",
                "character_choice": "林晚栀没有沉默离开，而是留下来把剩下的通知整理完。",
                "scene_consequence": "误会没解释清楚，但两人都有了下一次说话的理由。",
                "relationship_shift": "从礼貌相识到愿意多停留几分钟。",
                "ending_hook": "误会没有完全解释清楚，留下下一章继续见面的理由。",
                "target_length": 2000,
                "status": "planned",
                "emotion_curve": "熟悉感 -> 小误会 -> 想解释",
                "scene_ids": ["scene_2"],
            },
            {
                "id": "canvas_ch_3",
                "act_id": "act_3",
                "chapter_order": 3,
                "title": "第三章 没有说破的话",
                "goal": "前一章的误会被一次普通问候带出，林晚栀原想轻轻带过，却发现自己不想再只道谢；她主动补上一句真正想说的话，让关系停在被温和接住的信任停顿里。",
                "external_event": "林晚栀在一个日常场景里选择主动回应对方一次。",
                "trigger_event": "放学后两人在安静角落再次遇见，前一章的误会被一句普通问候带出来。",
                "immediate_reaction": "林晚栀下意识想说没关系，却发现这次自己并不想敷衍过去。",
                "obstacle_escalation": "她越想解释，越怕这份在意显得过重。",
                "counterpart_reaction": "对方没有逼问，只把话题放慢，给她留下继续说的空隙。",
                "character_choice": "她主动补上一句真正想说的话，而不是只道谢。",
                "scene_consequence": "两人之间第一次出现了可被回望的信任停顿。",
                "relationship_shift": "从被动回应到主动靠近一点。",
                "ending_hook": "对方没有追问，只用一个动作接住她的迟疑。",
                "target_length": 2200,
                "status": "planned",
                "emotion_curve": "犹豫 -> 主动 -> 被温和接住",
                "scene_ids": ["scene_3"],
            },
            {
                "id": "canvas_ch_4",
                "act_id": "act_4",
                "chapter_order": 4,
                "title": "第四章 普通傍晚",
                "goal": "傍晚再次出现前文留下的小线索，林晚栀意识到多问一句就会让关系靠近；她没有把情绪说满，而是用一个普通约定回应，让线索被回收、下一次见面被留下。",
                "external_event": f"两人在普通傍晚重新谈到前文线索：{hook}",
                "trigger_event": "前文留下的小线索在傍晚重新出现，打断了原本普通的同行。",
                "immediate_reaction": "林晚栀先假装没有立刻认出来，指尖却停在书页边。",
                "obstacle_escalation": "她知道只要多问一句，关系就会被推到更近的位置。",
                "counterpart_reaction": "对方没有替她做决定，只把选择交还给她。",
                "character_choice": "她选择用一个普通约定回应，而不是把情绪说满。",
                "scene_consequence": "前文线索被回收，但新的日常约定被留下。",
                "relationship_shift": "从不确定到愿意约定下一次普通见面。",
                "ending_hook": "留下新的日常约定，而不是一次性完成关系。",
                "target_length": 2200,
                "status": "planned",
                "emotion_curve": "回望 -> 确认 -> 新的日常约定",
                "scene_ids": ["scene_4"],
            },
        ]
        scenes = [
            self._canvas_scene(
                "scene_1",
                "canvas_ch_1",
                1,
                f"{genre or '校园日常'}的傍晚，图书馆门口或教学楼走廊，氛围{tone or '温柔克制'}。",
                lead,
                "林晚栀抱着书经过时，书本被风吹散，对方帮她捡起，两人第一次正式说话。",
                "她想自然地道谢，也想确认对方是不是注意到了自己的慌乱。",
                "两人还不熟，只能用礼貌和停顿试探距离。",
                facts,
                boundaries,
                "她走远后才发现自己已经记住了对方的名字。",
            ),
            self._canvas_scene(
                "scene_2",
                "canvas_ch_2",
                1,
                "校园日常里的小麻烦现场，旁边有人经过，时间有限。",
                lead,
                "两人因为同一件事短暂合作，却在一句话里产生误会。",
                "她想把事情解释清楚，但不想显得太在意。",
                "对方的好意和她的紧张错开了半步。",
                facts,
                boundaries,
                "误会暂时没解开，却让下一次见面变得必要。",
            ),
            self._canvas_scene(
                "scene_3",
                "canvas_ch_3",
                1,
                "放学后的安静角落，周围声音渐渐远去。",
                lead,
                "林晚栀主动把一个普通话题接下去，而不是像以前那样停住。",
                "她想靠近一点，但仍希望自己保有退路。",
                "越是普通的话题，越容易暴露她真正的在意。",
                facts,
                boundaries,
                "对方没有追问，只把节奏放慢，等她继续说。",
            ),
            self._canvas_scene(
                "scene_4",
                "canvas_ch_4",
                1,
                "傍晚的校园路灯下，前文小线索重新出现。",
                lead,
                "两人重新谈到前文留下的小线索，并用日常方式完成一次确认。",
                "她想确认这份靠近是真的，但不想让它变成压力。",
                "关系已经变化，却不能被急着命名。",
                facts,
                boundaries,
                "他们约定下一次仍从一个普通话题开始。",
            ),
        ]
        threads = [
            {
                "id": "thread_1",
                "kind": "foreshadowing",
                "label": "未说满的话",
                "setup_chapter_id": "canvas_ch_1",
                "payoff_chapter_id": "canvas_ch_4",
                "status": "seed",
                "notes": hook,
            },
            {
                "id": "thread_2",
                "kind": "relationship",
                "label": "慢速靠近",
                "setup_chapter_id": "canvas_ch_1",
                "payoff_chapter_id": "canvas_ch_3",
                "status": "active",
                "notes": "每次推进必须表现为动作、对话或选择，不直接跳到关系确认。",
            },
        ]
        return {
            "version": 1,
            "mode": "story_canvas",
            "acts": acts,
            "chapters": chapters,
            "scenes": scenes,
            "threads": threads,
            "quality_rules": [
                "每章至少一个外部事件。",
                "每章至少两轮人物对话。",
                "每章至少一个人物小选择。",
                "结尾必须留下具体可续写钩子。",
            ],
            "diagnostics": {"source": "local"},
        }

    def _canvas_scene(
        self,
        scene_id: str,
        chapter_id: str,
        scene_order: int,
        current_scene: str,
        protagonist: str,
        surface_event: str,
        character_desire: str,
        tension: str,
        facts: list[str],
        boundaries: list[str],
        ending_beat: str,
    ) -> dict[str, Any]:
        return {
            "id": scene_id,
            "chapter_id": chapter_id,
            "scene_order": scene_order,
            "current_scene": current_scene,
            "pov": f"第三人称限知，主要贴近{protagonist}的感受。",
            "present_characters": protagonist,
            "surface_event": surface_event,
            "character_desire": character_desire,
            "tension": tension,
            "required_facts": facts,
            "forbidden_progress": boundaries or ["不突然表白、不亲密越界、不把未发生线索写成已发生。"],
            "ending_beat": ending_beat,
            "linked_material_ids": [],
        }
