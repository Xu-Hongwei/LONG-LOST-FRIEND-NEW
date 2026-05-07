<script setup lang="ts">
import { computed, onMounted, ref, nextTick } from "vue";
import html2canvas from "html2canvas";
import { createSession, deleteMemoryItem, exportSession, listCharacters, patchMemory, resolveVisitor, sendMessage, updateMemoryItem } from "./api";
import type { CharacterBond, CharacterCard, CharacterState, ChatMessage, ContextSlot, MemoryItem, MemoryPane, MemoryPatch } from "./types";

const VISITOR_KEY = "campus-pulse-lite-visitor";
const LOVE_TEST_KEY = "campus-pulse-lite-love-test";
const LOVE_TEST_VERSION = "love-test-v3-20q-6types-profile-images";

type PageKey = "chat" | "love-test";
type LoveDimension = "warmth" | "space" | "initiative" | "security" | "depth" | "playfulness";

interface LoveOption {
  label: string;
  text: string;
  scores: Partial<Record<LoveDimension, number>>;
}

interface LoveQuestion {
  id: string;
  title: string;
  options: LoveOption[];
}

interface LoveProfile {
  id: string;
  name: string;
  subtitle: string;
  description: string;
  maleDetail: string;
  femaleDetail: string;
  relationshipNeed: string;
  blindSpot: string;
  idealDynamic: string;
  partnerCue: string;
  memoryLine: string;
}

type LoveGender = "female" | "male";

