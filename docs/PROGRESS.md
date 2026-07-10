# RemeMate Progress Log

> 历史过程从 `HANDOFF.md` 移出到这里；完整旧交接原文保存在
> `docs/archive/HANDOFF.full-2026-07-08.md`。

## 里程碑

### 2026-06-28：Backlog 七项收口
- 本地化 htmx，修复 stats 时区、words N+1、lapse 冷却体验等基础问题。
- 迁移脚本可重入，补齐多项 RLS / migration 经验。

### 2026-06-29 ~ 2026-06-30：UI 职责纠偏
- 明确 UI 不是单纯换皮，先做页面职责收口。
- 词表概念转为隐式：用户只感知语言，不管理词表。

### 2026-07-03：句子广场 MVP 与闭测准备
- 做过句子广场、三行日记、管理员建号、设置页等闭测能力。
- 后续判断：广场不是闭测第一优先级，保留思路但主线先聚焦词库/复习/造句/阅读收词。

### 2026-07-04 ~ 2026-07-07：Lute-style 阅读收词分支
- 增加 PDF 阅读、查词弹卡、阅读候选词、CJK 选词修复、拼音/假名标注。
- 产品定位从“专业阅读器”收敛为“词库下的阅读收词”。
- 候选词系统与每日任务卡 v1 完成。

### 2026-07-08：合并与闭测部署基线
- `lute-reading-mvp-design` 合并进 `master`。
- 清理分支，仅保留 `master`。
- 部署到云机 `/srv/rememate`，数据库迁移到 `2e79a6ececcc`。
- 线上 `flask doctor --strict` 全 OK，阅读词典数据部署到 `/srv/rememate-data/dictionaries`。

### 2026-07-10：Bark 回流与 SessionPad B1
- Bark 补齐到期词提醒，以及签名链接打开单词三按钮并回流 SRS 熟练度。
- SessionPad 开始特色验证，第一切片只实现私有语言伙伴档案的创建、列表、详情与编辑。
- `language_partners` 启用 FORCE RLS；账号绑定、复盘信纸、反馈包和 AI 均留在后续切片。

### 2026-07-10：SessionPad B2 复盘信纸
- 围绕一位语言伙伴创建带日期和可选标题的私有复盘信纸。
- 两栏保存结构化条目：`帮自己记` / `帮他记`，支持新增、修改和删除。
- 私人伙伴笔记只能进入帮自己记，错误修正只能进入帮他记；尚无发送或共享行为。
- `partner_recaps` 与 `partner_recap_items` 启用 FORCE RLS 和复合所有权外键。

## 当前 Git

- 分支：`sessionpad-recaps-v1`
- 部署基线：54d8afc（当前 HEAD 以 git log -1 --oneline 为准）
- 代码规模：约 17,796 行（Python/HTML/CSS/JS/SQL）
- 最近全量验证：`pytest -q` -> 362 passed, 16 warnings

## 过程归档

- 完整旧 HANDOFF：`docs/archive/HANDOFF.full-2026-07-08.md`
- 当前交接入口：`docs/HANDOFF.md`
- 统一待办池：`docs/BACKLOG.md`
- 每日任务卡：`docs/daily-task-card.md`
