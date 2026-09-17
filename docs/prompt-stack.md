# Easel Prompt Stack

> OpenClaw agent 的 prompt 由多层文件组合而成，每层职责明确、互不干扰。

## 组合顺序

```
Layer 1: SOUL.md         人格 + 能力总览（搭子语气、沟通风格、对五层能力的自我认知）
Layer 2: AGENTS.md       分工规则 + 编排逻辑 + Plan Mode + 制作层执行流程
Layer 3: CONTEXT.md      项目路径信息（sync.sh 自动生成，包含 outputs/assets/profiles 路径）
Layer 4: SKILL           被触发时加载 SKILL.md + 按需读取 references/ 下的文件
```

> **画像（Profile）如何进入 prompt**：不再写全局 USER.md（会有并发竞态）。CLI 与 Web 统一把画像**作为消息内联**传入，由 OpenClaw 按 AGENTS.md 自行读取 `profiles/<X>/` 并凝练。每个请求自包含，无全局文件污染。
> - **Web / skill**（单轮）：每条消息前缀 `我当前使用的画像是「X」。`（`easel/persona.py:persona_prefix`）。
> - **CLI `easel chat`**（多轮交互）：选画像后经 `openclaw chat --message "<同一前缀>"` 注入为**初始消息**，画像随 session 历史留存供后续 turn 沿用（超长会话被压缩后可能丢，属已知取舍）。
> - 三入口的画像逻辑统一收敛到 `easel/persona.py`（`list_personas` / `load_profile_text` / `persona_prefix`）。

> **记忆作用域**：Easel 不使用 OpenClaw 根目录的全局 `MEMORY.md` 承载账号知识；该文件由同步脚本保持为空。账号长期记忆只存放在 `profiles/<当前画像>/memory.md`，每个会话按自身绑定的画像直接读取。通用模式不读取任何画像记忆，也不通过动态改写全局文件切换画像。

## 各层说明

### Layer 1 — SOUL.md（常驻）
定义 agent 的**人格**（创作者的社媒内容"搭子"：懂策略、能上手、务实诚实）、沟通方式，以及一份**能力总览**，让 agent 心里有数、遇事先想"怎么帮他做成"而不是"我做不了"。所有 turn 都在 system prompt 中。
保持精简且**类目级**：能力总览按五层写"能做什么"，**不写具体 skill 名**（避免像 weibo 那样过时）、也**不写"去调某某 skill"这类操作机制**（那属 AGENTS 与技能库）；语气是好伙伴，不是工具说明书。

### Layer 2 — AGENTS.md（常驻）
核心业务逻辑：五层分工、Plan Mode 触发规则、纵向编排原则、制作层执行全流程。
所有 turn 都在 system prompt 中。是最重要的文件。

### Layer 3 — CONTEXT.md（半静态）
由 `sync.sh` 生成，包含项目绝对路径。换机器后重新跑 sync.sh 自动更新。
OpenClaw 跑项目脚本前从这里读取项目根路径——**先 `cd` 到该目录再跑脚本（不支持 `--cwd`）**。

### Layer 4 — SKILL（按需）
只有当 SKILL 被触发时才加载。加载顺序：
1. SKILL.md 主体（执行流程）
2. references/ 下的文件（按 SKILL.md 中的引用按需读取）
3. scripts/ 下的脚本（执行时调用，脚本本身不进 prompt）

> 五层 SKILL（含制作层）都完整同步进 OpenClaw workspace，OpenClaw 读进来照其流程自己执行、产出成品到 `outputs/`。

## 设计原则

- 每层只管自己的事，不越界
- 常驻层（1-3）保持精简，控制 token 消耗
- SKILL 层按需加载，不用的不加载
- references/ 里的文件只在 SKILL 执行过程中被读取，不常驻


## 热点入口的来源上下文

热点雷达和工作台“今日热点”通过 `web/frontend/src/lib/topicPrompt.ts` 构造用户消息，包含热点标题、来源平台和热榜返回的原始链接。消息沿现有对话 API 传给 OpenClaw，并随聊天记录保存；刷新及不删除来源文本的重试/编辑重发会保留这些信息。

- 热榜链接可能指向搜索页或讨论页，不代表已取得事件的一手原文。
- 链接缺失或不是 HTTP(S) 地址时，明确标记“未提供”，不根据标题构造链接。
- 热点收藏将平台和原链接存入选题的 `topicSource` 字段；选题库及工作台待做选题入口均传递该字段。编辑和状态推进保留来源；旧客户端编辑未传该字段时，后端保留原值。
- 手动新增、历史选题没有来源信息时仍可做内容，明确标记平台/链接“未提供”，不猜补链接。
- “做内容”同时传递结构化来源，交给后端按核心事件取证、写作和逐项复核；详见 [热点取证与写作](hot-topic-evidence.md)。

验证（在 `web/frontend` 下，Node.js 22.18+ 或 24）：`npm test`、`npm run build`。
手动验收：分别从热点雷达和工作台点击同一个热点，确认对话首条消息包含对应平台、完整链接；刷新后重试，确认来源仍在。再收藏热点，在选题库编辑备注、推进状态后点击做内容，确认平台和原链接仍保留；历史或手动选题应可发送且明确标记来源缺失。