const loveQuestions: LoveQuestion[] = [
  {
    id: "first_reply",
    title: "刚认识的人发来一段认真分享，你更自然的反应是？",
    options: [
      { label: "接住情绪", text: "先回应他的感受，再慢慢问细节。", scores: { warmth: 2, depth: 1 } },
      { label: "轻松破冰", text: "用一点玩笑和好奇心把气氛打开。", scores: { initiative: 1, playfulness: 2 } },
      { label: "慢一点", text: "认真看完，但不会马上把自己也交出去。", scores: { space: 2, security: 1 } }
    ]
  },
  {
    id: "closeness",
    title: "关系变亲近时，你最在意哪件事？",
    options: [
      { label: "稳定回应", text: "对方别忽冷忽热，节奏清楚一点。", scores: { security: 2, warmth: 1 } },
      { label: "保留呼吸", text: "亲近很好，但彼此还是要有自己的空间。", scores: { space: 2 } },
      { label: "互动火花", text: "最好能一起制造一些只有两个人懂的小瞬间。", scores: { initiative: 2, warmth: 1 } }
    ]
  },
  {
    id: "conflict",
    title: "出现小摩擦时，你通常希望对方怎么做？",
    options: [
      { label: "直接说清", text: "别猜来猜去，把真实想法讲明白。", scores: { security: 2, initiative: 1 } },
      { label: "先降温", text: "先别逼问，等情绪过去再谈。", scores: { space: 2, security: 1 } },
      { label: "温柔确认", text: "先让我知道关系没有被否定，再处理问题。", scores: { warmth: 2, security: 1 } }
    ]
  },
  {
    id: "date_style",
    title: "你更喜欢哪种约会感？",
    options: [
      { label: "安静陪伴", text: "散步、吃饭、各自做事也能很舒服。", scores: { security: 2, space: 1 } },
      { label: "临时冒险", text: "突然决定去哪里，过程比计划更重要。", scores: { initiative: 2, playfulness: 1 } },
      { label: "细节仪式", text: "不一定盛大，但要有被放在心上的细节。", scores: { warmth: 2, security: 1 } }
    ]
  },
  {
    id: "message_gap",
    title: "对方一段时间没回消息，你更可能怎么想？",
    options: [
      { label: "需要解释", text: "可以忙，但希望之后能说明一下。", scores: { security: 2 } },
      { label: "先做自己", text: "我会先转回自己的节奏，不急着追问。", scores: { space: 2 } },
      { label: "主动补位", text: "我可能会换个轻松话题，再给一次台阶。", scores: { initiative: 2, warmth: 1 } }
    ]
  },
  {
    id: "being_liked",
    title: "当你感觉被喜欢时，什么最容易打动你？",
    options: [
      { label: "记住细节", text: "对方记得我说过的小偏好和小麻烦。", scores: { warmth: 2, security: 1 } },
      { label: "尊重边界", text: "对方靠近得克制，不把亲密当成理所当然。", scores: { space: 2, security: 1 } },
      { label: "明确选择", text: "对方愿意主动表达，而不是一直让我猜。", scores: { initiative: 1, security: 2 } }
    ]
  },
  {
    id: "deep_talk",
    title: "夜里聊到比较私密的话题，你更期待哪种氛围？",
    options: [
      { label: "慢慢下潜", text: "不用急着给结论，能一起把真实感受说细。", scores: { depth: 2, warmth: 1 } },
      { label: "保持清醒", text: "可以真诚，但别把气氛推得太满。", scores: { space: 1, security: 2 } },
      { label: "轻轻带过", text: "深聊可以，但最好有人会适时把气氛拉轻。", scores: { playfulness: 2, initiative: 1 } }
    ]
  },
  {
    id: "public_affection",
    title: "对方在别人面前表达亲近，你更舒服的方式是？",
    options: [
      { label: "自然照顾", text: "不用张扬，但能看出他把我放在心上。", scores: { warmth: 2, security: 1 } },
      { label: "低调克制", text: "公开场合少一点亲密展示，我会更自在。", scores: { space: 2 } },
      { label: "大方承认", text: "我喜欢对方不躲闪，关系可以被自然看见。", scores: { initiative: 2, security: 1 } }
    ]
  },
  {
    id: "planning",
    title: "两个人要一起安排一件事，你比较喜欢？",
    options: [
      { label: "有人带路", text: "对方可以先提出方案，我再一起调整。", scores: { initiative: 2, security: 1 } },
      { label: "一起商量", text: "彼此说明需求，把舒服的边界提前讲好。", scores: { security: 2, depth: 1 } },
      { label: "随时变动", text: "别排太死，留点临时起意的空间。", scores: { playfulness: 2, space: 1 } }
    ]
  },
  {
    id: "pressure",
    title: "你状态不好时，恋人靠近你的最佳方式是？",
    options: [
      { label: "陪在旁边", text: "不用解决所有事，先让我知道他在。", scores: { warmth: 2, security: 1 } },
      { label: "给我空间", text: "让我自己缓一缓，之后我会回来。", scores: { space: 2 } },
      { label: "拉我出来", text: "用一点行动和玩笑，把我从情绪里带出来。", scores: { initiative: 1, playfulness: 2 } }
    ]
  },
  {
    id: "promise",
    title: "关于承诺，你更相信什么？",
    options: [
      { label: "长期一致", text: "少说大话，日常稳定比热烈表态更重要。", scores: { security: 2, depth: 1 } },
      { label: "当下真诚", text: "此刻的认真也有重量，不必一开始就保证永远。", scores: { warmth: 1, playfulness: 1, initiative: 1 } },
      { label: "共同建设", text: "承诺要变成行动计划，问题也要一起修。", scores: { security: 2, initiative: 1 } }
    ]
  },
  {
    id: "jealousy",
    title: "如果你有一点吃醋，最希望对方怎么回应？",
    options: [
      { label: "明确安抚", text: "直接告诉我我很重要，不要让我猜。", scores: { security: 2, warmth: 1 } },
      { label: "认真解释", text: "把边界和事实说清，我能自己消化。", scores: { depth: 1, security: 2 } },
      { label: "轻松化解", text: "用一点可爱的方式让我放松下来。", scores: { playfulness: 2, warmth: 1 } }
    ]
  },
  {
    id: "daily_contact",
    title: "你理想中的日常联系频率更接近？",
    options: [
      { label: "稳定报到", text: "不用一直聊，但每天有自然的连接。", scores: { security: 2, warmth: 1 } },
      { label: "各自自由", text: "忙的时候各过各的，想念时再靠近。", scores: { space: 2 } },
      { label: "随机冒泡", text: "随手分享奇怪小事，比固定流程更可爱。", scores: { playfulness: 2, initiative: 1 } }
    ]
  },
  {
    id: "love_language",
    title: "你更容易从哪种表达里感到被爱？",
    options: [
      { label: "行动照顾", text: "他记得我的习惯，并在小事上替我想。", scores: { warmth: 2, security: 1 } },
      { label: "深度理解", text: "他能理解我的矛盾、脆弱和复杂。", scores: { depth: 2, warmth: 1 } },
      { label: "共同体验", text: "一起尝试新鲜事，关系就会变亮。", scores: { initiative: 1, playfulness: 2 } }
    ]
  },
  {
    id: "pace",
    title: "暧昧推进到下一步时，你最需要？",
    options: [
      { label: "明确心意", text: "别一直模糊，要让我知道这不是玩笑。", scores: { security: 2, initiative: 1 } },
      { label: "自然流动", text: "不用定义太早，气氛到了就会发生。", scores: { playfulness: 1, warmth: 1, space: 1 } },
      { label: "缓慢确认", text: "每一步都要让我有时间感受和选择。", scores: { space: 2, depth: 1 } }
    ]
  },
  {
    id: "repair",
    title: "吵完架后，什么最能修复你？",
    options: [
      { label: "拥抱式和好", text: "先把关系接回来，再谈谁对谁错。", scores: { warmth: 2, security: 1 } },
      { label: "复盘原因", text: "弄清楚问题在哪里，下次怎么避免。", scores: { depth: 1, security: 2 } },
      { label: "留点时间", text: "别急着和好，给情绪一点退潮空间。", scores: { space: 2 } }
    ]
  },
  {
    id: "future",
    title: "谈到未来时，你更希望对方？",
    options: [
      { label: "给我确定感", text: "不用马上定终身，但要让我看到认真。", scores: { security: 2, depth: 1 } },
      { label: "一起想象", text: "可以浪漫一点，把未来说得有画面。", scores: { warmth: 1, playfulness: 1, initiative: 1 } },
      { label: "尊重当下", text: "未来重要，但现在别被压力塞满。", scores: { space: 2, warmth: 1 } }
    ]
  },
  {
    id: "alone_time",
    title: "恋爱后你怎么看待独处时间？",
    options: [
      { label: "必要留白", text: "我需要独处来恢复自己，这不代表疏远。", scores: { space: 2, depth: 1 } },
      { label: "可以共享", text: "在同一个空间各做各的也很亲密。", scores: { security: 1, warmth: 2 } },
      { label: "想被拉动", text: "有人把我从惯性里拉出来，我会觉得生活变新鲜。", scores: { initiative: 1, playfulness: 2 } }
    ]
  },
  {
    id: "vulnerability",
    title: "你愿意暴露脆弱的前提是？",
    options: [
      { label: "被稳定接住", text: "对方不会因为我的脆弱就后退或评判。", scores: { security: 2, warmth: 1 } },
      { label: "足够深入", text: "关系到了一定深度，我才会说真正的事。", scores: { depth: 2, space: 1 } },
      { label: "气氛轻柔", text: "不能太沉重，最好有一点轻松和余地。", scores: { playfulness: 1, warmth: 1, space: 1 } }
    ]
  },
  {
    id: "shared_memory",
    title: "你希望恋人怎样使用你们的共同记忆？",
    options: [
      { label: "自然提起", text: "在合适时候想起我说过的话，会很动人。", scores: { warmth: 2, depth: 1 } },
      { label: "别过度煽情", text: "可以记得，但不要每次都把气氛推满。", scores: { space: 2 } },
      { label: "变成暗号", text: "共同记忆最好能变成只有我们懂的梗。", scores: { playfulness: 2, initiative: 1 } }
    ]
  }
];

