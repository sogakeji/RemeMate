# 用户数据隔离安全设计

> 记录日期：2026-06-22
> 状态：P1 必须实现

---

## 风险背景

RemeMate 使用共享 PostgreSQL（区别于 MemoBuddy 的 per-user SQLite 文件）。数据隔离完全依赖逻辑层（user_id FK），一旦应用层代码有 bug 漏掉 WHERE 条件，用户词库可能被其他用户读到。需要三层防御确保纵深安全。

---

## 三层防御

### 第一层：数据模型强制访问路径

词的查询路径必须经过 `word_lists`：

```
words.list_id → word_lists.id → word_lists.user_id
```

任何查词的 SQL 若不 JOIN `word_lists WHERE user_id = ?` 在结构上就不完整，这是数据模型本身的约束，不依赖开发纪律。

### 第二层：Service 层 user_id 显式传参

**规则：所有触碰用户数据的 Service 方法，`user_id` 必须是显式参数，禁止从 `session` 或 `g` 里隐式取。**

```python
# ✅ 正确：user_id 显式传入
def get_words(user_id: int, list_name: str) -> list[Word]:
    return Word.query.join(WordList)\
        .filter(WordList.user_id == user_id,
                WordList.name == list_name).all()

# ❌ 禁止：隐式依赖全局上下文
def get_words(list_name: str) -> list[Word]:
    return Word.query.filter_by(list_name=list_name).all()
```

后台任务（dispatch、podcast、bark）没有请求上下文，隐式取 user 尤其危险，必须显式传入。

### 第三层：PostgreSQL Row-Level Security（数据库兜底）

应用层 bug 漏了 user_id 过滤时，数据库本身拒绝返回跨用户数据。

> **四个致命前提（任一缺失，第三层要么空转、要么把表锁死成 deny-all）**：
> 1. **ENABLE 必配 POLICY**：RLS enabled 但没建 policy = Postgres 默认 deny-all，对本人也返回 0 行。每张 ENABLE 的表都必须有 policy。
> 2. **必须 FORCE**：app 连接角色若是表 owner，Postgres 默认**不对 owner 施加 RLS**，第三层静默失效。必须 `FORCE ROW LEVEL SECURITY`，且迁移 owner 角色与 app 连接角色分离（见下文§角色分离）。
> 3. **set_config 注入，不是 SET**：`SET` 语句不接受绑定参数，`text("SET LOCAL ... = :uid")` 的 bind 不生效（退化成字符串拼接=注入面）。必须用 `select set_config(...)`。
> 4. **current_setting 用两参形式**：GUC 未设置时单参 `current_setting('x')::int` 会**抛异常**（500）。两参 `current_setting('x', true)` 缺失返回 NULL → policy 判 false → fail-closed 返回 0 行。

#### RLS 落地清单（放进手写 migration，Alembic autogenerate 抓不到）

**Step 1 — ENABLE + FORCE 所有需隔离的用户表**

```sql
-- 每张用户数据表都要 ENABLE + FORCE（FORCE 让 owner 也受约束）
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'word_lists','words','definitions','review_logs','output_entries',
    'conversations','messages',
    'intake_sources','source_segments','word_candidates',
    'user_settings','user_quota','token_usage_log','push_log'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
  END LOOP;
END $$;
```

**Step 2 — 每张表的 policy（有 user_id 列的直接判，没有的走 JOIN 子查询）**

```sql
-- 辅助：统一读当前请求 user_id（未设置返回 NULL → 所有 policy fail-closed）
-- 直接内联 current_setting('app.current_user_id', true)::int

-- 直接含 user_id 的表
CREATE POLICY iso ON word_lists      USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON review_logs     USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON conversations   USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON intake_sources  USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON source_segments USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON word_candidates USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON user_settings   USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON user_quota      USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON token_usage_log USING (user_id = current_setting('app.current_user_id', true)::int);
CREATE POLICY iso ON push_log        USING (user_id = current_setting('app.current_user_id', true)::int);

-- words：无 user_id，经 word_lists 级联
CREATE POLICY iso ON words USING (
    list_id IN (SELECT id FROM word_lists
                WHERE user_id = current_setting('app.current_user_id', true)::int));

-- definitions：无 user_id，经 words → word_lists 两级级联
CREATE POLICY iso ON definitions USING (
    word_id IN (SELECT w.id FROM words w JOIN word_lists wl ON w.list_id = wl.id
                WHERE wl.user_id = current_setting('app.current_user_id', true)::int));

-- messages：无 user_id，经 conversations 级联
CREATE POLICY iso ON messages USING (
    conv_id IN (SELECT id FROM conversations
                WHERE user_id = current_setting('app.current_user_id', true)::int));

-- output_entries：既存私人草稿又存广场公开句 → 本人可读 OR 已公开可读
CREATE POLICY iso ON output_entries USING (
    user_id = current_setting('app.current_user_id', true)::int
    OR is_public = true);
```

