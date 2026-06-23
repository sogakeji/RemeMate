# 路由与模块结构

> 记录日期：2026-06-22
> 状态：P1 基线，实现时按此划分
> 注：Session Pad 为 P2 功能，本文档不包含 /sessions 路由和 Socket.IO 相关结构

---

## 目录布局

```
rememate/
├── app/
│   ├── __init__.py              # create_app() 工厂函数，注册蓝图
│   ├── extensions.py            # db, login_manager, migrate 等扩展实例
│   ├── models/
│   │   ├── user.py              # User, UserSettings, UserQuota
│   │   ├── word.py              # WordList, Word, Definition, ReviewLog
│   │   ├── output.py            # OutputEntry（造句记录，表名 output_entries）
│   │   ├── intake.py            # IntakeSource, SourceSegment, WordCandidate
│   │   ├── social.py            # SentenceUpvote
│   │   └── conversation.py      # Conversation, Message
│   │
│   ├── blueprints/
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   └── routes.py        # /login /logout
│   │   ├── main/
│   │   │   ├── __init__.py
│   │   │   └── routes.py        # / /stats /settings
│   │   ├── words/
│   │   │   ├── __init__.py
│   │   │   └── routes.py        # /words /review /write
│   │   ├── intake/
│   │   │   ├── __init__.py
│   │   │   └── routes.py        # /intake/import /extract /quick-add /candidates
│   │   ├── square/
│   │   │   ├── __init__.py
│   │   │   └── routes.py        # /square /square/<id>/upvote
│   │   └── tutor/
│   │       ├── __init__.py
│   │       └── routes.py        # /tutor /tutor/<conv_id>
│   │
│   ├── services/
│   │   ├── llm.py               # 唯一 AI 入口：chat()，provider 抽象 + 熔断
│   │   ├── srs.py               # SM-2 调度：next_review(), grade()
│   │   ├── cleaning.py          # DeepSeek 归一化，词条结构化
│   │   ├── extraction.py        # 候选词生成，AI enrichment
│   │   ├── bark.py              # Bark 推送
│   │   ├── podcast.py           # edge-tts 生成，音频文件管理
│   │   ├── quota.py             # token 额度计数、重置、检查
│   │   └── rls.py               # before_request / teardown_request RLS 钩子
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   ├── main/
│   │   ├── words/
│   │   ├── intake/
│   │   ├── square/
│   │   └── tutor/
│   │
│   └── static/
│       ├── css/
│       └── js/                  # P1 无 WebSocket，无 socket_client.js
│
├── dispatch/
│   ├── runner.py                # 遍历活跃用户，调度 bark + podcast
│   └── jobs/
│       ├── bark_job.py
│       └── podcast_job.py
│
├── cli/
│   └── commands.py              # flask create-user, flask reset-quota 等
│
├── migrations/                  # Flask-Migrate / Alembic 自动生成
├── tests/
│   ├── conftest.py              # pytest fixtures，测试用 DB
│   ├── unit/                    # 纯函数：srs, cleaning, quota
│   └── integration/             # 跨用户隔离测试，API endpoint 测试
│
├── instance/
│   └── config.py                # 本地覆盖配置（不入 git）
├── .env                         # 环境变量（不入 git）
├── config.py                    # 基础配置类
├── wsgi.py                      # gunicorn 入口：from app import create_app; app = create_app()
└── requirements.txt
```

---

## 蓝图划分

| 蓝图 | URL 前缀 | 说明 |
|---|---|---|
| `auth` | `/` | 登录、登出，无前缀 |
| `main` | `/` | 首页、stats、settings |
| `words` | `/words` | 词库管理、SRS 复习、/write 造句 |
| `intake` | `/intake` | 导入、/extract、/quick-add、候选审核 |
| `square` | `/square` | 句子广场、点夯 |
| `tutor` | `/tutor` | AI 助教对话 |

---

## 关键路由清单

### auth
```
GET  /login                     登录页
POST /login                     登录处理
GET  /logout                    登出
```

### main
```
GET  /                          首页（SRS 待复习数、今日统计）
GET  /stats                     学习进度看板
GET  /settings                  用户设置页（bark key、deepseek key、timezone）
POST /settings                  保存设置
```

