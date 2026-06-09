# ROADMAP — Brilliancy

里程碑计划 v1.0 · 假设开发全部由 Claude Code 承担,Jerry 负责决策、内容把关、发布动作。
每个里程碑有**验收标准**和**可杀死点**(Kill criteria)——副业项目最大的风险是惯性,不是失败。

---

## 流程总览(小项目标准打法)

```
M0 骨架 → M1 核心玩法 → [验证点①: 儿子愿不愿意玩] → M2 内容流水线
→ M3 每日挑战+分享 → M4 付费墙 → M5 TestFlight → [验证点②: 留存数据]
→ M6 上架+发布周 → 之后: 每月内容增补 + 看数据迭代
```

原则:每个里程碑结束时 app 都能运行、能演示;先纵向打穿(一局棋完整体验),再横向铺量。

---

## M0 — 项目骨架(~1 个周末)

工程用 **XcodeGen** 管理(TECH_SPEC §2.1):Claude Code 在 Windows 写 `project.yml` + Swift 源文件,Jerry 在 Mac 上 `xcodegen generate` 后 build。`.xcodeproj` 不入库。

- Claude Code(Windows):repo + 这套文档 + `.gitattributes` + `.gitignore`(忽略 `*.xcodeproj/`);写 `project.yml`(scheme=Brilliancy, iOS 17)、SwiftUI 入口、模块目录骨架;接 GRDB、ChessKit;写 BoardView(显示局面、拖拽+点击走子、FEN 加载);pipeline venv 骨架
- Jerry(Mac,一次性):`brew install xcodegen stockfish`;pull → `cd App && xcodegen generate` → 在 Xcode/模拟器里跑起来 → 把编译错误喂回给 Claude Code
- pipeline:venv + Stockfish 跑通一个局面分析(Windows 上即可)

**验收:** Mac 上 `xcodegen generate && xcodebuild build` 通过;模拟器里能摆任意 FEN 并合法走子;`pytest`、`xcodebuild test` 框架就位。
**注意:** 这是整个回路的第一次跑通——确认"Windows 写 → push → Mac 生成+编译 → 回报错"这条链顺畅,比完成功能更重要。

## M1 — 核心猜着法循环(1–2 个周末)

- GuessSession 状态机:加载一盘**手工准备**的名局(硬编码 JSON 即可,不等流水线),猜→评分→揭示→推进→总结
- 评分算法 + 棋感评分(纯函数+测试)
- 讲解先用占位文本

**验收 = 验证点①:** 儿子玩完整一局,问他"还想再来一局吗?"
**可杀死点:** 如果他觉得无聊且说不清怎么改,先停下想清楚玩法,不要往前堆功能。

## M2 — 内容流水线(1–2 个周末,与 M1 可部分并行)

- 七个 stage 全部跑通(TECH_SPEC §5)
- 选出 MVP 50 局(curation list 由你和儿子定)
- **先精做 5 局**全流程(分析→标注→校验→人审),确认讲解质量达标,再批量跑剩余 45 局
- 儿子的评审流程跑起来(`6_review.py` 的 HTML 评审页)

**验收:** 5 局通过双层质检;讲解让 1700 棋手说"有用、像人话"。
**可杀死点:** 如果调了三轮 prompt,讲解仍然空洞或胡说 → 差异化不成立,降级为"无讲解纯猜分版"重新评估要不要做。

## M3 — 每日挑战 + 分享卡(1 个周末)

- 每日 JSON 拉取 + 缓存;streak 逻辑;成绩卡生成与 ShareLink
- CDN 发布脚本(预生成 60 天每日挑战)
- 推送(本地通知即可,V1 不做远程推送)

**验收:** 连续两天真机完成每日挑战,streak 正确,分享卡发到 iMessage 里好看、无剧透。

## M4 — 付费墙 + StoreKit(1 个周末)

- 三个商品、EntitlementStore、免费/付费内容门控(PRD §7 的精确切分)
- Paywall 页面 + 三个转化触点
- 沙盒账号全流程测试(购买、恢复、试用、退订)

**验收:** 沙盒里订阅/买断/恢复购买全通;免费用户能完整玩每日挑战但碰到题库会遇到付费墙。

## M5 — TestFlight(2–4 周,日历时间)

- App Store Connect 配置、隐私标签、内购审核材料
- 邀请 10–30 人:儿子棋友、棋club、r/chess 招募
- 看数据:D1/D7、每日挑战完成率、单局完成率、哪一步流失

**验收 = 验证点②:** ≥5 个非亲友用户自发用满一周。
**可杀死点:** D7 ≈ 0 且访谈说不出爱玩的点 → 上架前先修留存,不要带病发布。

## M6 — 上架 + 发布周(1 周集中)

- App Store 素材:截图(6.7"/6.1")、预览视频(可选)、描述、关键词(ASO: chess training, guess the move, master games)
- 定价生效、小企业计划确认
- **发布周清单(获客的全部,别跳过):**
  - r/chess 发帖(做了个 X 的口吻,带 TestFlight 期间的真实反馈)
  - Chess.com 论坛、棋类 Discord 各发一帖
  - 给 5–10 个中小棋类 YouTuber/博主发 lifetime code
  - Product Hunt(可选)
- 提审被拒预案:预留一周来回时间,常见雷区是内购说明和试用条款文案

**验收:** 上架 + 发布周动作全部执行完(执行完,不是"打算执行")。

## 上线后节奏(维持期,每月 ~1 个周末)

- 每月一个新题包(流水线已自动化,主要成本是儿子审核)
- 每日挑战滚动预生成
- 看三个数:下载、D7、转化率;只迭代数据指向的问题
- 6 个月 MRR < $100 且无增长迹象 → 体面归档:留着 app 在架上(年费 $99 当爱好税),停止投入

---

## 你(人类)不可委托的事

文档之外提醒一句,以下事项 Claude Code 替不了你:

1. Apple Developer 账号注册、银行/税务信息(IRS W-9)、小企业计划申请
2. App Store Connect 的最终提交按钮和审核沟通
3. 50 局名局的最终选择品味、讲解的最终质量判断(和儿子一起)
4. 社区发帖(用真人身份,r/chess 对营销帖敏感,语气要像棋友不像广告)
5. 决定每个"可杀死点"杀不杀