> **output_entries 的公开例外**：造句表同时承载私人草稿和句子广场公开句。policy 必须带 `OR is_public = true`，否则广场读不到别人公开的句子。**写入**仍受限本人——RLS 默认 USING 同时作用于读写；如需允许任何人对公开句点夯/举报，点夯写在独立 `sentence_upvotes` 表（见下）。

**Step 3 — 句子广场公开聚合表的处理**

`sentence_upvotes` 是公开内容（点夯数全用户可见，任何登录用户可对任意公开句点夯一次）。两种选择：
- **不开 RLS**（最简）：点夯表无敏感数据，按公开表处理，应用层用 `UNIQUE(entry_id, user_id)` 防重复。
- 若要审计「谁夯了谁」隐私，再开 RLS。P1 选不开 RLS。

#### GUC 注入：set_config 而非 SET

```python
# services/rls.py
from sqlalchemy import text
from flask_login import current_user

def set_rls_user():
    """before_request 钩子：注入当前用户 ID 到事务级 GUC"""
    if current_user.is_authenticated:
        # set_config 第三参 is_local=true → 等价 SET LOCAL，事务级；可参数化
        db.session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(current_user.id)},   # set_config 第二参必须是 text
        )
    # 未登录请求不设 GUC → current_setting 返回 NULL → 所有 RLS policy fail-closed

def reset_rls_user(exc=None):
    """teardown_request 钩子：连接归还池前清除 GUC，防跨请求残留"""
    db.session.execute(text("SELECT set_config('app.current_user_id', '', true)"))
```

#### 一请求一事务（避免多 commit 丢 GUC）

`set_config(..., is_local=true)` 是事务级，**COMMIT 后即失效**。一个请求里若多次 commit（如 intake commit、grade 提交都 commit），第一次 COMMIT 后 GUC 清空，后续查询在「无 user_id」状态下跑 → fail-closed 读空或写入异常。

**硬规则**：
- 一个 HTTP 请求对应一个事务，请求结束统一 commit（Flask-SQLAlchemy 默认行为，不要在 service 层手动 commit）
- 确需多段 commit 的流程（如 intake 分批），每次 commit 后在同请求内**重新 `set_config`**，或显式开新事务并重设 GUC

#### 角色分离（FORCE 生效的前提）

| 角色 | 用途 | RLS |
|---|---|---|
| `rememate_owner` | 跑 migration、建表，是所有表 owner | 不连接 app |
| `rememate` | app 运行时连接（gunicorn）| 受 FORCE RLS 约束 |
| `rememate_dispatch` | 后台任务 | `BYPASSRLS`，显式 user_id 过滤兜底 |

app 角色**不是表 owner**，再叠加 FORCE，双重保证 RLS 对 app 连接始终生效。

句子广场点夯表等公开内容**不开启 RLS**（设计上就是全用户可见，见上 Step 3）。

---

## 后台任务的 RLS 例外处理

dispatch / podcast / bark 等后台任务需要**遍历所有用户**，与 RLS 的单用户隔离策略冲突。解决方案：

**两套连接角色分工**：

| 路径 | 连接角色 | 防御层 |
|---|---|---|
| HTTP 请求（用户操作） | 普通角色 + RLS | 第一层 + 第二层 + RLS 兜底 |
| 后台批处理（dispatch） | `BYPASSRLS` 角色 | 仅第一层 + 第二层（显式 user_id 过滤） |

后台任务使用 BYPASSRLS 角色时，Service 层显式 user_id 参数约束（第二层防御）是唯一兜底，必须严格执行。

```python
# dispatch 遍历模式：显式逐用户处理，绝不做跨用户批量查询
for user in get_all_active_users():
    process_bark_for_user(user_id=user.id)   # user_id 显式传入
```

---

## RLS 连接复用安全要求

`set_config(..., is_local=true)` 是事务级，COMMIT 后失效。但 SQLAlchemy 连接池跨请求复用连接时若时机不对，可能残留前一请求的 user_id 值，导致跨用户数据泄漏。

**必须执行**：
- `teardown_request` 把 GUC 清空（见上文 `reset_rls_user`，置空字符串 → `current_setting` 两参返回 NULL → fail-closed）
- 集成测试必须覆盖"连续两个请求、不同用户"场景，验证第二个请求不读到第一个用户的数据（见下 `test_consecutive_requests_different_users`）

> 注：钩子注册见 `routes-and-modules.md` 的 `create_app()`（`before_request(set_rls_user)` / `teardown_request(reset_rls_user)`）。`set_rls_user` / `reset_rls_user` 的实现见上文§GUC 注入。

---

## ★ CLI / 建账号必须绕过 RLS（否则建不了用户）

FORCE RLS 后，policy 的 `USING` 表达式在 INSERT 时也充当 `WITH CHECK`（未单独写 WITH CHECK 时 Postgres 用 USING 兜底）。CLI 命令（`create-user` 等）**没有 HTTP 请求上下文，GUC 未设置** → `current_setting('app.current_user_id', true)` 返回 NULL → 对 `user_settings` / `user_quota` 的 INSERT 的 WITH CHECK 判 false → **插入被拒，新用户建不出来**。更糟的是 create_user 要先 INSERT `users` 才有 user_id，存在先有鸡还是先有蛋。