const loveProfiles: LoveProfile[] = [
  {
    id: "harbor",
    name: "安全港型",
    subtitle: "稳定、确认、慢慢升温",
    description: "你在恋爱里最容易被“持续可靠”打动。热烈当然也会让你心动，但真正让你放松下来的，是对方在日常里稳定出现、说到做到，并且愿意把关系讲清楚。你不一定需要高频聊天，却很在意回应是否有温度、承诺是否有落点、暧昧是否一直被悬着。",
    maleDetail: "男性安全港型更像稳定锚点：情绪不轻易失控，承诺会落到行动里，擅长用照顾、守护和长期责任感表达爱。短板是表达偏内敛，过度迁就时容易显得没有主见。",
    femaleDetail: "女性安全港型更像温暖容器：敏感细腻、踏实专一，擅长经营关系里的小细节，会把平淡日子照顾得很安稳。短板是容易习惯性包容，偶尔因为太在意而多想。",
    relationshipNeed: "你需要确定感、解释权和可预期的陪伴。对方越能在小事上给出稳定反馈，你越容易自然敞开。",
    blindSpot: "太强的忽冷忽热会快速消耗你；如果对方长期暧昧不明，你会开始自我保护。",
    idealDynamic: "慢慢升温、清楚选择、稳定复现。爱意不必宏大，但要能被日常证明。",
    partnerCue: "角色适合多做确认和承接，少用忽远忽近制造张力；推进关系时给理由、给时间、给安全感。",
    memoryLine: "用户的恋爱互动偏好偏向安全港型：重视稳定回应、明确确认、持续陪伴和慢热升温。"
  },
  {
    id: "spark",
    name: "火花探索型",
    subtitle: "主动、好奇、制造共同瞬间",
    description: "你喜欢恋爱里有一点不可预测的亮光。比起规规矩矩地推进关系，你更容易被临时起意、共同冒险、突然接上的玩笑和只有两个人懂的暗号吸引。你并不是不需要认真，而是希望认真不要变成沉重，亲密最好能带着生命力。",
    maleDetail: "男性火花探索型通常热情外向、创造力强，喜欢主动制造约会、惊喜和新鲜体验。短板是新鲜感褪去后耐心容易下降，情绪来得快也容易冲动。",
    femaleDetail: "女性火花探索型更灵动、感性、重仪式感，喜欢被宠爱和被重视，也愿意主动创造浪漫。短板是容易被情绪带动，关系太平淡时会明显失去兴致。",
    relationshipNeed: "你需要主动性、新鲜感和互动的来回。对方愿意发起、会接梗、能把普通日子点亮，会让你明显更投入。",
    blindSpot: "过度流程化、过早沉重承诺或一直原地等待，会让你感觉关系失去弹性。",
    idealDynamic: "一起发现、一起试探、一起把小事变成记忆。关系像一场轻巧但真诚的同行。",
    partnerCue: "角色可以更主动一点，偶尔发起轻松提议、玩笑和共同暗号，但不要把建议写死成剧情任务。",
    memoryLine: "用户的恋爱互动偏好偏向火花探索型：喜欢主动、有趣、新鲜、能共同制造小瞬间的互动。"
  },
  {
    id: "garden",
    name: "留白花园型",
    subtitle: "亲近但不黏连，温柔但有边界",
    description: "你喜欢亲密关系里保留呼吸感。你并不抗拒靠近，也不是冷淡，只是很在意靠近是否尊重你的节奏。真正舒服的恋爱，对你来说像一座被好好照看的花园：有人来，也有人懂得停在合适的位置；有分享，也允许沉默。",
    maleDetail: "男性留白花园型偏独立理性，重视个人空间和边界，表达爱意常常含蓄而务实。短板是容易显得疏离，不擅长回应高频情绪需求。",
    femaleDetail: "女性留白花园型温柔但独立，注重恋爱的质感和精神共鸣，喜欢安静舒适的陪伴。短板是表达太含蓄时容易让对方误会，也可能拒绝对方的关心。",
    relationshipNeed: "你需要选择权、边界感和低压陪伴。对方越不急着占满你，你越可能主动靠近。",
    blindSpot: "连续追问、过快定义关系、把亲密当成理所当然，会让你本能退后。",
    idealDynamic: "有距离的亲密，有分寸的温柔。两个人各自完整，又愿意在合适的时候靠近。",
    partnerCue: "角色适合低压陪伴，少连续追问，多给选择权；亲密感通过细节和耐心自然长出来。",
    memoryLine: "用户的恋爱互动偏好偏向留白花园型：重视空间感、边界感、低压陪伴和自主选择。"
  },
  {
    id: "lantern",
    name: "暖灯共感型",
    subtitle: "情绪细腻，容易被真诚接住",
    description: "你对恋爱里的情绪温度很敏感。一个人的语气、停顿、是否记得细节、能不能看懂你没说出口的那一层，都会影响你对关系的信任。你容易被真诚、柔软、细腻的表达打动，也很珍惜那些被认真理解的瞬间。",
    maleDetail: "男性暖灯共感型温柔细腻、善于倾听，会把伴侣的情绪放在很重要的位置，用陪伴和体贴表达爱。短板是容易过度承接对方情绪，忽略自己的需要。",
    femaleDetail: "女性暖灯共感型共情力很强，擅长安慰、照顾和情感滋养，会用小细节传递温暖。短板是容易过度迁就，也容易被对方的负面情绪影响。",
    relationshipNeed: "你需要情绪承接、细节记忆和温柔表达。对方先看见你的感受，再给建议，会比直接解决问题更有效。",
    blindSpot: "敷衍、冷处理、粗糙玩笑或只讲道理不回应感受，会让你觉得自己没有被真正看见。",
    idealDynamic: "像一盏暖灯：不刺眼，但一直照着。两个人能温柔地说真话，也能把小细节记成共同记忆。",
    partnerCue: "角色适合先回应情绪，再给轻柔建议；可以自然使用共同记忆，但避免夸张煽情。",
    memoryLine: "用户的恋爱互动偏好偏向暖灯共感型：重视情绪承接、细节记忆、温柔表达和被理解感。"
  },
  {
    id: "compass",
    name: "清醒共建型",
    subtitle: "真诚、沟通、一起修关系",
    description: "你喜欢恋爱有浪漫，但不希望它只停在情绪里。你会被成熟、坦诚、愿意沟通的人吸引：出现问题时能讲清事实，也愿意一起调整。对你来说，爱不是互相猜，而是两个人都有意识地把关系建设得更好。",
    maleDetail: "男性清醒共建型理性、有规划、有责任感，倾向把伴侣视为并肩前行的伙伴。短板是情感表达可能不够柔软，容易把关系处理得太像目标管理。",
    femaleDetail: "女性清醒共建型清醒独立，擅长沟通边界、规划未来和推动关系升级。短板是对自己和伴侣要求较高，容易在浪漫体验上显得克制。",
    relationshipNeed: "你需要透明沟通、边界协商和行动兑现。对方如果能把喜欢落实成选择和调整，你会更信任这段关系。",
    blindSpot: "长期回避问题、用暧昧替代沟通、只会甜言蜜语但不修复，会让你迅速降温。",
    idealDynamic: "既心动，也清醒；既浪漫，也能复盘。两个人不是被关系推着走，而是一起把关系往前带。",
    partnerCue: "角色适合坦诚表达、主动复盘、尊重边界；不要用谜语式暧昧或单方面情绪拉扯来制造吸引。",
    memoryLine: "用户的恋爱互动偏好偏向清醒共建型：重视坦诚沟通、边界协商、问题修复和行动兑现。"
  },
  {
    id: "tide",
    name: "潮汐深潜型",
    subtitle: "慢热、深情、需要真实连接",
    description: "你的恋爱不是很快燃起的烟花，更像潮汐和深水。你可能表面克制，但一旦确认安全和深度，就会把关系看得很认真。你需要的不只是陪伴，而是某种真实连接：对方愿意进入更深的对话，也愿意理解你的复杂和沉默。",
    maleDetail: "男性潮汐深潜型深沉内敛、慢热专一，常用长久陪伴和默默解决问题表达深情。短板是不擅长主动表达，升温慢，容易让急性子的伴侣误会。",
    femaleDetail: "女性潮汐深潜型温柔内敛、情感细腻，重视信任和精神默契，一旦确认关系会很深情。短板是脆弱不易外露，感到敷衍或背叛时会迅速退缩。",
    relationshipNeed: "你需要深度、耐心和精神连接。对方不必一直热闹，但要能在关键时刻进入你的真实世界。",
    blindSpot: "浅层热闹、频繁转移话题、对复杂情绪缺乏耐心，会让你觉得关系停在表面。",
    idealDynamic: "慢慢靠近，深深理解。两个人可以安静，也可以认真谈那些不容易说出口的部分。",
    partnerCue: "角色适合放慢节奏，多承接深层表达；少用密集玩笑打断情绪，也不要过早要求明确回应。",
    memoryLine: "用户的恋爱互动偏好偏向潮汐深潜型：慢热深情，重视精神连接、深度对话和耐心陪伴。"
  }
];

