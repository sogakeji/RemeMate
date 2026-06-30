"""ui-rescope step4d-切片A：词列表页隐式化（UI 不暴露建表/删表/加词表单）。

router/service 兼容层保留（POST /words 建表、POST /words/<id>/delete 删表仍在，
供测试 / 切换器闭环用）；UI 不再渲染建表表单与删表按钮。
"""
import re

from sqlalchemy import text

from tests.helpers import provision_user, login

PW = "pw12345678"


def _switch(client, code):
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     client.get("/").get_data(as_text=True)).group(1)
    client.post("/language/switch", data={"language_code": code, "csrf_token": csrf})


def test_words_page_no_explicit_list_form(app, client, bypass_engine):
    """词列表页不暴露建表表单（隐式词表口径）。"""
    provision_user(app, "wl1@t.com", PW)
    login(client, "wl1@t.com", PW)
    _switch(client, "fr")
    page = client.get("/words").get_data(as_text=True)
    assert "新建词表" not in page
    assert "删除" not in page                       # 无删表按钮
    assert "name=\"name\"" not in page               # 无建表名输入框


def test_words_page_prompts_when_no_language(app, client, bypass_engine):
    """未设语言：词库页引导去设置，不显示词卡或建表。"""
    provision_user(app, "wl2@t.com", PW)
    login(client, "wl2@t.com", PW)
    page = client.get("/words").get_data(as_text=True)
    assert "先选一个正在学的语言" in page


def test_words_page_lists_current_language_words(app, client, bypass_engine):
    """设 fr 后加的 fr 词出现在 /words 列表页；en 的词不出现。"""
    uid = provision_user(app, "wl3@t.com", PW)
    login(client, "wl3@t.com", PW)
    _switch(client, "fr")
    # 加 fr 词 + en 词（经加词中心隐式建表）
    client.post("/words/add", json={"language_code": "fr", "word": "soleil",
                                   "definitions": [{"meaning": "太阳"}]},
                headers={"X-CSRFToken": _csrf_add(client)})
    client.post("/words/add", json={"language_code": "en", "word": "apple",
                                    "definitions": [{"meaning": "苹果"}]},
               headers={"X-CSRFToken": _csrf_add(client)})
    page = client.get("/words").get_data(as_text=True)
    assert "soleil" in page
    assert "apple" not in page                      # 切的是 fr，en 词不显示
    assert "法语" in page                            # 当前语言名


def test_words_detail_no_embedded_add_form(app, client, bypass_engine):
    """词表详情页不再内嵌加词表单（加词移到加词中心）。"""
    provision_user(app, "wl4@t.com", PW)
    login(client, "wl4@t.com", PW)
    client.post("/words", data={"name": "L", "language_code": "fr"})
    with bypass_engine.connect() as c:
        lid = c.execute(text("SELECT id FROM word_lists WHERE name='L'")).scalar()
    page = client.get(f"/words/{lid}").get_data(as_text=True)
    assert "加词" in page                            # 有「加词 →」导流链接
    # 但不是内嵌表单的提交按钮（form 提交到 words.detail 的 POST 加词分支）
    assert 'action="{{ url_for(\'words.detail\'' not in page


def _csrf_add(client):
    return re.search(r'name="csrf-token" content="([^"]+)"',
                     client.get("/").get_data(as_text=True)).group(1)