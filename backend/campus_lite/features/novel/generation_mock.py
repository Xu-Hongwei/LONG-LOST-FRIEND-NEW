from __future__ import annotations

import re
from typing import Any


class NovelGenerationMockMixin:
    def _mock_body_from_beats(
        self,
        protagonist: str,
        beats: list[dict[str, Any]],
        first_hint: str,
        surface_event: str,
        ending_beat: str,
    ) -> list[str]:
        paragraphs: list[str] = []
        for index, beat in enumerate(beats[:7]):
            action = self._mock_scene_line(beat.get("visible_action"), surface_event if index == 0 else "风把纸页轻轻掀起。")
            inner = self._mock_scene_line(beat.get("inner_turn"), "她把话放慢了一点。")
            dialogue = [str(item).strip("“”\" ") for item in beat.get("dialogue", []) if str(item).strip()]
            if dialogue:
                lines = []
                for item_index, line in enumerate(dialogue[:3]):
                    speaker = protagonist if item_index % 2 else "对方"
                    verb = "说" if item_index % 2 else "问"
                    lines.append(f"“{line}”{speaker}{verb}。")
                paragraphs.append(f"{action}{''.join(lines)}{inner}")
            elif index == 0:
                paragraphs.append(f"{action}她想起{first_hint}，脚步因此慢了半拍。{inner}")
            else:
                paragraphs.append(f"{action}{inner}")
        return paragraphs

    def _mock_scene_continuations(
        self,
        protagonist: str,
        first_hint: str,
        surface_event: str,
        ending_beat: str,
        chapter_order: int,
    ) -> list[str]:
        if chapter_order <= 1:
            return [
            f"借阅台旁边排着两个人，打印机吐出一截白纸，又卡在半路。管理员低声提醒队伍往里收，{protagonist}只好把散开的书先靠在墙边，空出一只手去找那张不见的借阅单。",
            "她看见纸角压在对方鞋边，弯腰时校牌从书页间滑出来，轻轻磕在地上。对方比她先一步拾起，却没有马上递回，只把校牌翻到背面，确认没有弄脏。",
            f"“林晚栀？”对方念得很轻，像只是核对名字。{protagonist}抬头看了他一眼，又很快移开，“嗯。”",
            "后面有人小声说快闭馆了。风从门缝里挤进来，把玻璃门吹得响了一下。她本来想把所有东西抱回怀里，却发现最上面那本书不是自己的。",
            "那本书的扉页夹着一张课程表，边缘被雨水洇出一点浅痕。她犹豫了一瞬，把书递过去：“这个好像拿错了。”",
            "对方接过去，低头看见课程表上的教室号，忽然笑了一下：“我们明天同一栋楼上课。”这句话不算熟络，却让走廊里的距离短了一点。",
            f"{protagonist}没有顺着笑意多说，只把自己的书一本一本理齐。那个和{first_hint}有关的念头又浮上来，她这次没有急着按下去，只让它停在翻书的动作里。",
            "管理员终于把卡住的纸抽出来，借阅台前空出一条窄路。对方往旁边让了让，手里还拿着那张被风吹皱的便签。",
            "“这张也给你。”他说。便签背面朝上，干干净净，看不出他到底有没有看见上面的字。",
            f"{protagonist}接过来，指尖碰到纸边时顿了一下。她想说没关系，又觉得这三个字太像匆忙收场，最后只低声问：“你叫什么？”",
            "对方报出名字。走廊尽头的灯在这时亮起来，把他身后的影子拉得很长。她重复了一遍，声音很轻，却没有念错。",
            "两个人并肩走到门口，雨已经下起来，台阶上积着一层薄亮的水。她停在屋檐下面，把便签夹回书里，才发现背面多了一行极小的字：明天别忘了带伞。",
            ]
        event = surface_event.rstrip("。") or "眼前的小麻烦"
        ending = ending_beat.rstrip("。") or "一个还没有说完的问题"
        if chapter_order % 3 == 0:
            return [
                f"这一次，{protagonist}没有把话题放回原处。她站在楼梯平台旁，听见下面传来拖动桌椅的声音，才发现自己其实一直在等对方先开口。",
                f"{event}。这件事看起来很小，却正好卡在两个人都不好装作没看见的位置。",
                "对方把手里的资料往栏杆上一放，低声问：“上次那件事，你是不是还没说完？”",
                f"{protagonist}指尖停在纸页边缘。她本可以说没有，可那样就又会把话推回去。她看着楼下慢慢亮起的灯，说：“有一点。”",
                f"那个和{first_hint}有关的念头终于有了可以落下的地方。她没有说得太满，只把最容易误会的一句先解释清楚。",
                "风从楼梯间往上走，吹得公告纸轻轻响。对方没有插话，只把快要滑下去的资料按住，像是在替她守住一点空隙。",
                "“我以为你不想继续聊。”他说。",
                "“不是。”林晚栀回答得很快，又因为这份快而顿住。她把后半句放慢，“我只是怕说得太急。”",
                f"{ending}。这一次她没有转身就走，而是在楼梯平台多站了半分钟，等那句话真正落稳。",
            ]
        if chapter_order % 3 == 1:
            return [
                f"到了约好的地方，{protagonist}才发现时间被临时改过。门口贴着一张新通知，纸边还没压平，被风吹得轻轻翘起来。",
                f"{event}。她看了两遍，确认不是自己记错，心里那点刚积起来的从容又被打散。",
                "对方从楼梯那边跑过来，呼吸有些乱：“等很久了吗？”",
                "“没有。”她说完，又补了一句，“刚好看见通知。”",
                f"那个和{first_hint}有关的念头像被通知纸压住一角。她伸手把纸边抚平，顺势把新的时间指给他看。",
                "两个人站在门口算时间，谁都没有立刻说麻烦。旁边同学经过，笑着问他们是不是又被安排到一起。",
                f"{protagonist}没有否认，也没有承认，只低头在纸上圈出一个还能重合的空档。",
                "对方看着那个空档，声音放轻了一点：“这个时间对你会不会太赶？”",
                f"{ending}。她把笔帽合上，忽然觉得有些选择不必说破，也已经比上一次更靠近一点。",
            ]
        return [
            f"这一次不是重新开始。{protagonist}认得出对方说话前会停半拍，也认得出自己为什么没有立刻走开。",
            f"{event}。旁边有人催了一句，声音不高，却让刚缓下来的气氛又紧了起来。",
            f"{protagonist}把手里的东西往怀里收了收，先处理最容易被看见的那一部分。她没有解释太多，只问：“这样可以吗？”",
            "对方看了一眼她指着的位置，没有抢着替她决定。“可以，不过这里可能还差一张表。”",
            f"她顺着他的视线看过去，才发现问题并不在自己刚才担心的地方。那个和{first_hint}有关的念头被轻轻拨了一下，却没有立刻落下来。",
            "路过的同学从旁边探头：“你们两个一起负责这个？”这句话来得太突然，林晚栀指尖一顿，纸角差点折出痕迹。",
            "“只是刚好碰到。”她说得很稳，声音却比平时轻。对方没有纠正，也没有顺势开玩笑，只把另一边压住，让纸面重新平整。",
            f"事情终于处理好时，天色已经暗了一层。{protagonist}低头确认最后一行字，才发现自己刚才一直把呼吸放得很轻。",
            f"分别前，对方把剩下的材料递给她：“这个你拿着，下一次可能还用得到。”{protagonist}接过来，发现边角上留着一处新的折痕。",
            f"{ending}。她没有马上追问，只把那一点不确定收进书页里，像给下一次见面留了一枚很小的路标。",
        ]

    def _mock_chapter(
        self,
        project: Any,
        chapter: Any,
        materials: list[Any],
        target_length: int,
        scene_card: dict[str, Any] | None = None,
        scene_beats: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        chosen = materials[:6]
        detail_hints = []
        for row in chosen[:5]:
            hint = self._naturalize_material(row["content"])
            if hint and hint not in detail_hints:
                detail_hints.append(hint)
        first_hint = detail_hints[0] if detail_hints else "一段没说完的心事"
        protagonist = project["protagonist"] or project["title"]
        card = scene_card or {}
        surface_event = self._mock_scene_line(
            card.get("surface_event") or chapter["goal"],
            "两个人在傍晚的日常场景里继续交谈，通过动作、停顿和一句未说满的话推进彼此的理解。",
        )
        ending_beat = self._mock_scene_line(
            card.get("ending_beat"),
            "她在借阅单背面看见一行刚写下的字。",
        )
        beats = scene_beats or self._mock_scene_beats(project, chapter, card)
        paragraphs = self._mock_body_from_beats(protagonist, beats, first_hint, surface_event, ending_beat)
        target_floor = max(260, int(max(target_length, 400) * 0.76))
        continuations = self._mock_scene_continuations(protagonist, first_hint, surface_event, ending_beat, int(chapter["chapter_order"]))
        index = 0
        body = "\n\n".join(paragraphs)
        while len(re.sub(r"\s", "", body)) < target_floor and index < len(continuations):
            paragraphs.append(continuations[index])
            body = "\n\n".join(paragraphs)
            index += 1
        summary = self._clean_material_text(f"{surface_event} {ending_beat}")[:260] or "在连续校园场景中写出外部事件、人物选择和可续写的结尾。"
        return {
            "title": chapter["title"] if chapter["title"] != "下一章" else f"第{chapter['chapter_order']}章：余温",
            "summary": summary,
            "body": body,
            "source_material_ids": [row["id"] for row in chosen],
        }
