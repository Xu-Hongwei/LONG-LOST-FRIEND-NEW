import type { ComputedRef, Ref } from "vue";
import { optimizeNovelInstruction } from "./api";
import type { CanvasActionKey } from "./constants";
import type { ChapterDraft } from "./useNovelProject";
import type { NovelChapter, NovelProject, StoryCanvasChapter, StoryCanvasEvent } from "../../types";

type PriorStateEntry = { chapter: NovelChapter };

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function compactInstructionText(text: string) {
  return text.replace(/\s+/g, " ").replace(/\?+/g, "").trim();
}

function instructionSection(title: string, lines: string[]) {
  const cleaned = lines.map((line) => line.trim()).filter(Boolean);
  return cleaned.length ? `${title}：\n${cleaned.join("\n")}` : "";
}

export function useNovelInstruction(options: {
  activeNovelProject: ComputedRef<NovelProject | null>;
  activeNovelChapter: ComputedRef<NovelChapter | null>;
  chapterDraft: Ref<ChapterDraft>;
  chapterInstruction: Ref<string>;
  projectChapterTargetLength: Ref<number>;
  isOptimizingInstruction: Ref<boolean>;
  instructionOptimizationNote: Ref<string>;
  activeCanvasChapter: ComputedRef<StoryCanvasChapter | null>;
  activeChapterWordCount: ComputedRef<number>;
  chapterLengthRatio: ComputedRef<number>;
  novelStateLastHandoff: ComputedRef<Record<string, unknown> | null>;
  novelStateSummary: ComputedRef<string>;
  novelStateOpenThreads: ComputedRef<string[]>;
  activeNovelPriorStateEntries: ComputedRef<PriorStateEntry[]>;
  chapterQualityDiagnosis: ComputedRef<Record<string, unknown>>;
  rememberChapterInstruction: () => void;
}) {
  function sceneCardInstructionValue(key: string) {
    return compactInstructionText(options.chapterDraft.value.scene_card[key] || "");
  }

  function canvasActionInstructionValue(key: CanvasActionKey) {
    return compactInstructionText(String(options.activeCanvasChapter.value?.[key] || ""));
  }

  function activeBoundEvent(): StoryCanvasEvent | null {
    const chapter = options.activeCanvasChapter.value;
    const pool = options.activeNovelProject.value?.story_canvas?.event_pool;
    const active = pool?.active || [];
    const retired = pool?.retired || [];
    const events = [...active, ...retired];
    if (!chapter || !events.length) return null;
    const contract = chapter.event_contract && typeof chapter.event_contract === "object"
      ? chapter.event_contract as Record<string, unknown>
      : {};
    const id = String(contract.event_id || chapter.event_pool_id || "");
    const byId = id ? events.find((item) => item.id === id) : null;
    if (byId) {
      return {
        ...byId,
        place: String(contract.place || byId.place || ""),
        time_anchor: String(contract.time_anchor || byId.time_anchor || ""),
        event: String(contract.external_event || byId.event || ""),
        hook: String(contract.hook || byId.hook || ""),
        motifs: Array.isArray(contract.motifs) ? contract.motifs.map(String).filter(Boolean) : byId.motifs,
        use_mode: String(contract.use_mode || byId.use_mode || "guide"),
        selection_score: Number(contract.score || byId.selection_score || chapter.event_pool_score || 0),
        selection_reasons: Array.isArray(contract.reasons) ? contract.reasons.map(String).filter(Boolean) : byId.selection_reasons
      };
    }
    return events.find((item) => (item.bound_chapter_orders || []).map(String).includes(String(chapter.chapter_order))) || null;
  }

  function boundEventInstructionLines(event: StoryCanvasEvent | null) {
    if (!event) return [];
    const tags = (event.tags || {}) as Record<string, unknown>;
    const tagList = (key: string) => Array.isArray(tags[key])
      ? (tags[key] as unknown[]).map(String).filter(Boolean).slice(0, 4).join("、")
      : "";
    return [
      `事件池ID：${event.id}`,
      event.time_anchor ? `时间锚点：${event.time_anchor}` : "",
      event.place ? `地点：${event.place}` : "",
      event.event ? `外部事件：${event.event}` : "",
      event.hook ? `结尾钩子：${event.hook}` : "",
      event.motifs?.length ? `意象：${event.motifs.slice(0, 4).join("、")}` : "",
      tagList("theme_markers") ? `主题命中：${tagList("theme_markers")}` : "",
      tagList("tone_markers") ? `基调命中：${tagList("tone_markers")}` : "",
      String(tags.progression_role || "").trim() ? `推进角色：${String(tags.progression_role)}` : "",
      tagList("progression_markers") ? `推进命中：${tagList("progression_markers")}` : "",
      tagList("promise_markers") ? `承诺命中：${tagList("promise_markers")}` : "",
      event.selection_reasons?.length ? `选择原因：${event.selection_reasons.slice(0, 3).join("；")}` : ""
    ].filter(Boolean);
  }

  function optimizedChapterInstruction() {
    const goal = compactInstructionText(options.chapterDraft.value.goal) || "承接前文，完成一个具体事件中的关系推进";
    const current = options.activeChapterWordCount.value;
    const target = Math.max(400, Number(options.projectChapterTargetLength.value) || 1800);
    const minimum = Math.max(400, Math.round(target * 0.7));
    const ratio = options.chapterLengthRatio.value;
    const card = {
      currentScene: sceneCardInstructionValue("current_scene"),
      pov: sceneCardInstructionValue("pov"),
      presentCharacters: sceneCardInstructionValue("present_characters"),
      characterDesire: sceneCardInstructionValue("character_desire"),
      requiredFacts: sceneCardInstructionValue("required_facts"),
      forbiddenProgress: sceneCardInstructionValue("forbidden_progress")
    };
    const canvasAction = {
      externalEvent: canvasActionInstructionValue("external_event"),
      triggerEvent: canvasActionInstructionValue("trigger_event"),
      immediateReaction: canvasActionInstructionValue("immediate_reaction"),
      obstacleEscalation: canvasActionInstructionValue("obstacle_escalation"),
      counterpartReaction: canvasActionInstructionValue("counterpart_reaction"),
      characterChoice: canvasActionInstructionValue("character_choice"),
      sceneConsequence: canvasActionInstructionValue("scene_consequence"),
      relationshipShift: canvasActionInstructionValue("relationship_shift"),
      endingHook: canvasActionInstructionValue("ending_hook")
    };
    const boundEvent = activeBoundEvent();
    const boundEventLines = boundEventInstructionLines(boundEvent);
    const storyCanvas = options.activeNovelProject.value?.story_canvas;
    const promise = storyCanvas?.story_promise;
    const protocol = storyCanvas?.progression_protocol;
    const protocolLines = [
      promise?.core_experience ? `核心体验：${promise.core_experience}` : "",
      promise?.genre_contract ? `题材承诺：${promise.genre_contract}` : "",
      promise?.relationship_engine ? `关系引擎：${promise.relationship_engine}` : "",
      promise?.tone_commitment ? `基调承诺：${promise.tone_commitment}` : "",
      protocol?.driver ? `故事驱动力：${protocol.driver}` : "",
      protocol?.relationship_rule ? `关系推进规则：${protocol.relationship_rule}` : "",
      protocol?.progression_tools?.length ? `推进工具：${protocol.progression_tools.slice(0, 5).join("；")}` : "",
      protocol?.drift_guards?.length ? `漂移护栏：${protocol.drift_guards.slice(0, 5).join("；")}` : ""
    ].filter(Boolean);
    const chapterProgressionLines = [
      options.activeCanvasChapter.value?.progression_role ? `本章推进角色：${options.activeCanvasChapter.value.progression_role}` : "",
      options.activeCanvasChapter.value?.chapter_drive ? `本章推进驱动：${options.activeCanvasChapter.value.chapter_drive}` : "",
      options.activeCanvasChapter.value?.promise_targets?.length ? `本章承诺目标：${options.activeCanvasChapter.value.promise_targets.slice(0, 4).join("；")}` : ""
    ].filter(Boolean);
    let mode = "精修当前章";
    let lengthDirective = `当前正文约 ${current} 字，接近目标区间。请保持已有节奏，补强场景连贯性和章节收束。`;
    if (!current) {
      mode = "新写完整章节";
      lengthDirective = "当前正文为空。请直接进入小说场景，写出完整章节，不要写大纲、说明或创作报告。";
    } else if (ratio < 70) {
      mode = "扩写当前章";
      lengthDirective = `当前正文约 ${current} 字，明显低于目标 ${target} 字。请在保留已有事实、语气和人物边界的基础上扩写同一章，不要另起新章，不要跳到后续剧情。`;
    } else if (ratio < 90) {
      mode = "续写并补足当前章";
      lengthDirective = `当前正文约 ${current} 字，略低于目标 ${target} 字。请承接现有正文继续写，并补足动作、对白和场景转折。`;
    } else if (ratio > 130) {
      mode = "压缩精修当前章";
      lengthDirective = `当前正文约 ${current} 字，超过目标 ${target} 字较多。请保留核心事实和最有画面感的动作、对白、情绪落点，压缩重复描写。`;
    }
    const sceneLines = [
      card.currentScene ? `当前场景：${card.currentScene}` : "",
      card.pov ? `视角：${card.pov}` : "",
      card.presentCharacters ? `在场人物：${card.presentCharacters}` : "",
      card.characterDesire ? `人物欲望：${card.characterDesire}` : "",
      card.requiredFacts ? `必须保留事实：${card.requiredFacts}` : "",
      card.forbiddenProgress ? `禁止推进：${card.forbiddenProgress}` : ""
    ];
    const canvasActionLines = [
      canvasAction.externalEvent ? `外部事件：${canvasAction.externalEvent}` : "",
      canvasAction.triggerEvent ? `触发事件：${canvasAction.triggerEvent}` : "",
      canvasAction.immediateReaction ? `即时反应：${canvasAction.immediateReaction}` : "",
      canvasAction.obstacleEscalation ? `阻碍升级：${canvasAction.obstacleEscalation}` : "",
      canvasAction.counterpartReaction ? `对方反应：${canvasAction.counterpartReaction}` : "",
      canvasAction.characterChoice ? `人物选择：${canvasAction.characterChoice}` : "",
      canvasAction.sceneConsequence ? `场景后果：${canvasAction.sceneConsequence}` : "",
      canvasAction.relationshipShift ? `关系变化：${canvasAction.relationshipShift}` : "",
      canvasAction.endingHook ? `结尾钩子：${canvasAction.endingHook}` : ""
    ];
    const sceneTaskLines = sceneLines.some(Boolean) ? sceneLines : [
      "围绕本章剧情概述和画布动作链展开一个连续、可见的校园日常场面。",
      "场景卡只负责镜头、人物欲望、事实边界和禁止推进，不负责另行改写剧情事件。"
    ];
    const actionTaskLines = canvasActionLines.some(Boolean) ? canvasActionLines : [
      "用一个具体外部事件打开场景。",
      "让人物遇到一个不能立刻解决的小阻碍。",
      "安排至少一个人物小选择，并用具体动作收束到可续写的钩子。"
    ];
    return [
      `生成模式：${mode}`,
      instructionSection("信息优先级", [
        "项目推进协议决定整本书怎么推进，是 genre/tone 之后的执行约束。",
        "本章剧情概述决定这一章发生什么，是剧情事实和方向，不是写作命令。",
        "画布动作链决定事件推进顺序：先外部事件，再触发反应、阻碍升级、人物选择和结尾钩子。",
        "场景卡决定怎么贴近人物和场景来写：视角、在场人物、人物欲望、必须保留事实和禁止推进。",
        "生成指令只决定写法、篇幅、节奏和质量补救；不得改写本章剧情概述、画布动作链和已确认事实。"
      ]),
      instructionSection("长度要求", [
        `目标长度：${target} 字`,
        `最低可接受长度：${minimum} 字`,
        lengthDirective,
        "如果一次无法写满目标长度，也必须先达到最低可接受长度，并停在可继续续写的自然钩子上。"
      ]),
      instructionSection("项目推进协议", protocolLines),
      instructionSection("本章推进方式", chapterProgressionLines),
      instructionSection("本章剧情概述", [goal]),
      instructionSection("项目事件池绑定", boundEventLines.length ? [
        ...boundEventLines,
        "事件池决定这一章发生什么；场景卡只补镜头、视角、人物欲望和边界，不能把本章改成另一个无关事件。"
      ] : []),
      instructionSection("画布动作链", actionTaskLines),
      instructionSection("场景镜头与边界", sceneTaskLines),
      instructionSection("场景展开顺序", [
        "先按画布动作链里的外部事件或触发事件打开场景；如果画布缺失，再用雨势、铃声、旁人经过、物件掉落或时间被打断补足。",
        "再写人物的即时动作和克制反应，让读者看见她想处理什么、又为什么不能马上处理；不要把阻碍写成分析句。",
        "中段用短对白和动作来推进，不用解释关系变化；对白之间穿插物件、视线、距离和环境声。",
        "结尾优先收在画布动作链的结尾钩子上；如果缺失，再收在一个可继续写的动作、物件或未问出口的问题上。"
      ]),
      instructionSection("长度与节奏", [
        `正文目标约 ${target} 字，最低先达到 ${minimum} 字；如果当前只有 ${current} 字，优先扩写同一场景内部的动作链和对白，不另起新章。`,
        "建议把篇幅分给：场景进入约 20%，事件展开约 35%，对白与选择约 30%，结尾钩子约 15%。",
        "每 2-3 段必须有一个可见动作或环境变化，避免连续心理抒情。"
      ]),
      instructionSection("扩写策略", [
        "保留已有正文事实、语气和人物边界。",
        "增加 2-3 个可见动作节点，例如停顿、递还物品、整理书页、避开旁人、走廊里的短暂打断。",
        "增加至少 2 轮自然对白；对白要短，不要把人物心意说满。",
        "增加环境变化推动节奏，例如光线变化、铃声、脚步声、旁人经过、门被关上。",
        "让主角做一个小选择，例如没有立刻离开、主动补一句话、收好某个物件、回头确认对方反应。",
        canvasAction.endingHook ? "结尾必须停在画布动作链的结尾钩子附近。" : "结尾必须停在一个具体可续写的动作、物件或未说完的话上。"
      ]),
      "",
      instructionSection("禁止事项", [
        "不要出现“本章剧情概述”“场景卡”“人物欲望”“阻碍/张力”“作为伏笔”等元叙述。",
        "不要直接写“他们关系变近了”“两人还不熟”“这是后续剧情的伏笔”。",
        "不要突然表白、承诺、亲密越界。",
        "不要重复已有段落。",
        "不要把剧情标签、素材列表、内部字段名或编号写进正文。"
      ])
    ].filter(Boolean).join("\n\n");
  }

  async function applyOptimizedChapterInstruction() {
    const baseInstruction = optimizedChapterInstruction();
    options.chapterInstruction.value = baseInstruction;
    options.rememberChapterInstruction();
    options.instructionOptimizationNote.value = "已生成本地硬约束骨架，正在请求远程导演优化。";
    if (!options.activeNovelProject.value || options.isOptimizingInstruction.value) {
      options.instructionOptimizationNote.value = options.activeNovelProject.value ? "正在优化中。" : "当前没有长篇项目，已使用本地骨架。";
      return;
    }
    options.isOptimizingInstruction.value = true;
    try {
      const result = await optimizeNovelInstruction(options.activeNovelProject.value.id, {
        chapter_id: options.activeNovelChapter.value?.id || null,
        base_instruction: baseInstruction,
        title: options.chapterDraft.value.title,
        goal: options.chapterDraft.value.goal,
        summary: options.chapterDraft.value.summary,
        body: options.chapterDraft.value.body,
        status: options.chapterDraft.value.status,
        scene_card: options.chapterDraft.value.scene_card,
        canvas_chapter: options.activeCanvasChapter.value ? { ...options.activeCanvasChapter.value } as unknown as Record<string, unknown> : {},
        previous_handoff: options.novelStateLastHandoff.value || {},
        prior_novel_state: {
          summary: options.novelStateSummary.value,
          open_threads: options.novelStateOpenThreads.value,
          completed_chapters: options.activeNovelPriorStateEntries.value.map(({ chapter }) => ({
            chapter_order: chapter.chapter_order,
            title: chapter.title,
            summary: chapter.summary,
            status: chapter.status
          }))
        },
        quality_diagnosis: options.chapterQualityDiagnosis.value,
        target_length: options.projectChapterTargetLength.value
      });
      options.chapterInstruction.value = result.instruction || baseInstruction;
      options.rememberChapterInstruction();
      options.instructionOptimizationNote.value = result.source === "remote"
        ? "远程导演优化已应用。"
        : `远程优化不可用，已保留本地骨架${result.diagnostics?.reason ? `：${result.diagnostics.reason}` : "。"}`;
    } catch (err) {
      options.chapterInstruction.value = baseInstruction;
      options.rememberChapterInstruction();
      options.instructionOptimizationNote.value = `远程优化失败，已保留本地骨架：${readableError(err)}`;
    } finally {
      options.isOptimizingInstruction.value = false;
    }
  }

  return {
    applyOptimizedChapterInstruction
  };
}
