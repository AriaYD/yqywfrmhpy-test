# 上下文交接引擎（compact 前写交接，compact 后自动衔接）

解决的问题：长任务窗口涨到 90%+ 也不自动压缩，压缩后新上下文丢掉进度、忘掉硬约束、重做已完成的活。

## 一句话流程

```
70%  Stop hook 拦住这一轮 → Claude 先更新 PROGRESS.md + 写 .claude/handoff/HANDOFF.md
80%  CLI 自动 compact（CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80）
     ├─ PreCompact  → 快照机器事实到 facts.md，置 .pending
     └─ PostCompact → 把「必读文档 + 硬约束 + 手写断点 + 机器事实 + 恢复协议」打到 stdout，
                      Claude Code 将其作为消息注入压缩后的上下文
新窗口 SessionStart → 若 .pending 还在（说明是换窗口不是压缩），同样自动注入
```

`/handoff` 斜杠命令 = 手动触发第一步，换窗口前用。

## 组成

| 文件 | 作用 |
|---|---|
| `.claude/settings.json` | 注册 4 个 hook + `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80` |
| `.claude/hooks/handoff.py` | 引擎本体，6 个子命令：`guard` `precompact` `postcompact` `sessionstart` `build` `pct` |
| `.claude/commands/handoff.md` | `/handoff`，手动写断点交接 |
| `.claude/hooks/tests/test_handoff.py` | 自检，33 项 |
| `.claude/handoff/HANDOFF.md` | **Claude 亲手写的断点**（语义部分，机器写不出来的那些） |
| `.claude/handoff/facts.md` | 机器采集的事实：branch / commit / `git status` / 本会话改过的文件 / 未完成 Task / 最后几轮对话 |
| `.claude/handoff/archive/` | 每次注入留档 |

交接产物全部 gitignore（会话级状态，不进版本库）。

## 阈值怎么来的（CLI 2.1.220 实测/反编译核实，不是猜的）

```js
// 触发点
Sfo(W, o) = o.pct ? min(floor(W * pct/100), W - 13000) : W - 13000
uMu(tokens, W, ...) → tokens >= Sfo ? "compact" : ...
// 有效窗口
CSe(model) = 模型窗口 - min(最大输出, 20000)
SZc(model) = Wb/OH 判定原生 1M → 1e6，否则 200k
```

**模型窗口不是常数**，这点踩过坑：`claude-opus-5` 在支持的账号上是**原生 1M**，
有效窗口 980k；`claude-haiku-4-5` 这类是 200k，有效窗口 180k。
把 1M 当成 200k 会让 18% 被算成 95%，提醒全程误报。

| 模型 | 有效窗口 | 默认触发点（窗口−13k） | 设 80% 后的触发点 |
|---|---|---|---|
| opus-5 / sonnet-5 / fable-5（原生 1M） | 980k | 967k ≈ 98.7% | 784k = 80% |
| haiku-4.5 等 200k 模型 | 180k | 167k ≈ 93% | 144k = 80% |

`resolve_limit()` 三层判定：`CP_CTX_LIMIT` 显式指定 > 实测反推（跑到过 187k 以上必然不是 200k 窗口）
> 按模型名查表。`guard` 用同一个分母，默认 70% 提醒。

调阈值（环境变量，写进 `.claude/settings.json` 的 `env`）：

| 变量 | 默认 | 含义 |
|---|---|---|
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | `80` | CLI 自动压缩触发点（% of 有效窗口） |
| `CP_GUARD_PCT` | `70` | 提醒写交接的水位 |
| `CP_CTX_LIMIT` | 自动 | 分母。留空则按模型自动判定 980k / 180k |
| `CP_REFRESH_STEP` | `5` | 交接写过之后，再涨多少个百分点才重新提醒 |
| `CP_NOTIFY` | `action` | 右上角通知：`action` 只在真做了事时弹 / `all` 每次运行都弹 / `off` 不弹 |
| `CP_PROJECT_MARKER` | `CampusPath_Implementation_Plan_V2.md` | 项目身份标记，认不到就整体静默 |

## 只服务本项目

注入文案里写死了 CampusPath 的必读文档与硬约束，拿到别的项目会注入**错误的项目事实**，
所以做了两层隔离：

1. hook 注册在**项目级** `.claude/settings.json`，本来就只有本项目加载；
2. `handoff.py` 再认一次 `CampusPath_Implementation_Plan_V2.md`——
   调用方给的 `CLAUDE_PROJECT_DIR`/`cwd` 里没有这个文件就**全部子命令静默退出**，
   连 `.claude/handoff/` 目录都不建。（拿掉这层检查，自检里 4 条隔离测试会红。）