**解法**：CLI / 后台建账号统一走 **`rememate_dispatch`（BYPASSRLS）** 连接，不走 app 的 `rememate` 角色。

```python
# cli/commands.py — CLI 用 BYPASSRLS engine，与 HTTP 请求隔离
# create-user / reset-password / deactivate-user / reset-quota 全部走这个连接
cli_engine = create_engine(os.environ["DISPATCH_DATABASE_URL"])  # BYPASSRLS 角色
```

P2 开放注册时，注册路由走的是 HTTP（app 角色 + RLS）。此时 provisioning 需在「先 INSERT users 拿到 id → `set_config` 设成该 id → 再 INSERT user_settings/user_quota」的顺序内完成，或该路由临时用 BYPASSRLS 连接建账号。P1 仅 CLI 建账号，直接 BYPASSRLS 最简。

---

## 必写的安全集成测试

### Service 层隔离测试（第二层）

```python
def test_user_cannot_access_other_user_words():
    user_a = create_user("a@test.com")
    user_b = create_user("b@test.com")
    add_word(user_a, "décollage")

    words = get_words(user_id=user_b.id, list_name="Francais")
    assert len(words) == 0

def test_api_endpoint_isolation():
    client.login(user_b)
    resp = client.get(f"/api/words?list=Francais")
    # 只能看到 user_b 自己的词，看不到 user_a 的
    assert all(w["owner"] == user_b.id for w in resp.json["words"])
```

### RLS 本层测试（第三层 — ★critical，上面的 service 测试测不到）

**关键**：service 层测试里第二层（显式 user_id 过滤）先挡住了，RLS 本层根本没被触发。必须**绕过 service、直连 DB、用 app 角色**，验证 policy 真能拦：

```python
def test_rls_blocks_raw_query_without_service_layer():
    """模拟 service 层漏写 user_id 过滤时，RLS 兜底拦截"""
    user_a = create_user("a@test.com")
    user_b = create_user("b@test.com")
    add_word(user_a, "décollage")

    # 用 app 角色连接（非 owner），设成 user_b
    with app_role_connection() as conn:
        conn.execute(text("SELECT set_config('app.current_user_id', :uid, true)"),
                     {"uid": str(user_b.id)})
        # 故意不带任何 user_id 过滤的裸查询（模拟 service 层 bug）
        rows = conn.execute(text("SELECT * FROM words")).fetchall()
        assert len(rows) == 0   # RLS 拦住，user_b 看不到 user_a 的词

def test_rls_enabled_tables_not_deny_all_for_owner():
    """回归 A1a：ENABLE 但漏建 policy 会导致本人也读空"""
    user_a = create_user("a@test.com")
    add_review_log(user_a)
    add_output_entry(user_a, is_public=False)
    with app_role_connection() as conn:
        conn.execute(text("SELECT set_config('app.current_user_id', :uid, true)"),
                     {"uid": str(user_a.id)})
        assert conn.execute(text("SELECT count(*) FROM review_logs")).scalar() > 0
        assert conn.execute(text("SELECT count(*) FROM output_entries")).scalar() > 0

def test_rls_unset_guc_fails_closed():
    """未登录/GUC 未设置 → 读空而非 500"""
    user_a = create_user("a@test.com")
    add_word(user_a, "décollage")
    with app_role_connection() as conn:
        # 不设 GUC
        rows = conn.execute(text("SELECT * FROM words")).fetchall()
        assert rows == []   # current_setting 两参返回 NULL，policy false，0 行无异常

def test_output_entries_public_visible_across_users():
    """广场公开句跨用户可见（output_entries 的 is_public 例外）"""
    user_a = create_user("a@test.com")
    user_b = create_user("b@test.com")
    add_output_entry(user_a, is_public=True)
    with app_role_connection() as conn:
        conn.execute(text("SELECT set_config('app.current_user_id', :uid, true)"),
                     {"uid": str(user_b.id)})
        rows = conn.execute(text("SELECT * FROM output_entries WHERE is_public")).fetchall()
        assert len(rows) == 1   # user_b 能读到 user_a 的公开句

def test_multi_commit_keeps_rls_user():
    """回归 A1e：一请求内多次 commit 后 GUC 仍在"""
    # 走真实请求路径，触发 intake commit + 另一次 commit，断言第二段查询不读空

def test_consecutive_requests_different_users():
    """连接池复用：连续两请求不同用户，第二个读不到第一个的数据"""
    # 已要求；验证 teardown 的 set_config('','',true) 清除生效
```

> `app_role_connection()` 必须用 `rememate`（非 owner）角色连接，否则 FORCE 缺失时测试会假绿。

---

## 公开内容的边界

以下内容设计上跨用户可见，**不属于穿透漏洞**：

| 内容 | 可见范围 |
|---|---|
| 句子广场（is_public=True 的修正句）| 全用户 |
| 句子的点夯数 | 全用户 |
| 用户展示名（display_name）| 全用户 |

用户词库、复习记录、造句日记（未公开）、对话历史 → 严格隔离。
