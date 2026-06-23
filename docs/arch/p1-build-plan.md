# RemeMate P1 实现步骤

> 记录日期：2026-06-23
> 状态：实现路线图（动手前文档已过两轮评审，见 review-2026-06-22 / review-2026-06-23）
> 原则：先建地基（脚手架 + 鉴权 + RLS），再按依赖顺序铺功能；能跑通最小闭环就尽早邀朋友测。

---

## 0. 总览：阶段依赖图

```
阶段一 脚手架 + DB + RLS  ──┐  (串行，所有功能的地基)
阶段二 Auth + CLI 建账号  ──┤
                            ↓
阶段三 词库 + SRS 复习闭环  ──→  最小可用，可邀人测
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
   阶段四 造句+AI批改     阶段五 输入管道      阶段六 AI助教
   (依赖 words)         (依赖 words+词表入口)  (独立)
        ↓
   阶段七 句子广场 (依赖 output_entries 有数据)
        ↓
   阶段八 token额度+设置页 (AI 功能全上线后收口)
        ↓
   阶段九 dispatch 推送 + 播客 (依赖 words/用户配置)
        ↓
   阶段十 部署上线 (同机隔离)
```

阶段四/五/六相互独立，是**可并行窗口**（见文末§并行说明）。

---

## 阶段一：脚手架 + 数据库 + RLS（地基，串行）

**目标**：一个能起来的空壳 Flask app，所有表建好，RLS 三层防御到位，跨用户隔离测试能跑。

- [ ] 项目骨架：`create_app()` 工厂、`extensions.py`(db/login_manager/migrate)、`config.py`、`wsgi.py`
- [ ] 全部 models 一次建齐（按 routes-and-modules.md 的 models/ 划分）：user / word / output / intake / social / conversation
- [ ] Flask-Migrate 初始化 + 第一个建表 migration
- [ ] **手写 RLS migration**（紧跟建表 migration）：ENABLE+FORCE、每表 policy、`output_entries` 读写分离四条 policy、三角色创建与 GRANT（`rememate_owner` / `rememate` / `rememate_dispatch BYPASSRLS`）—— 见 data-isolation-security.md §RLS 落地清单
- [ ] `services/rls.py`：`set_rls_user` / `reset_rls_user`（`set_config` 注入），注册到 `before_request` / `teardown_request`
- [ ] **RLS 本层测试**（直连 DB、用 app 非 owner 角色）：deny-all 回归、fail-closed、公开句例外、连续两请求不同用户

**完成判据**：`pytest tests/integration/test_rls.py` 全绿；空 app 能 `flask run` 起来。

> ⚠ 这一步必须串行、必须先做。RLS 不是后续补丁——表和 policy 一起进 migration，否则后面每个功能都要回头补隔离。

---

## 阶段二：Auth + CLI 建账号（串行）

**目标**：能建账号、能登录、能登出，provisioning 一次建全三张表。

- [ ] User 模型字段补全（locked_until / login_attempts / timezone）
- [ ] 登录流程：CSRF、不区分用户枚举、连续失败锁定、`next` 同域校验
- [ ] `@login_required` + `login_manager.login_view`
- [ ] **CLI `create-user` 走 BYPASSRLS engine**，三表一事务（User + UserSettings 含 notify 默认值 + UserQuota 含 `quota_reset_at` 初始化）—— 见 auth-flow.md §CLI 建账号 + data-isolation-security.md §CLI 必须绕过 RLS
- [ ] 其余 CLI：reset-password / deactivate-user / reset-quota

**完成判据**：`flask create-user` 建出可登录的账号；新账号 UserSettings/UserQuota 行存在且 `quota_reset_at` 非 None。

---

## 阶段三：词库 + SRS 复习闭环（串行，最小可用里程碑）

**目标**：建词表 → 有词 → 能复习。跑通就能邀朋友测核心价值。

- [ ] `POST /words` 建词表（day-1 阻塞点，必须先有）+ 词库列表/详情/删除
- [ ] `services/srs.py`：SM-2 `grade(word, quality)`，**三按钮 → 质量分映射**（没记住=2 / 模糊=3 / 秒记=5），含 lapse 边界单测 —— 见 v0.1 §3.6
- [ ] `/review` 三按钮页 + `POST /review/<word_id>/grade`（HTMX）
- [ ] `/stats` 进度看板
- [ ] 手动加词的最小入口（先不依赖完整输入管道，能塞几个词进去测复习即可）

**完成判据**：建表→加词→复习→SM-2 间隔正确递推；`pytest tests/unit/test_srs.py` 全绿。**此处可邀人测。**

---

## 阶段四：造句 + AI 批改（依赖 words，可并行）

- [ ] `services/llm.py`：provider 抽象 + `chat()` + 熔断器（内存版）+ 25s 总超时 + NSFW fail-closed —— 见 llm-provider-failover.md
- [ ] `/write` 造句页 + `POST /write/<word_id>/submit`（SSE 流式批改）
- [ ] DeepSeek 批改返回 `{corrected, translation, feedback, is_nsfw}`
- [ ] `output_entries` 写入（含 is_public/translation/upvote_count/is_nsfw 字段）

---

## 阶段五：输入管道（依赖 words + 建表入口，可并行）