### words
```
GET  /words                     词库列表
POST /words                     新建词表（name + language_code）← 新用户首个入口
GET  /words/<list_id>           词表详情
POST /words/<list_id>/delete    删除词表（HTMX，二次确认）
GET  /review                    SRS 复习页（三按钮）
POST /review/<word_id>/grade    提交复习评分（HTMX，三按钮→SM-2 质量分见 v0.1 §SRS 三按钮映射）
GET  /write                     造句日记页
POST /write/<word_id>/submit    提交造句，触发 AI 批改（SSE 流式）
POST /write/<entry_id>/publish  公开到句子广场（HTMX）
```

> **建表入口是 day-1 阻塞点（review C1）**：`IntakeSource.word_list_id` 非空，CSV/extract/quick-add 都要求先有词表。新用户零词表 → 必须先能 `POST /words` 建表，否则整条入库链卡死。建议入库页在用户无词表时内联引导建表，或注册时默认建一个「我的词库」。

### intake
```
GET  /intake/import             CSV 上传页
POST /intake/import             解析 CSV、建 intake_source，返回 source_id（不调 AI，秒回）
GET  /intake/<source_id>/process  SSE：分批调 DeepSeek 归一化，推进度（避免 nginx 超时）
GET  /intake/extract            文本抽词页
POST /intake/extract            提交文本，创建 intake_source + SSE 流式抽词
GET  /intake/quick-add          快速加词页
POST /intake/quick-add          提交词条，AI 补全后入候选或直接入库
GET  /intake/<source_id>/candidates   候选词审核页
POST /intake/candidates/<id>/accept   接受候选词（HTMX）
POST /intake/candidates/<id>/ignore   忽略候选词（HTMX）
POST /intake/candidates/bulk-accept   批量接受（HTMX）
POST /intake/<source_id>/commit       commit 已接受候选词 → words
```

### square
```
GET  /square                    句子广场首页
GET  /square?lang=fr            按语言过滤
POST /square/<entry_id>/upvote  点夯（HTMX）
POST /square/<entry_id>/report  举报（HTMX）
POST /square/<entry_id>/learn   一起记，加入自己 SRS（HTMX）
```

### tutor
```
GET  /tutor                     对话历史列表
POST /tutor                     新建对话
GET  /tutor/<conv_id>           对话页
POST /tutor/<conv_id>/message   发消息（SSE 流式）
```

---

## 模块边界规则

**规则 1：业务逻辑只在 services/ 层**
Blueprint routes 只做：取参数 → 调 service → 渲染模板 / 返回 HTMX 片段。不在 route 里直接写 SQLAlchemy 查询。

**规则 2：services/ 不导入 Blueprint**
services/ 与 HTTP 层解耦，不依赖 `request`、`session`、`g`。所有参数显式传入（见 data-isolation-security.md §第二层）。

**规则 3：dispatch/ 与 app/ 共享 models，不共享 blueprints**
dispatch runner 直接 import models 和 services，不走 HTTP 路由。使用 BYPASSRLS 连接角色（见 data-isolation-security.md）。

---

## create_app() 结构

```python
def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or "config.ProductionConfig")

    # 扩展初始化
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # RLS 钩子
    from app.services.rls import set_rls_user, reset_rls_user
    app.before_request(set_rls_user)
    app.teardown_request(reset_rls_user)

    # 蓝图注册
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.words import bp as words_bp
    from app.blueprints.intake import bp as intake_bp
    from app.blueprints.square import bp as square_bp
    from app.blueprints.tutor import bp as tutor_bp

    for bp in [auth_bp, main_bp, words_bp, intake_bp, square_bp, tutor_bp]:
        app.register_blueprint(bp)

    # CLI 命令
    from cli.commands import register_commands
    register_commands(app)

    return app
```

---

## P2 扩展预留（Session Pad）

Session Pad 上线时需新增：
- `app/models/session_pad.py` — LanguagePartner, SessionRoom, SessionParticipant, SessionEntry
- `app/blueprints/session_pad/` — routes.py + socket_events.py
- `app/templates/session_pad/`
- `app/static/js/socket_client.js`
- `extensions.py` 加入 socketio 实例
- `create_app()` 加入 `socketio.init_app(app, async_mode="gevent")`
- gunicorn 切换至 `-k gevent -w 2`（届时验证 monkey-patch 兼容性）
