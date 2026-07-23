# RS1 验收报告（2026-07-23）

> 范围：在 GCP Ubuntu 独立测试机上，对 `feature/review-story-v1` 补测并做 PostgreSQL 验收。
>
> 规则：只补测试与跑闸门；不开始 RS2；不调用 AI；不开发路由/UI；不 merge / push / 部署。
>
> 代码权威：`D:\home\RemeMate` 全量同步到 `/home/iamshinypig/rememate-recovery-test`。

---

## 1. 结论

| 项 | 结果 |
| --- | --- |
| 分支 | `feature/review-story-v1` |
| 实现 HEAD（验收时） | `222d7c0` feat: add review story data foundation |
| 测试提交 | `f0d90e8` 及后续复核修正 |
| migration | 两边升级到 **单一 head `f1a2b3c4d5e6`** |
| FORCE RLS | `review_story_runs`、`learning_funnel_events` 均 ENABLE+FORCE |
| RS1 定向（初验） | **58 passed**（unit 33 + integration 25） |
| RLS 回归（初验） | **19 passed** |
| 全量 `pytest -q`（初验） | **`539 passed, 16 warnings`，`FULL_RC=0`**（~29m） |
| `flask doctor --strict` | `DOCTOR_RC=1`：仅测试机 LLM/词典 WARN；DB/迁移/admin OK |
| 生产代码缺陷 | **未发现**（初验失败均来自测试夹具：RLS GUC 未注入、silent 日误断言 targets） |
| RS2 / AI / UI | **未做** |

**判定：RS1 数据地基 + 日内摘要在独立 PostgreSQL 上行为可信。**
doctor 测试机 WARN 不记为 RS1 业务失败。

### 1.1 复核修正（提交后，未再跑 29 分钟全量）

初验报告有三处 P2 过实，已只改测试/文档：

1. **目标词 2–5**：真实 eligibility 下 non-silent 至少 6 词 → `min(5, n)=5`。
   集成现拆为：生产路径 8 词 → 5 targets；以及 monkeypatch eligibility 后精确 2/3/4/5 快照路径。
   纯 2–5 选词排序仍由 **unit** 覆盖。
2. **`learning_funnel_events` 写隔离**：补 own INSERT/DELETE、跨用户 INSERT 拒绝、peer UPDATE/DELETE 0 行。
3. **RLS 异常断言**：跨用户 INSERT 改为 `ProgrammingError` 且消息含 `row-level security`。
4. **报告**：去掉尾随空格（`git diff --check`）；状态改为已提交，不再写「待提交」。

---

## 2. 新增测试覆盖

| 文件 | 覆盖 |
| --- | --- |
| `tests/unit/test_review_stories.py` | eligibility 9/10 与 5/6、负值校验、2–5 目标词与排序、哈希稳定/击穿/归一化、provider-safe 字段、DST 春拨/秋拨、跨午夜本地日窗 |
| `tests/integration/test_review_stories.py` | 本地日/跨午夜、同词最差评分、跨用户/跨语言、eligibility 边界、生产路径 5 targets、强制 eligibility 下 2–5 快照、主释义、哈希、source/空词过滤、`review_story_runs` CRUD RLS、`learning_funnel_events` 读写隔离、唯一约束、并发冲突、事件类型白名单、check 约束、索引存在 |

测试夹具注意：裸 `app_context` 必须 `_set_rls_uid`（与 `test_ui_rescope_foundation` 同模式），否则 FORCE RLS 下摘要永远 0 词。

---

## 3. 闸门命令与结果（GCP 初验）

```text
HEAD=222d7c0  BRANCH=feature/review-story-v1
flask db current/heads (rememate + rememate_test) → f1a2b3c4d5e6 (single head)
RS1 unit+integration: 58 passed
RLS regression:       19 passed
FULL pytest -q:       539 passed, 16 warnings in 1738.81s  FULL_RC=0
doctor --strict:      DOCTOR_RC=1 (LLM/dict WARN only)
```

日志：`~/rememate-recovery-logs/{rs1-targeted,rs1-rls,rs1-full,rs1-doctor,rs1-summary}.*`

复核后应再跑：RS1 定向 + RLS 回归 + `git diff --check`（无需全量，除非改生产代码）。

---

## 4. 明确边界

- 未改 `app/` 业务代码
- 未开 RS2、未接 provider、未加路由/模板
- 未 merge / push / 部署
- 测试与本报告已进入分支历史（见 `f0d90e8` 及后续 fix commit）
