"""rls: ENABLE + FORCE row level security + per-table policies

手写迁移（Alembic autogenerate 抓不到 RLS）。落地清单见
docs/design/data-isolation-security.md §RLS 落地清单。

要点：
- 每张用户表 ENABLE + FORCE（FORCE 让 owner 也受约束）。
- GUC 表达式用 NULLIF(current_setting(...,true),'')::int：
  未设置(2参→NULL) 与 置空('' →NULL) 都 fail-closed，绝不抛 invalid-integer。
- output_entries 读写分离 4 条 policy（公开句可读、仅本人可写）。
- users / sentence_upvotes 不开 RLS（登录前查 users；点夯为公开内容）。
- 角色（rememate_owner/rememate/rememate_dispatch）创建见 scripts/dev/init-db.sql；
  生产由部署脚本建，密码来自 env，不写进本迁移。

Revision ID: 1ca04f710530
Revises: 0e8d5314dced
Create Date: 2026-06-23
"""
from alembic import op

revision = '1ca04f710530'
down_revision = '0e8d5314dced'
branch_labels = None
depends_on = None

# 当前请求用户 ID 表达式（fail-closed）
UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"

# 直接含 user_id 列的表
DIRECT_TABLES = [
    "word_lists", "review_logs", "conversations",
    "intake_sources", "source_segments", "word_candidates",
    "user_settings", "user_quota", "token_usage_log", "push_log",
]

# 需要 ENABLE+FORCE 的全部用户表（含级联表与 output_entries）
ALL_RLS_TABLES = DIRECT_TABLES + ["words", "definitions", "messages", "output_entries"]


def _recreate_policy(name, table, stmt):
    """CREATE POLICY 无 IF NOT EXISTS；先 DROP IF EXISTS 再 CREATE，保证可重入
    （review 2026-06-23 M7）。
    """
    op.execute(f"DROP POLICY IF EXISTS {name} ON {table};")
    op.execute(stmt)


def upgrade():
    # 1. ENABLE + FORCE（幂等：重复 ENABLE/FORCE 不报错）
    for t in ALL_RLS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")

    # 2. 直接 user_id 的 policy
    for t in DIRECT_TABLES:
        _recreate_policy("iso", t, f"CREATE POLICY iso ON {t} USING (user_id = {UID});")

    # 3. 级联 policy
    _recreate_policy("iso", "words", f"""
        CREATE POLICY iso ON words USING (
            list_id IN (SELECT id FROM word_lists WHERE user_id = {UID}));
    """)
    _recreate_policy("iso", "definitions", f"""
        CREATE POLICY iso ON definitions USING (
            word_id IN (SELECT w.id FROM words w
                        JOIN word_lists wl ON w.list_id = wl.id
                        WHERE wl.user_id = {UID}));
    """)
    _recreate_policy("iso", "messages", f"""
        CREATE POLICY iso ON messages USING (
            conv_id IN (SELECT id FROM conversations WHERE user_id = {UID}));
    """)

    # 4. output_entries：读=本人 OR 已公开；写=仅本人（读写分离，防改/删他人公开句）
    _recreate_policy("oe_sel", "output_entries", f"""
        CREATE POLICY oe_sel ON output_entries FOR SELECT
            USING (user_id = {UID} OR is_public = true);
    """)
    _recreate_policy("oe_ins", "output_entries", f"""
        CREATE POLICY oe_ins ON output_entries FOR INSERT
            WITH CHECK (user_id = {UID});
    """)
    _recreate_policy("oe_upd", "output_entries", f"""
        CREATE POLICY oe_upd ON output_entries FOR UPDATE
            USING (user_id = {UID}) WITH CHECK (user_id = {UID});
    """)
    _recreate_policy("oe_del", "output_entries", f"""
        CREATE POLICY oe_del ON output_entries FOR DELETE
            USING (user_id = {UID});
    """)


def downgrade():
    for policy, t in [
        ("oe_sel", "output_entries"), ("oe_ins", "output_entries"),
        ("oe_upd", "output_entries"), ("oe_del", "output_entries"),
        ("iso", "messages"), ("iso", "definitions"), ("iso", "words"),
    ]:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {t};")
    for t in DIRECT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS iso ON {t};")
    for t in ALL_RLS_TABLES:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;")
