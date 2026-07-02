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

```bash
# 首次建测试库 + 迁移：
sudo -u postgres psql -f scripts/dev/init-test-db.sql
MIGRATE_DATABASE_URL=postgresql://rememate_owner:dev_owner_pw@127.0.0.1:5432/rememate_test \
  flask db upgrade
# 跑测试（conftest 强制连 rememate_test，缺 TEST_* 直接报错）：
python -m pytest -q
```

## 仍缺 / 待补

- `ffmpeg`：阶段九播客音频后处理可能需要，届时 `apt install ffmpeg`
- LLM key：填 `DEEPSEEK_API_KEY`，或填 `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL` 使用 OpenAI-compatible 网关后，AI 功能才可用。
- WSL 当前默认 root 用户；如需贴近生产可另建普通用户（非必须）
