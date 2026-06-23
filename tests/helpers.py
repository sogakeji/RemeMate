"""测试数据构造 helper（均走 BYPASSRLS 连接）。"""
from sqlalchemy import text


def make_user(bypass_engine, email):
    with bypass_engine.begin() as c:
        return c.execute(text(
            "INSERT INTO users(email,password_hash,display_name,role,is_active,"
            "login_attempts,timezone,created_at) "
            "VALUES (:e,'x','n','user',true,0,'UTC',now()) RETURNING id"
        ), {"e": email}).scalar()


def make_word(bypass_engine, user_id, word="décollage"):
    with bypass_engine.begin() as c:
        list_id = c.execute(text(
            "INSERT INTO word_lists(user_id,name,language_code,created_at) "
            "VALUES (:u,'L','fr',now()) RETURNING id"
        ), {"u": user_id}).scalar()
        word_id = c.execute(text(
            "INSERT INTO words(list_id,word,marked,due_date,interval,ease,reps,lapses) "
            "VALUES (:l,:w,false,now(),1,2.5,0,0) RETURNING id"
        ), {"l": list_id, "w": word}).scalar()
        return list_id, word_id


def make_output_entry(bypass_engine, user_id, word_id, is_public):
    with bypass_engine.begin() as c:
        return c.execute(text(
            "INSERT INTO output_entries(word_id,user_id,corrected,is_public,"
            "upvote_count,is_nsfw,created_at) "
            "VALUES (:w,:u,'phrase',:p,0,false,now()) RETURNING id"
        ), {"w": word_id, "u": user_id, "p": is_public}).scalar()


def make_review_log(bypass_engine, user_id, word_id):
    with bypass_engine.begin() as c:
        c.execute(text(
            "INSERT INTO review_logs(word_id,user_id,ts,grade,source,interval_after) "
            "VALUES (:w,:u,now(),5,'review',1)"
        ), {"w": word_id, "u": user_id})


def set_uid(conn, uid):
    """在 app 连接上设置 RLS GUC（session 级，持续到连接关闭）。uid=None → 置空字符串。"""
    conn.execute(text("SELECT set_config('app.current_user_id', :u, false)"),
                 {"u": "" if uid is None else str(uid)})


def provision_user(app, email="u@t.com", password="pw12345678",
                   name="Tester", admin=False, tz="Asia/Shanghai"):
    """在 app 上下文里走 provisioning（BYPASSRLS）建账号，返回 user_id。"""
    from app.services.provisioning import create_user_with_defaults

    with app.app_context():
        uid, _ = create_user_with_defaults(
            email, name, admin=admin, timezone=tz, password=password
        )
    return uid


def login(client, email="u@t.com", password="pw12345678"):
    return client.post("/login", data={"email": email, "password": password})
