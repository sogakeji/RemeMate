"""脚手架冒烟：app 工厂可建、/healthz 正常、RLS 钩子在请求中不报错。"""
from app import create_app


def test_app_boots_and_healthz():
    app = create_app("testing")
    client = app.test_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
