export type LoveDimension = "warmth" | "space" | "initiative" | "security" | "depth" | "playfulness";

export interface LoveOption {
  label: string;
  text: string;
  scores: Partial<Record<LoveDimension, number>>;
}

export interface LoveQuestion {
  id: string;
  title: string;
  options: LoveOption[];
}

export interface LoveProfile {
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

export type LoveGender = "female" | "male";

export const loveQuestions: LoveQuestion[] = [
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

export const loveProfiles: LoveProfile[] = [
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

