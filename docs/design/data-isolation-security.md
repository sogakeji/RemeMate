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

```sql
-- 开启 RLS
ALTER TABLE word_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE words ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE output_entries ENABLE ROW LEVEL SECURITY;

-- word_lists 直接按 user_id 隔离
CREATE POLICY user_isolation ON word_lists
    USING (user_id = current_setting('app.current_user_id')::int);

-- words 通过 word_lists 级联隔离
CREATE POLICY user_isolation ON words
    USING (list_id IN (
        SELECT id FROM word_lists
        WHERE user_id = current_setting('app.current_user_id')::int
    ));
```

Flask 每个请求注入用户 ID：

```python
@app.before_request
def set_rls_user():
    if current_user.is_authenticated:
        db.session.execute(
            text("SET LOCAL app.current_user_id = :uid"),
            {"uid": current_user.id}
        )
```

句子广场等公开内容表**不开启 RLS**（设计上就是全用户可见）。

---

## 必写的安全集成测试

每个涉及用户数据的 API endpoint 都要有跨用户访问测试：

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

---

## 公开内容的边界

以下内容设计上跨用户可见，**不属于穿透漏洞**：

| 内容 | 可见范围 |
|---|---|
| 句子广场（is_public=True 的修正句）| 全用户 |
| 句子的点夯数 | 全用户 |
| 用户展示名（display_name）| 全用户 |

用户词库、复习记录、造句日记（未公开）、对话历史 → 严格隔离。