const currentPage = ref<PageKey>("chat");
const visitorId = ref(localStorage.getItem(VISITOR_KEY) || "");
const loveAnswers = ref<Record<string, number>>(loadLoveAnswers(localStorage.getItem(VISITOR_KEY) || ""));
const loveGender = ref<LoveGender>(loadLoveGender(localStorage.getItem(VISITOR_KEY) || ""));
const showLoveResultModal = ref(false);
const messageListRef = ref<HTMLElement | null>(null);
const characters = ref<CharacterCard[]>([]);
const selectedCharacterId = ref("");
const activeCharacter = computed(() => characters.value.find((item) => item.id === selectedCharacterId.value) || null);
const sessionId = ref("");
const messages = ref<ChatMessage[]>([]);
const draft = ref("");
const busy = ref(false);
const error = ref("");
const memoryPane = ref<MemoryPane | null>(null);
const promptSlots = ref<ContextSlot[]>([]);
const characterState = ref<CharacterState | null>(null);
const characterBond = ref<CharacterBond | null>(null);
const manualNoteDraft = ref("");
const memoryFilter = ref<"all" | "global" | "character" | "session" | "recall">("all");
const editingMemoryId = ref("");
const memoryDraft = ref<MemoryPatch>({});
const expandedMemoryId = ref("");
const expandedSlotKey = ref("");
const stateExpanded = ref(false);
const bondExpanded = ref(false);

const includedSlots = computed(() => promptSlots.value.filter((slot) => slot.included));
const excludedSlots = computed(() => promptSlots.value.filter((slot) => !slot.included));
const filteredMemories = computed(() => {
  if (!memoryPane.value) return [];
  if (memoryFilter.value === "recall") return memoryPane.value.last_recall || [];
  if (memoryFilter.value === "all") return memoryPane.value.memories;
  return memoryPane.value.memories.filter((memory) => memory.memory_scope === memoryFilter.value);
});
const recallCount = computed(() => memoryPane.value?.last_recall?.length || 0);
const energyPercent = computed(() => Math.round((characterState.value?.energy || 0) * 100));
const resonancePercent = computed(() => Math.round((characterState.value?.resonance || 0) * 100));
const bondPercent = computed(() => Math.round((characterBond.value?.resonance_base || 0) * 100));
const loveProgress = computed(() => Object.keys(loveAnswers.value).length);
const loveProgressPercent = computed(() => Math.round((loveProgress.value / loveQuestions.length) * 100));
const loveDimensionLabels: Record<LoveDimension, string> = {
  warmth: "情绪温度",
  space: "边界留白",
  initiative: "主动推进",
  security: "安全确认",
  depth: "深度连接",
  playfulness: "轻盈火花"
};
const loveScores = computed<Record<LoveDimension, number>>(() => {
  const scores: Record<LoveDimension, number> = { warmth: 0, space: 0, initiative: 0, security: 0, depth: 0, playfulness: 0 };
  for (const question of loveQuestions) {
    const answerIndex = loveAnswers.value[question.id];
    const option = question.options[answerIndex];
    if (!option) continue;
    for (const [key, value] of Object.entries(option.scores)) {
      scores[key as LoveDimension] += value || 0;
    }
  }
  return scores;
});
const loveDimensionEntries = computed(() => Object.entries(loveScores.value) as [LoveDimension, number][]);
const loveDimensionMax = computed<Record<LoveDimension, number>>(() => {
  const maxScores: Record<LoveDimension, number> = { warmth: 0, space: 0, initiative: 0, security: 0, depth: 0, playfulness: 0 };
  for (const question of loveQuestions) {
    for (const dimension of Object.keys(maxScores) as LoveDimension[]) {
      maxScores[dimension] += Math.max(...question.options.map((option) => option.scores[dimension] || 0));
    }
  }
  return maxScores;
});
const profileRanks = computed(() => {
  const scores = loveScores.value;
  const ranks = [
    { id: "harbor", score: scores.security * 1.35 + scores.warmth * 0.7 + scores.depth * 0.35 },
    { id: "spark", score: scores.playfulness * 1.25 + scores.initiative * 1.05 + scores.warmth * 0.25 },
    { id: "garden", score: scores.space * 1.45 + scores.security * 0.35 + scores.depth * 0.25 },
    { id: "lantern", score: scores.warmth * 1.25 + scores.depth * 0.8 + scores.security * 0.25 },
    { id: "compass", score: scores.security * 0.85 + scores.initiative * 0.65 + scores.depth * 0.55 + scores.space * 0.25 },
    { id: "tide", score: scores.depth * 1.45 + scores.space * 0.5 + scores.warmth * 0.35 }
  ];
  return ranks.sort((left, right) => right.score - left.score);
});
const loveResult = computed(() => {
  if (loveProgress.value < loveQuestions.length) return null;
  const top = profileRanks.value[0]?.id || "harbor";
  return loveProfiles.find((profile) => profile.id === top) || loveProfiles[0];
});
const selectedLoveDetail = computed(() => {
  if (!loveResult.value) return "";
  return loveGender.value === "female" ? loveResult.value.femaleDetail : loveResult.value.maleDetail;
});
const loveProfileImageUrl = computed(() => {
  if (!loveResult.value) return "";
  const suffix = loveGender.value === "female" ? "女" : "男";
  return `/personality/${encodeURIComponent(`${loveResult.value.name}${suffix}.png`)}`;
});
const hasCompleteLoveTest = computed(() => loveProgress.value === loveQuestions.length);
const memoryCounts = computed(() => {
  const memories = memoryPane.value?.memories || [];
  return {
    all: memories.length,
    global: memories.filter((memory) => memory.memory_scope === "global").length,
    character: memories.filter((memory) => memory.memory_scope === "character").length,
    session: memories.filter((memory) => memory.memory_scope === "session").length,
    recall: recallCount.value
  };
});