同理，全局 `~/.claude/hooks/pre_compact.sh` / `post_compact.sh` 里那套 handover
写死了 Polymarket 的项目事实，已限定只在 `~/AllProjects/polymarket_all`（含子目录）启用。

## 验证记录（2026-07-30，全部真机实跑）

| 项 | 方式 | 结果 |
|---|---|---|
| 自检 37 项 | `python3 .claude/hooks/tests/test_handoff.py` | 37 passed |
| 自检本身有效 | 五次变异：sidechain 过滤／`stop_hook_active` 防循环／PostCompact 不注入手写交接／项目标记检查／1M 窗口判定 | 各自只让对应的那些变红，还原后全绿 |
| 分母判定 | 拿本会话真实 transcript 跑 `handoff.py pct` | `{tokens:198904, pct:20.3, limit:980000, model:claude-opus-5}`，与状态栏显示一致 |
| 项目隔离 | 在临时的"别的项目"目录里跑四个子命令 | 全部静默、不建目录 |
| 全局 handover 收窄 | 用 CampusPath／alpha-feed／polymarket_all／其子目录各跑一次 | 前两者静默，后两者照常工作 |
| SessionStart 注入 | 造 `.pending` + 带标记的 HANDOFF.md，跑 `claude -p` 问模型是否看见该标记 | 模型答 YES 并复述所在小节；`.pending` 被消费、留档生成 |
| PreCompact 触发 | `claude -p "/compact"` | `facts.md` 落盘（该次因消息太少未真压缩，PostCompact 未走） |
| 全局 hook 让位 | 用本项目 cwd 与 `/tmp` 各跑一次全局 `pre_compact.sh` | 本项目让位、`/tmp` 照常工作 |

未直接实测：PostCompact 注入（headless 攒不出足够长的会话）。它与 SessionStart 共用同一个 `consume()` 渲染路径（已实测），且 CLI 侧「hook stdout 作为消息注入压缩后上下文」在二进制中已核实（`PostCompact [cmd] completed successfully: …` 计入 `compactedMessageCount`）。

## 已经踩过的一次：会话早于配置，四个 hook 一个都没生效

2026-07-30，一个会话涨到 **87%** 也没有任何提醒，也没有自动压缩。查下来：

| 事实 | 值 |
|---|---|
| 会话开始 | `2026-07-29T20:32:08Z` |
| `.claude/settings.json` 提交 | `2026-07-30T13:48:33Z` |
| 差 | 会话**早于**配置约 17 小时 |
| 该会话的 `.guard-<id>.json` | 不存在 → guard 一次都没被调用过 |

引擎本身没问题：喂给它那个会话的真实 transcript，`pct` 算出 87.0%，
`guard` 也正确返回 `decision: block`。**问题是这个进程里压根没注册 hook。**

真正的缺陷是**失效无声**——不报错、不警告，只有等到人自己觉得"怎么没动静"。
所以现在：

* `handoff.py status` 一条命令给出结论，判据是**这个 session_id 有没有留下过
  guard 状态文件**（guard 真跑过的唯一证据），而不是"配置文件写得对不对"——
  配置再对也不代表当前进程加载了它；
* `SessionStart` 在**没有**待交接时也打一行字，说明自己已武装、阈值是多少。
  它是唯一能在第一回合就证明引擎活着的地方，它不吭声，失效就必然无声。

```bash
python3 .claude/hooks/handoff.py status   # 看 armed 与 verdict
```

## 注意

- **hook 与 env 在会话启动时读取**：正在跑的窗口不会自动生效，要重启那个窗口。重启前先在旧窗口跑 `/handoff` 把断点写下来。
  改完配置后，**在新窗口跑一次 `status` 确认 `armed` 为 true**，别默认它生效了。
- 全局 `~/.claude/hooks/pre_compact.sh` / `post_compact.sh` 已改为：cwd 存在 `.claude/hooks/handoff.py` 就让位（否则会把别的项目的 handover 内容注进来）。
- `guard` 会 block 住 Stop。CLI 有连环 block 上限保护，且 `stop_hook_active=true` 时本 hook 一定放行，不会死循环。
- 临时关掉：`CP_GUARD_PCT=101`；彻底停用：把 `.claude/settings.json` 的 `hooks` 段删掉。
