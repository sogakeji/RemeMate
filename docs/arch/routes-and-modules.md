# 路由与模块结构

> 记录日期：2026-06-22
> 状态：P1 基线，实现时按此划分

---

## 目录布局

```
rememate/
├── app/
│   ├── __init__.py              # create_app() 工厂函数，注册蓝图
│   ├── extensions.py            # db, login_manager, socketio 等扩展实例
│   ├── models/
│   │   ├── user.py              # User, UserSettings
│   │   ├── word.py              # WordList, Word, Definition, ReviewLog
│   │   ├── output.py            # PracticeAttempt（原 output_entries）
│   │   ├── intake.py            # IntakeSource, SourceSegment, WordCandidate
│   │   ├── session_pad.py       # LanguagePartner, SessionRoom, SessionParticipant, SessionEntry
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
│   │   │   └── routes.py        # /import /extract /quick-add /candidates
│   │   ├── session_pad/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py        # /sessions /sessions/<id>
│   │   │   └── socket_events.py # Socket.IO 事件处理
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
│   │   ├── session_pad/
│   │   ├── square/
│   │   └── tutor/
│   │
│   └── static/
│       ├── css/
│       └── js/
│           └── socket_client.js  # 仅 session_pad 页面引入
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
| `session_pad` | `/sessions` | Session Pad 页面 + Socket.IO 事件 |
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
GET  /words/<list_id>           词表详情
GET  /review                    SRS 复习页（三按钮）
POST /review/<word_id>/grade    提交复习评分（HTMX）
GET  /write                     造句日记页
POST /write/<word_id>/submit    提交造句，触发 AI 批改（SSE 流式）
POST /write/<entry_id>/publish  公开到句子广场（HTMX）
```

### intake
```
GET  /intake/import             CSV 上传页
POST /intake/import             上传并创建 intake_source
GET  /intake/extract            文本抽词页
POST /intake/extract            提交文本，创建 intake_source + 后台处理
GET  /intake/quick-add          快速加词页
POST /intake/quick-add          提交词条，AI 补全后入候选或直接入库
GET  /intake/<source_id>/candidates   候选词审核页
POST /intake/candidates/<id>/accept   接受候选词（HTMX）
POST /intake/candidates/<id>/ignore   忽略候选词（HTMX）
POST /intake/candidates/bulk-accept   批量接受（HTMX）
POST /intake/<source_id>/commit       commit 已接受候选词 → words
```

### session_pad
```
GET  /sessions                  我的会话列表 + 语言伙伴列表
GET  /sessions/new              创建会话页
POST /sessions                  创建会话，返回 room_token
GET  /sessions/<room_token>     会话页（Socket.IO 页面）
POST /sessions/<room_token>/end 结束会话，生成 intake_source，跳转 /extract
GET  /sessions/<room_token>/review  会后只读回顾页
GET  /partners/<partner_id>     语言伙伴档案页
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

**规则 3：Socket.IO 事件只在 session_pad/socket_events.py**
其他蓝图不引入 socketio。socket_events.py 只处理实时广播，持久化通过调用 services/ 完成。

**规则 4：dispatch/ 与 app/ 共享 models，不共享 blueprints**
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
    socketio.init_app(app, async_mode="gevent")

    # RLS 钩子
    from app.services.rls import set_rls_user, reset_rls_user
    app.before_request(set_rls_user)
    app.teardown_request(reset_rls_user)

    # 蓝图注册
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.words import bp as words_bp
    from app.blueprints.intake import bp as intake_bp
    from app.blueprints.session_pad import bp as session_pad_bp
    from app.blueprints.square import bp as square_bp
    from app.blueprints.tutor import bp as tutor_bp

    for bp in [auth_bp, main_bp, words_bp, intake_bp,
               session_pad_bp, square_bp, tutor_bp]:
        app.register_blueprint(bp)

    # CLI 命令
    from cli.commands import register_commands
    register_commands(app)

    return app
```