function loveBarWidth(dimension: LoveDimension, value: number) {
  const max = loveDimensionMax.value[dimension] || 1;
  return Math.min(100, Math.round((value / max) * 100));
}

function setPage(page: PageKey) {
  currentPage.value = page;
}

function answerLoveQuestion(questionId: string, optionIndex: number) {
  const wasComplete = hasCompleteLoveTest.value;
  loveAnswers.value = { ...loveAnswers.value, [questionId]: optionIndex };
  saveLoveAnswers();
  if (!wasComplete && Object.keys(loveAnswers.value).length === loveQuestions.length) {
    showLoveResultModal.value = true;
  }
}

function resetLoveTest() {
  loveAnswers.value = {};
  showLoveResultModal.value = false;
  localStorage.removeItem(loveStorageKey(visitorId.value));
}

function setLoveGender(gender: LoveGender) {
  loveGender.value = gender;
  localStorage.setItem(loveGenderStorageKey(visitorId.value), gender);
}

function loveStorageKey(id: string) {
  return `${LOVE_TEST_KEY}:${id || "anonymous"}`;
}

function loveGenderStorageKey(id: string) {
  return `${LOVE_TEST_KEY}:gender:${id || "anonymous"}`;
}

function saveLoveAnswers() {
  localStorage.setItem(loveStorageKey(visitorId.value), JSON.stringify({ version: LOVE_TEST_VERSION, answers: loveAnswers.value }));
}

function loadLoveAnswers(id: string) {
  try {
    const raw = localStorage.getItem(loveStorageKey(id));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as { version?: string; answers?: Record<string, number> };
    if (parsed.version !== LOVE_TEST_VERSION || !parsed.answers) return {};
    return Object.fromEntries(Object.entries(parsed.answers).filter(([questionId]) => loveQuestions.some((question) => question.id === questionId)));
  } catch {
    return {};
  }
}

function loadLoveGender(id: string): LoveGender {
  return localStorage.getItem(loveGenderStorageKey(id)) === "male" ? "male" : "female";
}

function refreshLoveTestForVisitor(id: string) {
  loveAnswers.value = loadLoveAnswers(id);
  loveGender.value = loadLoveGender(id);
  showLoveResultModal.value = false;
}

function wrapCanvasText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines = 8) {
  let line = "";
  let lines = 0;
  for (const char of text) {
    const testLine = line + char;
    if (ctx.measureText(testLine).width > maxWidth && line) {
      ctx.fillText(line, x, y);
      y += lineHeight;
      lines += 1;
      line = char;
      if (lines >= maxLines) return y;
    } else {
      line = testLine;
    }
  }
  if (line && lines < maxLines) {
    ctx.fillText(line, x, y);
    y += lineHeight;
  }
  return y;
}

function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  });
}

async function saveLoveResultImage() {
  if (!loveResult.value) return;
  const profile = loveResult.value;
  try {
    const modalElement = document.querySelector('.love-modal') as HTMLElement | null;
    if (!modalElement) return;

    // 隐藏不想出现在截图里的按钮
    const actionsBlock = document.querySelector('.modal-actions') as HTMLElement | null;
    const closeBtn = document.querySelector('.modal-close') as HTMLElement | null;
    if (actionsBlock) actionsBlock.style.display = 'none';
    if (closeBtn) closeBtn.style.display = 'none';

    // 提升截屏区域样式保证完整度
    // 强制去除滚动条等会导致截图尺寸被截断的问题
    const oldMaxHeight = modalElement.style.maxHeight;
    const oldOverflow = modalElement.style.overflow;
    modalElement.style.maxHeight = 'none';
    modalElement.style.overflow = 'visible';

    const canvas = await html2canvas(modalElement, {
      backgroundColor: '#121511',
      scale: 2, // 高清渲染
      useCORS: true,
      logging: false
    });

    // 恢复原有样式
    modalElement.style.maxHeight = oldMaxHeight;
    modalElement.style.overflow = oldOverflow;
    if (actionsBlock) actionsBlock.style.display = '';
    if (closeBtn) closeBtn.style.display = '';

    const anchor = document.createElement("a");
    anchor.href = canvas.toDataURL("image/png");
    anchor.download = `${profile.name}-${loveGender.value === "female" ? "女" : "男"}-恋爱人格结果.png`;
    anchor.click();
  } catch(e) {
    console.error("生成图片失败: ", e);
  }
}

async function applyLoveProfileToMemory() {
  if (!sessionId.value || !memoryPane.value || !loveResult.value) return;
  const result = loveResult.value;
  const note = [
    memoryPane.value.manual_note,
    `[恋爱人格测试] ${result.memoryLine} 核心需求：${result.relationshipNeed} 角色互动建议：${result.partnerCue}`
  ].filter(Boolean).join("\n");
  manualNoteDraft.value = note;
  busy.value = true;
  error.value = "";
  try {
    memoryPane.value = await patchMemory(sessionId.value, { manual_note: note });
    currentPage.value = "chat";
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    const resolved = await resolveVisitor(visitorId.value);
    visitorId.value = resolved.visitor_id;
    localStorage.setItem(VISITOR_KEY, resolved.visitor_id);
    refreshLoveTestForVisitor(resolved.visitor_id);
    characters.value = await listCharacters();
    selectedCharacterId.value = characters.value[0]?.id || "";
    if (selectedCharacterId.value) {
      await openSession();
    }
  } catch (err) {
    error.value = readableError(err);
  }
});

