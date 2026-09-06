# 本地开发环境搭建（WSL）

> 记录日期：2026-06-23
> 环境：Windows + WSL2 Ubuntu 24.04，仓库位于 WSL 原生文件系统 `~/rememate`
> 已实测通过：Python 3.12.3 / PostgreSQL 16.14 / gevent 26.5 + psycopg2 monkey-patch 连库 OK

---

## 为什么在 WSL

- Python 3.12（gevent / psycopg2 都有成熟 wheel；Windows 主环境是 3.14，C 扩展易踩坑）
- Linux 原生 Postgres + systemd/nginx，和上线的 VPS 1:1，部署可在 WSL 预演
- 仓库放 WSL 原生 fs（`~/rememate`），不放 `/mnt/d`（跨 fs 慢、权限别扭）

## 一次性安装

```bash
sudo apt update && sudo apt install -y \
  python3-pip python3-venv build-essential libpq-dev \
  postgresql postgresql-contrib
```

## 数据库初始化（三角色 + 库 + 默认权限）

脚本：`scripts/dev/init-db.sql`。三角色分工见 data-isolation-security.md §角色分离：

| 角色 | 用途 | RLS |
|---|---|---|
| `rememate_owner` | 建表 / 跑 migration，表 owner | 不被 app 运行时使用 |
| `rememate` | app 运行时连接 | 受 FORCE RLS 约束（非 owner）|
| `rememate_dispatch` | 后台任务 | BYPASSRLS |

```bash
sudo service postgresql start
sudo -u postgres psql -v ON_ERROR_STOP=1 -f scripts/dev/init-db.sql
```

> dev 密码写死在 `init-db.sql` 与 `.env`，仅本机 localhost 用。生产用强密码 + 独立 env。
> `init-db.sql` 为幂等：开头 DROP 后重建，可反复跑（**会清空 rememate 库，慎用于有数据时**）。

## Python venv

```bash
cd ~/rememate
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 环境变量

`.env`（不入 git，已含 dev 值与自动生成的 SECRET_KEY / DATA_ENCRYPTION_KEY）。
样例见 `.env.example`。三套 DATABASE_URL 对应三角色：

- `DATABASE_URL` → app（`rememate`，受 RLS）
- `MIGRATE_DATABASE_URL` → owner（`rememate_owner`，跑 Alembic / RLS 手写迁移）
- `DISPATCH_DATABASE_URL` → dispatch（`rememate_dispatch`，BYPASSRLS）

## 兼容性验证（已通过，保留为回归检查）

```bash
python - <<'PY'
from gevent import monkey; monkey.patch_all()
import psycopg2
c = psycopg2.connect(host="127.0.0.1", dbname="rememate",
                     user="rememate", password="dev_app_pw")
cur = c.cursor(); cur.execute("select current_user, current_database()")
print("OK:", cur.fetchone())
PY
```

## 日常启动

```bash
sudo service postgresql start          # WSL 重启后需手动起（或配 systemd 自启）
cd ~/rememate && . .venv/bin/activate
# 迁移与启动：
# flask db upgrade                       # env.py 用 MIGRATE_DATABASE_URL(owner)
# gunicorn -c gunicorn.conf.py wsgi:app  # 含 psycogreen 补丁；勿加 --preload
```

## 闭测部署

小范围邀请朋友试用时，继续保持无公开注册，通过 CLI 建账号。部署后的最小自检和账号命令见
`docs/deploy-closed-beta.md`。

## 测试库（独立于 dev，pytest 会清空它）

日常测试统一使用可销毁 PostgreSQL 16 容器运行器；宿主机需要 Python 3.12、Docker 和 Node。运行器生成临时角色/密码、只发布随机回环端口、在 tmpfs 中建库，并在成功、失败或可捕获中断后按准确容器 ID 清理：

```bash
python scripts/run_isolated_tests.py -- -q
python scripts/run_isolated_tests.py --migration-check
```

迁移检查要求单一 Alembic head，执行 fresh upgrade、最后一版 downgrade/upgrade，并比较模型 metadata。认证过期时区回归可用：

```bash
python scripts/run_isolated_tests.py --database-timezone Asia/Shanghai -- -q \
  tests/integration/test_account_access.py \
  tests/integration/test_password_reset_routes.py \
  tests/integration/test_registration_activation_routes.py
```

不要把旧 `init-test-db.sql` 用于云机共享集群；它会 DROP 数据库，不是日常测试启动命令。

底层 pytest 入口不自动读取 `.env`；绕过运行器时必须显式传入：

- `TEST_DATABASE_HOST`：确认过的专用测试实例回环地址（127.0.0.1 / localhost / ::1）。
- `TEST_DATABASE_PORT`：该实例明确的端口；没有默认端口。
- `TEST_DATABASE_URL`：PostgreSQL / psycopg2，角色 rememate，确切库名 rememate_test。
- `TEST_DISPATCH_DATABASE_URL`：同一 host/port/database，角色 rememate_dispatch。

两个 URL 都必须显式带密码，禁止 URL query 连接覆盖项及非空 `PG*` 环境覆盖。URL 一致性检查不能证明数据库可销毁，仍须由运行器/操作者确认实例归属；不要把已共享的 55432 填进去绕过隔离准备。

只有在操作者已确认实例可销毁时，才可显式配置上述变量直接运行 pytest。迁移必须另用 owner 连接；不得用 app/dispatch 角色跑迁移。共享 55432 不属于可销毁实例。

无需数据库的入口安全测试：

```bash
python -m pytest tests/unit/test_test_database_config.py --noconftest -q
```

错误只报告无敏感值的字段类别；不要将真实 URL 用作 pytest 参数 ID 或打印到日志。

## 仍缺 / 待补

- `ffmpeg`：阶段九播客音频后处理可能需要，届时 `apt install ffmpeg`
- LLM key：填 `DEEPSEEK_API_KEY`，或填 `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL` 使用 OpenAI-compatible 网关后，AI 功能才可用。
- WSL 当前默认 root 用户；如需贴近生产可另建普通用户（非必须）
