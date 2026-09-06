# D02：私有闭测学习闭环观察面板

> 状态：用户已确认 Practice、独立 admin 页与 UTC 滚动窗口口径；允许实现，不授权 merge、push 或部署。
> 基准：`bf256d4`（D01 已提交但尚未合并 master）；分支：`feature/d02-learning-observation`。

## 要回答的问题

只回答闭测用户是否在重复完成真实学习动作，以及现有故事、SessionPad、Practice 链路停在哪里。面板用于选择下一张产品票，不评价个人，不声称小样本有统计显著性。

## 建议口径

所有窗口为 UTC 半开区间 `[start, end)`：最近滚动 7×24 小时与紧邻的前 7×24 小时。页面并排显示两个窗口的计数，不显示环比百分比。

### 核心活跃

学习动作只取以下既有事实，按 `user_id` 去重：

- `review_logs`：`source IN ('review', 'bark')` 且 `grade IN (2, 3, 5)`；`write` 不冒充主动复习。
- `output_entries.created_at`。
- `intake_sources.created_at` 或 `completed_at`。
- `partner_recaps.created_at`、`partner_packets.created_at`、`partner_packet_thanks.thanked_at`、`partner_packet_item_adoptions.created_at`。
- 白名单 `learning_funnel_events.occurred_at`。
- D02 增补：`practice_sessions.completed_at`，仅 `status='completed'`。

每个窗口返回：学习活跃用户数、至少两个不同 UTC 日期有学习动作的重复活跃用户数、`user_id + UTC date` 去重后的活跃人日数。登录、打开页面、建号和语言切换不计。

### 基础与故事闭环

- 复习用户：上述合法 review/bark ReviewLog 的 distinct users。
- 保存输出用户：OutputEntry distinct users。
- 复习后输出：同一用户、同一非空 `word_id`，合法复习在前，OutputEntry 在后且不超过 24 小时；两条记录都必须位于同一报告窗口。显示 `qualifying users / review users`，分母为零时百分比为 `None`/`—`。
- Story：按事件白名单分别显示 eligible（normal/strong 合并）、started、ready、handoff、story-attributed saved 的 distinct users；不把 cache hit 当新生成。

### SessionPad 与 Practice

- SessionPad：创建复盘用户、发送反馈用户、感谢用户、采纳候选用户。
- Practice：完成用户；以及窗口内至少两个不同 UTC 日期完成 Practice 的重复练习用户。显示 `repeat users / completed users`；blocked/active/abandoned 不计完成。

## 接口与隐私边界

- 新增固定聚合服务 `app/services/closed_beta_observation.py`，只用 `DISPATCH_DATABASE_URL` 读取预定义聚合；不接收任意筛选、SQL、用户 ID 或搜索文本。
- 服务返回固定结构，只含窗口边界、整数计数及可空比率；不返回用户 ID、邮箱、语言、词句、故事、错误、伙伴、复盘或反馈正文。
- 建议新增独立只读页 `GET /admin/observation`，并从现有 admin 页链接。独立页便于断言响应不含任何身份或正文；普通用户 403。
- dispatch 查询失败时页面显示“统计暂不可用”，不回退 app 角色、不输出数据库 URL/异常详情。
- v1 不新增埋点、第三方 SDK、个人轨迹、排行榜、用户钻取、CSV 导出或自动推送。
- 默认不新增 migration；只有实际查询计划证明必要时才单独提出索引，不为小样本预建索引。

## 已确认测试 seam（待本计划确认后执行）

1. **聚合服务 seam**：固定多用户 fixture + 固定 `now`，验证窗口边界、distinct user、跨日重复、同词 24h 归因、零分母和 Practice 口径。
2. **Admin HTTP seam**：管理员 200、普通用户 403；页面只出现聚合结构，不出现 fixture 的邮箱、用户 ID 或任意正文 sentinel；两个窗口均可辨认。
3. **失败降级 seam**：缺失/不可用 dispatch 连接只呈现安全的 unavailable 状态，不泄露 URL、凭据或 SQL 异常。
4. **回归 seam**：D01 隔离运行器目标测试、全量 pytest 与 migration-check；桌面和 390px 页面检查。无 migration 时仍要求 single head/metadata clean。

## 实施切片

- **OB1**：先写服务 seam 的一个窗口边界失败测试，再实现固定报告结构；逐项增加核心、基础/故事、SessionPad/Practice 指标。
- **OB2**：独立 admin GET 页面、导航和中英文文案；只消费报告结构。
- **OB3**：隐私负例、dispatch 失败降级、两个尺寸浏览器检查、全量与文档收口。

## 实施与验证结果

- 已新增固定 dispatch 聚合服务、独立 `GET /admin/observation`、管理页入口、中英文文案和小屏横向滚动表格；未新增 migration 或埋点。
- 隐私测试确认独立页面不包含 fixture 邮箱、显示名或正文 sentinel；匿名重定向、普通用户 403，dispatch 失败只显示安全的 unavailable 状态。
- `onlytest` 独立 PostgreSQL 16：D02 + admin 目标测试 14 passed；Asia/Shanghai D02 8 passed；全量 910 passed / 16 warnings；migration single-head/fresh/往返/metadata clean；`git diff --check` 通过。
- 精确页面 HTML 由 Flask 集成夹具渲染，并以 Chromium/Playwright 在 1536×900 与 390×844 实际目检。目检修正了行标题误用蓝色表头样式和未定义的 secondary 按钮样式；最终桌面无横向溢出，390px body 无横向溢出，指标表在自身容器内可横向滚动查看两个窗口。
- 尚未 merge、push、部署或读取生产数据；因此还没有可用于选择 D03/D04 的真实观察结果。

## 完成与停止条件

完成：固定 fixture 可重算；所有比率显示分子/分母且零分母无百分比；普通用户 403；响应无身份/正文；目标及全量测试、migration-check、`git diff --check` 通过。

立即停止并修正：任何跨用户明细、正文或身份出现在服务返回/页面；聚合依赖 app RLS 绕过；为了历史好看补造事件；Practice blocked 被算完成；窗口或归因无法用固定 fixture 解释。

## 需要用户确认

1. Practice 是否按上述口径纳入：完成用户 + 至少两个不同 UTC 日期完成的重复用户。
2. 是否采用独立 `/admin/observation` 页面，而不是塞进会列出最近用户邮箱的 `/admin/` 页面。
3. 是否接受 UTC 滚动 7×24 小时窗口，而非按每个用户本地自然日聚合。