- [ ] CSV 上传：解析→建 intake_source（秒回）→ `GET /intake/<id>/process` SSE 分批归一化
- [ ] `/extract` 文本抽词（SSE，返回 context 偏移用于高亮）
- [ ] `/quick-add` 快速加词（单词同步）
- [ ] 候选词审核页 `/candidates`：逐条 accept/ignore、内联编辑、bulk-accept
- [ ] `commit_intake_source`（加载 source、同词静默去重、触发 SRS 初始化）

> CSV/extract 走 SSE 避免 nginx 超时；单批受 `MAX_TOKENS_PER_REQUEST` 约束。

---

## 阶段六：AI 助教（独立，可并行）

- [ ] `/tutor` 对话列表 + 新建 + 对话页
- [ ] `POST /tutor/<conv_id>/message`（SSE 流式）
- [ ] conversations / messages 按 user 隔离（RLS 已覆盖）

---

## 阶段七：句子广场（P1，依赖 output_entries 有数据）

- [ ] `/square` 首页 + 按语言过滤 + 卡片（修正句 + 母语翻译）
- [ ] `POST /square/<id>/upvote`（点夯，UNIQUE 防重复）/ report / learn（一起记）
- [ ] 点夯换 token：`add_bonus_from_upvote` 三重反刷（同句去重 + 每日次数封顶 + 总额封顶）
- [ ] 推荐池门槛 **P1 硬编码=1 票**（不建活跃用户聚合 job）
- [ ] 举报累计自动隐藏待审

---

## 阶段八：token 额度 + 设置页（AI 全上线后收口）

- [ ] `services/quota.py`：`check_and_reserve`（单请求上限 + `_get_or_create_quota` 兜底）、`record`、`_maybe_reset`（处理 None）、时区午夜重置
- [ ] 用户自带 key 加密存储（独立 DATA_ENCRYPTION_KEY，Fernet）
- [ ] `/settings` 页：bark_url / webhook_url / deepseek_key / timezone / 四个 notify 开关 / 额度展示
- [ ] **webhook/bark URL 保存时 SSRF 校验**（`is_safe_push_url`）
- [ ] quota P1 必测清单（新用户/重置/时区/单请求上限/反刷）

---

## 阶段九：dispatch 推送 + 播客（依赖 words + 用户配置）

- [ ] `dispatch/runner.py`：BYPASSRLS engine、活跃用户过滤、单用户异常不中断
- [ ] 四类通知 + 两通道（bark_url / webhook_url），**发送前二次 SSRF 校验** + 禁重定向
- [ ] 复习提醒（幂等键用当天日期，逾期每日重提醒）
- [ ] 每日摘要（summary timer 每 15 min，命中本地 08:00 窗口，半小时偏移时区也覆盖）
- [ ] 导入完成即时推（commit 路由直接调用）
- [ ] 播客 TTS（edge-tts，音频 `/srv/rememate/audio/`，podcast_token 留 rotate 接口）
- [ ] PushLog 幂等表 + 7 天清理
- [ ] dispatch P1 必测清单（时区窗口 / SSRF 拒绝 / 幂等键）

---

## 阶段十：部署上线（同机隔离）

- [ ] MemoBuddy 云机上：rememate 用户、`/srv/rememate/`、独立 venv
- [ ] nginx 独立 server block（rememate.com → 127.0.0.1:8891），SSE 端点 `proxy_buffering off` + 加长超时
- [ ] `gunicorn -k gevent -w 2`，验证 monkey-patch 与 psycopg2/requests/edge-tts 兼容性
- [ ] Postgres 独立 DB + 三角色，连接池预算（app/dispatch/MemoBuddy < max_connections）
- [ ] systemd：service + bark.timer + summary.timer + podcast.timer + backup.timer（flock 防重叠）
- [ ] 独立 env（SECRET_KEY / DATA_ENCRYPTION_KEY / 三套 DATABASE_URL）、独立日志、独立备份
- [ ] certbot 证书

---

## 估时（solo，含返工/debug）

| 阶段 | 纯开发 | 关键风险 |
|---|---|---|
| 一 脚手架+RLS | 3-4 天 | RLS migration 最易踩坑，慢即是快 |
| 二 Auth+CLI | 2 天 | BYPASSRLS 连接配置 |
| 三 词库+SRS | 4 天 | SM-2 映射测试 |
| 四 造句+AI | 3 天 | gevent + SSE 兼容 |
| 五 输入管道 | 5 天 | 候选审核交互最重 |
| 六 AI助教 | 3 天 | |
| 七 句子广场 | 3 天 | 反刷逻辑 |
| 八 额度+设置 | 2 天 | SSRF 校验 |
| 九 dispatch | 3 天 | 时区窗口 |
| 十 部署 | 2 天 | monkey-patch 验证 |
| 测试+联调 | 5 天 | RLS 本层 + 跨用户隔离 |

合计约 **35-37 天纯开发**；solo 实际节奏 **8-10 周**（有本职工作干扰则 ~3 个月）。

---

## 并行说明（若用多 agent）

**可并行窗口**：阶段一、二、三必须串行完成（产出可运行的 models + RLS + auth + 词库地基）。之后阶段四（造句）、五（输入管道）、六（AI助教）相互独立，可分三个 agent 并行。

**并行硬约束**：
- 各 agent 只在自己的 blueprint + service 内工作，不动 models/ 和 rls.py（地基冻结）
- 共享的 `services/llm.py`（阶段四先建）作为接口给五/六复用，签名先定死
- 阶段七（广场）必须等阶段四产出 output_entries 数据后再做，不并入并行窗口
- 合并时统一过一遍跨用户隔离测试