async function openSession() {
  if (!selectedCharacterId.value || !visitorId.value) return;
  busy.value = true;
  error.value = "";
  try {
    refreshLoveTestForVisitor(visitorId.value);
    const session = await createSession(visitorId.value, selectedCharacterId.value);
    sessionId.value = session.session_id;
    characterState.value = session.character_state;
    characterBond.value = session.character_bond;
    memoryPane.value = session.memory_pane;
    manualNoteDraft.value = session.memory_pane.manual_note || "";
    promptSlots.value = session.memory_pane.prompt_slots || [];
    messages.value = session.messages?.length
      ? session.messages
      : [{ id: "opening", role: "assistant", content: session.character.opening_line }];

    await nextTick();
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
    }
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function submit() {
  const text = draft.value.trim();
  if (!text || !sessionId.value || busy.value) return;
  const optimistic: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: text };
  messages.value.push(optimistic);
  draft.value = "";
  busy.value = true;
  error.value = "";

  await nextTick();
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
  }

  try {
    const response = await sendMessage(visitorId.value, sessionId.value, text);
    messages.value.push(response.message);
    characterState.value = response.character_state;
    characterBond.value = response.character_bond;
    memoryPane.value = response.memory_pane;
    manualNoteDraft.value = response.memory_pane.manual_note || "";
    promptSlots.value = response.prompt_slots;

    await nextTick();
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
    }
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function saveMemoryNote() {
  if (!sessionId.value || !memoryPane.value) return;
  busy.value = true;
  try {
    memoryPane.value = await patchMemory(sessionId.value, { manual_note: manualNoteDraft.value });
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function toggleFreeze() {
  if (!sessionId.value || !memoryPane.value) return;
  busy.value = true;
  try {
    memoryPane.value = await patchMemory(sessionId.value, { frozen: !memoryPane.value.frozen });
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

function readableError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function startEditMemory(memory: MemoryItem) {
  editingMemoryId.value = memory.id;
  memoryDraft.value = {
    memory_type: memory.memory_type,
    memory_scope: memory.memory_scope,
    content: memory.content,
    confidence: memory.confidence,
    importance: memory.importance
  };
}

function cancelEditMemory() {
  editingMemoryId.value = "";
  memoryDraft.value = {};
}

async function saveMemoryItem(memoryId: string) {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    memoryPane.value = await updateMemoryItem(sessionId.value, memoryId, memoryDraft.value);
    cancelEditMemory();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

async function removeMemoryItem(memoryId: string) {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    memoryPane.value = await deleteMemoryItem(sessionId.value, memoryId);
    if (editingMemoryId.value === memoryId) cancelEditMemory();
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}

function toggleMemoryDetails(memoryId: string) {
  expandedMemoryId.value = expandedMemoryId.value === memoryId ? "" : memoryId;
}

function toggleSlotDetails(slotKey: string) {
  expandedSlotKey.value = expandedSlotKey.value === slotKey ? "" : slotKey;
}

async function exportDebugBundle() {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    const payload = await exportSession(sessionId.value);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `campus-pulse-${sessionId.value}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    error.value = readableError(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="shell" :class="{ 'test-shell': currentPage === 'love-test' }">
    <aside class="left-panel">
      <div class="brand">
        <span class="brand-mark"></span>
        <div>
          <h1>Campus Pulse Lite</h1>
          <p>persona memory lab</p>
        </div>
      </div>

      <nav class="page-nav">
        <button :class="{ active: currentPage === 'chat' }" @click="setPage('chat')">聊天</button>
        <button :class="{ active: currentPage === 'love-test' }" @click="setPage('love-test')">恋爱人格测试</button>
      </nav>

      <label v-if="currentPage === 'chat'" class="field">
        <span>Visitor ID</span>
        <input v-model="visitorId" @change="openSession" spellcheck="false" />
      </label>

      <section v-if="currentPage === 'chat'" class="character-list">
        <button
          v-for="character in characters"
          :key="character.id"
          class="character-row"
          :class="{ active: character.id === selectedCharacterId }"
          @click="selectedCharacterId = character.id; openSession()"
        >
          <span class="portrait" :style="{ '--accent': character.visual?.accent || '#8da2c8' }"></span>
          <span>
            <strong>{{ character.name }}</strong>
            <small>{{ character.archetype }}</small>
          </span>
        </button>
      </section>

      <section v-if="currentPage === 'chat' && activeCharacter" class="character-brief">
        <p class="eyebrow">Character Card</p>
        <h3>{{ activeCharacter.name }}</h3>
        <p>{{ activeCharacter.personality || activeCharacter.bio }}</p>
        <dl>
          <div>
            <dt>Scenario</dt>
            <dd>{{ activeCharacter.scenario || "校园轻陪伴聊天" }}</dd>
          </div>
          <div>
            <dt>Rhythm</dt>
            <dd>{{ activeCharacter.voice?.sentence_rhythm || activeCharacter.speech_style }}</dd>
          </div>
          <div>
            <dt>Dynamic Action</dt>
            <dd>{{ activeCharacter.interaction_policy?.action_style || "按当前语境动态生成，低密度，不抢话" }}</dd>
          </div>
        </dl>
      </section>

      <section v-if="currentPage === 'love-test'" class="character-brief">
        <p class="eyebrow">Love Type</p>
        <h3>相处风格校准</h3>
        <p>这不是严肃诊断，也不会替角色推进剧情。它只把你的偏好转成可解释的互动建议。</p>
        <div class="gender-toggle">
          <button :class="{ active: loveGender === 'female' }" @click="setLoveGender('female')">女性画像</button>
          <button :class="{ active: loveGender === 'male' }" @click="setLoveGender('male')">男性画像</button>
        </div>
        <div v-if="loveResult" class="love-type-art" :style="{ backgroundImage: `url('${loveProfileImageUrl}')` }">
          <span>{{ loveResult.name }}</span>
        </div>
        <div v-else class="love-type-art pending">
          <span>答完后生成画像</span>
        </div>
        <dl>
          <div>
            <dt>Progress</dt>
            <dd>{{ loveProgress }} / {{ loveQuestions.length }}</dd>
          </div>
          <div>
            <dt>Apply</dt>
            <dd>完成后可写入手动记忆，让当前角色知道怎样靠近你更舒服。</dd>
          </div>
        </dl>
      </section>
    </aside>

    <section v-if="currentPage === 'chat'" class="chat-panel">
      <header class="chat-header" v-if="activeCharacter">
        <div>
          <p class="eyebrow">{{ activeCharacter.archetype }}</p>
          <h2>{{ activeCharacter.name }}</h2>
          <span>{{ activeCharacter.tagline }}</span>
          <div v-if="characterBond" class="header-growth">
            <small>{{ characterBond.familiarity_stage }}</small>
            <small>Resonance {{ bondPercent }}%</small>
          </div>
        </div>
        <div class="header-actions">
          <button class="ghost muted" @click="exportDebugBundle">Export</button>
          <div class="status" :class="{ busy }">{{ busy ? "thinking" : "ready" }}</div>
        </div>
      </header>

      <div class="message-list" ref="messageListRef">
        <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
          <span>{{ message.role === "user" ? "你" : activeCharacter?.name || "角色" }}</span>
          <p>{{ message.content }}</p>
        </article>
      </div>

      <form class="composer" @submit.prevent="submit">
        <textarea
          v-model="draft"
          :disabled="busy"
          rows="3"
          placeholder="输入这一轮想说的话"
          @keydown.enter.exact.prevent="submit"
        />
        <button :disabled="busy || !draft.trim()">Send</button>
      </form>

      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section v-else class="love-test-panel">
      <header class="love-hero" :class="{ 'no-progress': true }">
        <div>
          <p class="eyebrow">Love Type Calibration</p>
          <h2>恋爱人格测试</h2>
          <p>用 20 道轻量选择题，把“我希望怎样被靠近”变成角色能使用的相处偏好。</p>
        </div>
      </header>

      <section class="love-layout">
        <div class="love-questions">
          <article v-for="(question, index) in loveQuestions" :key="question.id" class="love-question">
            <div class="question-title">
              <span>{{ String(index + 1).padStart(2, "0") }}</span>
              <h3>{{ question.title }}</h3>
            </div>
            <div class="love-options">
              <button
                v-for="(option, optionIndex) in question.options"
                :key="option.label"
                :class="{ selected: loveAnswers[question.id] === optionIndex }"
                @click="answerLoveQuestion(question.id, optionIndex)"
              >
                <strong>{{ option.label }}</strong>
                <small>{{ option.text }}</small>
              </button>
            </div>
          </article>
        </div>

        <aside class="love-result">
          <div class="love-progress">
            <span>{{ loveProgressPercent }}%</span>
            <i><b :style="{ width: `${loveProgressPercent}%` }"></b></i>
          </div>
          <p class="eyebrow">Progress</p>
          <h3>{{ hasCompleteLoveTest ? "测试完成" : `还差 ${loveQuestions.length - loveProgress} 题` }}</h3>
          <p>结果会在全部答完后以弹窗展示，避免提前暴露类型影响选择。</p>
          <div class="dimension-bars">
            <label v-for="[dimension, value] in loveDimensionEntries" :key="dimension">
              <span>{{ loveDimensionLabels[dimension] }} {{ value }}</span>
              <i><b :style="{ width: `${loveBarWidth(dimension, value)}%` }"></b></i>
            </label>
          </div>
          <button v-if="hasCompleteLoveTest" class="wide" @click="showLoveResultModal = true">查看结果</button>
          <button class="ghost muted" @click="resetLoveTest">重新测试</button>
          <p v-if="error" class="error">{{ error }}</p>
        </aside>
      </section>
    </section>

    <div v-if="showLoveResultModal && loveResult" class="modal-backdrop" @click.self="showLoveResultModal = false">
      <section class="love-modal">
        <button class="modal-close" @click="showLoveResultModal = false">Close</button>
        <div class="modal-art" :style="{ backgroundImage: `url('${loveProfileImageUrl}')` }"></div>
        <div class="modal-copy">
          <p class="eyebrow">Love Type Result</p>
          <h3>{{ loveResult.name }}</h3>
          <strong>{{ loveGender === "female" ? "女性画像" : "男性画像" }} · {{ loveResult.subtitle }}</strong>
          <p>{{ loveResult.description }}</p>
          <p>{{ selectedLoveDetail }}</p>
          <div class="result-cue">
            <span>恋爱核心需求</span>
            <p>{{ loveResult.relationshipNeed }}</p>
          </div>
          <div class="result-cue">
            <span>容易踩雷</span>
            <p>{{ loveResult.blindSpot }}</p>
          </div>
          <div class="result-cue">
            <span>理想关系动态</span>
            <p>{{ loveResult.idealDynamic }}</p>
          </div>
          <div class="result-cue">
            <span>角色互动建议</span>
            <p>{{ loveResult.partnerCue }}</p>
          </div>
          <div class="dimension-bars">
            <label v-for="[dimension, value] in loveDimensionEntries" :key="dimension">
              <span>{{ loveDimensionLabels[dimension] }} {{ value }}</span>
              <i><b :style="{ width: `${loveBarWidth(dimension, value)}%` }"></b></i>
            </label>
          </div>
        </div>
        <div class="modal-actions">
          <button class="wide" @click="saveLoveResultImage">保存结果图片</button>
          <button class="wide ghost" :disabled="busy || !sessionId" @click="applyLoveProfileToMemory">写入当前角色记忆</button>
        </div>
      </section>
    </div>

    <aside v-if="currentPage === 'chat'" class="right-panel">
      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">State</p>
            <h3>{{ characterState?.mood || "No state" }}</h3>
          </div>
          <button class="ghost muted" @click="stateExpanded = !stateExpanded">{{ stateExpanded ? "Hide" : "Detail" }}</button>
        </div>

        <section v-if="characterState" class="state-strip side-strip">
          <button class="state-summary" type="button" @click="stateExpanded = !stateExpanded">
            <span>
              <small>Tone</small>
              <strong>{{ characterState.tone }}</strong>
            </span>
            <span>
              <small>Distance</small>
              <strong>{{ characterState.distance }}</strong>
            </span>
            <span class="state-focus">
              <small>Focus</small>
              <strong>{{ characterState.focus }}</strong>
            </span>
          </button>
          <div class="state-bars">
            <label>
              <span>Energy {{ energyPercent }}%</span>
              <i><b :style="{ width: `${energyPercent}%` }"></b></i>
            </label>
            <label>
              <span>Resonance {{ resonancePercent }}%</span>
              <i><b :style="{ width: `${resonancePercent}%` }"></b></i>
            </label>
          </div>
          <dl v-if="stateExpanded" class="state-detail">
            <div>
              <dt>Pace</dt>
              <dd>{{ characterState.behavior.pace }}</dd>
            </div>
            <div>
              <dt>Initiative</dt>
              <dd>{{ characterState.behavior.initiative }}</dd>
            </div>
            <div>
              <dt>Warmth</dt>
              <dd>{{ characterState.behavior.warmth }}</dd>
            </div>
            <div>
              <dt>Memory Use</dt>
              <dd>{{ characterState.behavior.memory_use }}</dd>
            </div>
            <div>
              <dt>Avoid</dt>
              <dd>{{ characterState.behavior.avoid }}</dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>{{ characterState.last_shift || characterState.evidence }}</dd>
            </div>
          </dl>
        </section>
      </section>

      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">Bond</p>
            <h3>{{ characterBond?.familiarity_stage || "No bond" }}</h3>
          </div>
          <button class="ghost muted" @click="bondExpanded = !bondExpanded">{{ bondExpanded ? "Hide" : "Detail" }}</button>
        </div>

        <section v-if="characterBond" class="bond-strip side-strip">
          <button class="bond-summary" type="button" @click="bondExpanded = !bondExpanded">
            <span>
              <small>Base Resonance</small>
              <strong>{{ bondPercent }}%</strong>
            </span>
            <span class="bond-preference">
              <small>Preference</small>
              <strong>{{ characterBond.interaction_preferences }}</strong>
            </span>
          </button>
          <dl v-if="bondExpanded" class="bond-detail">
            <div>
              <dt>Trust</dt>
              <dd>{{ characterBond.trust_notes }}</dd>
            </div>
            <div>
              <dt>Boundary</dt>
              <dd>{{ characterBond.boundary_notes }}</dd>
            </div>
            <div>
              <dt>Milestones</dt>
              <dd>{{ characterBond.milestones.length ? characterBond.milestones.join(" / ") : "暂无关键节点" }}</dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>{{ characterBond.evidence }}</dd>
            </div>
          </dl>
        </section>
      </section>

      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">Memory</p>
            <h3>{{ memoryPane?.frozen ? "Frozen" : "Live" }}</h3>
          </div>
          <button class="ghost" @click="toggleFreeze">{{ memoryPane?.frozen ? "Unfreeze" : "Freeze" }}</button>
        </div>

        <textarea v-model="manualNoteDraft" class="note" rows="4" placeholder="手动记忆" />
        <button class="wide" @click="saveMemoryNote">Save note</button>

        <div class="memory-tabs">
          <button :class="{ active: memoryFilter === 'all' }" @click="memoryFilter = 'all'">All {{ memoryCounts.all }}</button>
          <button :class="{ active: memoryFilter === 'global' }" @click="memoryFilter = 'global'">Global {{ memoryCounts.global }}</button>
          <button :class="{ active: memoryFilter === 'character' }" @click="memoryFilter = 'character'">Role {{ memoryCounts.character }}</button>
          <button :class="{ active: memoryFilter === 'session' }" @click="memoryFilter = 'session'">Session {{ memoryCounts.session }}</button>
          <button :class="{ active: memoryFilter === 'recall' }" @click="memoryFilter = 'recall'">Recall {{ memoryCounts.recall }}</button>
        </div>

        <div class="memory-list">
          <div v-for="memory in filteredMemories" :key="memory.id" class="memory-item">
            <template v-if="editingMemoryId === memory.id">
              <div class="memory-edit-grid">
                <label>
                  <span>Scope</span>
                  <select v-model="memoryDraft.memory_scope">
                    <option value="global">global</option>
                    <option value="character">character</option>
                    <option value="session">session</option>
                  </select>
                </label>
                <label>
                  <span>Type</span>
                  <select v-model="memoryDraft.memory_type">
                    <option value="stable_user_info">stable_user_info</option>
                    <option value="user_preference">user_preference</option>
                    <option value="relationship_progress">relationship_progress</option>
                    <option value="open_thread">open_thread</option>
                    <option value="recent_emotion">recent_emotion</option>
                  </select>
                </label>
              </div>
              <textarea v-model="memoryDraft.content" class="note compact" rows="3" />
              <label class="range-field">
                <span>Importance {{ Math.round(Number(memoryDraft.importance || 0) * 100) }}%</span>
                <input v-model.number="memoryDraft.importance" type="range" min="0" max="1" step="0.05" />
              </label>
              <div class="memory-actions">
                <button class="ghost" @click="saveMemoryItem(memory.id)">Save</button>
                <button class="ghost muted" @click="cancelEditMemory">Cancel</button>
              </div>
            </template>
            <template v-else>
              <div class="memory-meta">
                <button class="memory-title" @click="toggleMemoryDetails(memory.id)">
                  {{ memory.memory_scope }} / {{ memory.memory_type }}
                </button>
                <div class="memory-actions">
                  <button @click="startEditMemory(memory)">Edit</button>
                  <button @click="removeMemoryItem(memory.id)">Delete</button>
                </div>
              </div>
              <div class="score-row">
                <span>importance {{ Math.round(memory.importance * 100) }}%</span>
                <span>confidence {{ Math.round(memory.confidence * 100) }}%</span>
              </div>
              <p>{{ memory.content }}</p>
              <dl v-if="expandedMemoryId === memory.id" class="detail-grid">
                <div>
                  <dt>ID</dt>
                  <dd>{{ memory.id }}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{{ memory.source_message_id || "manual / unknown" }}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{{ memory.created_at }}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{{ memory.updated_at }}</dd>
                </div>
              </dl>
            </template>
          </div>
          <div v-if="!filteredMemories.length" class="empty">No memory in this view.</div>
        </div>
      </section>

      <section class="memory-section">
        <div class="section-title">
          <div>
            <p class="eyebrow">Prompt Stack</p>
            <h3>{{ includedSlots.length }} included</h3>
          </div>
        </div>

        <div class="slot-list">
          <div v-for="slot in includedSlots" :key="slot.key" class="slot-item" :class="{ expanded: expandedSlotKey === slot.key }">
            <div @click="toggleSlotDetails(slot.key)">
              <strong>{{ slot.key }}</strong>
              <span>{{ slot.priority }} / {{ slot.token_budget }}</span>
            </div>
            <p>{{ slot.content }}</p>
            <dl v-if="expandedSlotKey === slot.key" class="detail-grid">
              <div>
                <dt>Role</dt>
                <dd>{{ slot.role }}</dd>
              </div>
              <div>
                <dt>Included</dt>
                <dd>{{ slot.included ? "yes" : "no" }}</dd>
              </div>
              <div>
                <dt>Budget</dt>
                <dd>{{ slot.token_budget }}</dd>
              </div>
            </dl>
          </div>
          <div v-if="excludedSlots.length" class="excluded">{{ excludedSlots.length }} excluded by budget</div>
        </div>
      </section>
    </aside>
  </main>
</template>
