# RemeMate 恢复闸门验收报告（2026-07-22）

> 范围：在独立 GCP Ubuntu 云机上验证 Windows 权威工作区 `D:\home\RemeMate` 的恢复版本。  
> 规则：只做环境搭建、测试与诊断；不开发功能、不修改业务代码；不连接生产库；不 SSH 生产；不 push / 不部署。  
> 报告日期：2026-07-22（Asia/Shanghai 当日验收窗口）

---

## 1. 结论（闸门判定）

| 问题 | 判定 |
| --- | --- |
| 是否满足「可以开始 `feature/review-story-v1`」的恢复闸门？ | **pytest 行为闸门已绿**；doctor --strict 仍因测试机无 LLM/词典 WARN 非 0 |
| 生产是否可部署六项修复？ | **否**（origin 指向生产；本轮禁止 push；doctor strict 在测试机仍有环境 WARN） |
| 六项安全/数据可信度修复是否“代码 + migration + 行为”大体可信？ | **是（在 `max_connections=100` 后）** |
| 唯一阻塞测试失败（曾出现） | 测试 SQL `AmbiguousColumn`，**已只改测试文件修复**；单测已绿；定向重跑 **122 passed** |

**实用结论：**

1. 恢复 master 的 migration head `e0f1a2b3c4d5` 可在独立 PostgreSQL 上完整 upgrade。  
2. 第一轮大面积失败是 **测试环境连接槽耗尽**，不是业务回归。  
3. 提 `max_connections` 后，全量从 `241 failed / 245 passed` 变为 **`1 failed / 485 passed`**；修测试 SQL 后该 1 条单测通过，定向 **122/122**。  
4. **Gate4 全量已 486 passed / 0 failed**（停 demo 服务 + 1.5G swap + `max_connections=100`）。  
5. `flask doctor --strict`：DB/迁移/admin **OK**；测试机无 LLM / 无词典仍 WARN → 非 0。  
6. 严格“含 doctor strict 全绿”仍差环境配置；**pytest 行为闸门已绿**。开 `feature/review-story-v1` 前建议书面接受 doctor 测试机 WARN，或补 LLM/词典后再 strict。

---

## 2. 验收对象与代码状态

### 2.1 代码来源

| 项 | 值 |
| --- | --- |
| Windows 权威工作区 | `D:\home\RemeMate` |
| Ubuntu 测试副本 | `/home/iamshinypig/rememate-recovery-test`（原生盘，非 `/mnt/d`） |
| 复制方式 | 从 Windows 完整工作区 tar 上传（含未提交 docs/wayfinder） |
| 未使用 | 生产服务器代码、origin 拉取替代版本 |

### 2.2 Git

| 项 | 值 |
| --- | --- |
| 分支 | `master`（`origin/master` **ahead 8**） |
| HEAD | `5bf4c29b9a141e6650a0932d68bf067681b14625` |
| 说明 | `5bf4c29 docs: set local master recovery gate` |
| 生产基线 | `1b72128`（云机闭测版） |

相对生产的提交：

```
5bf4c29 docs: set local master recovery gate
91fe8f7 docs: record six-fix recovery gate
e410753 fix: make review grading idempotent
b88ba88 fix: enforce normalized word uniqueness
5a27f78 fix: make manual word creation idempotent
637cd93 fix: keep accepted partner invites recoverable
994362a fix: separate public moderation from correction
26f481a fix: enforce output entry word ownership
```

### 2.3 迁移

| 库 | alembic head |
| --- | --- |
| `rememate` | `e0f1a2b3c4d5` |
| `rememate_test` | `e0f1a2b3c4d5` |

关键修复迁移：

- `d9e0f1a2b3c4`：output entry word ownership RLS  
- `e0f1a2b3c4d5`：normalized word uniqueness  

### 2.4 工作区注意

- 仅测试相关：`tests/integration/test_words.py` 修了 `SELECT word, id` → `SELECT w.word, w.id`  
- 文档侧原有未提交修改（`AGENTS.md`、`docs/*`、`docs/wayfinder/` 等）来自恢复规划，不是本轮业务改动  
- **未 push、未 reset、未部署**

---

## 3. 测试环境

### 3.1 机器

| 项 | 值 |
| --- | --- |
| 角色 | 独立 GCP 验收机（非生产） |
| 访问 | 先 `ssh gcp-test`；实例重启后 IP 为 `136.66.121.112`（`iamshinypig`） |
| OS | Debian 12 cloud，kernel `6.1.0-43-cloud-amd64` |
| 内存 | **969 MiB**，无 swap（全量时 available 常 <100–200 MiB） |
| 磁盘 | 约 9.7G；曾 95%+ 满，清理后约 0.5–1G 可用 |
| sudo | `iamshinypig` 具备 `NOPASSWD: ALL`（后期确认） |
| Python | 3.11.2 + `uv` 创建 `.venv` |

### 3.2 PostgreSQL（用户态）

| 项 | 值 |
| --- | --- |
| 版本 | **PostgreSQL 16.14**（micromamba/conda-forge） |
| 数据目录 | `/home/iamshinypig/rememate-pgdata` |
| 监听 | `127.0.0.1:55432` |
| `max_connections` | 初值 **20** → 后改 **100** |
| `shared_buffers` | 32MB（自定义段） |

### 3.3 三角色与库

| 角色 | 用途 | 属性 |
| --- | --- | --- |
| `rememate_owner` | DDL / migration | 表 owner |
| `rememate` | app 运行时 | FORCE RLS |
| `rememate_dispatch` | 后台 / 测试 bypass | **BYPASSRLS** |

| 库 | 用途 |
| --- | --- |
| `rememate` | doctor / 非清库用途 |
| `rememate_test` | pytest（conftest 会 DELETE 全表） |

### 3.4 FORCE RLS

`rememate_test` 上 **24** 张用户数据表 `relrowsecurity=t` 且 `relforcerowsecurity=t`，包括 `words`、`output_entries`、`review_logs`、`language_partners`、`partner_*`、`reading_*`、`user_settings`、`user_quota` 等。

`rememate_dispatch.rolbypassrls = true` 已核验。

### 3.5 Hermes 干扰

**根因：** 系统级 `/etc/systemd/system/hermes-gateway.service`，`Restart=always`，`User=iamshinypig`。

**处理：** stop/disable + 备份 unit + mask 为 `/dev/null`；测试窗口内 `enabled=masked`、`active=inactive`。

---

## 4. 执行时间线

| 阶段 | 内容 | 结果 |
| --- | --- | --- |
| A | 读文档；复制工作区到 Ubuntu 原生目录 | 完成 |
| B | 用户态 PG + 三角色 + venv + migration | head=`e0f1a2b3c4d5` |
| C | SSH 公钥中断；实例重启 / IP 变更 | 恢复后继续 |
| D | Hermes 反复拉起 / 内存不足 | mask 系统 unit |
| E | Gate1：`max_connections=20` | 241 failed / 245 passed（连接槽） |
| F | Gate2：`max_connections=100` | 1 failed / 485 passed |
| G | 只改测试 SQL | 单测 1 passed |
| H | Gate3：定向 122 passed；全量重跑见 §5.4 |

---

## 5. 分轮测试结果

### 5.1 Gate1（环境不可信）

| 套件 | 结果 |
| --- | --- |
| 定向 | 11 failed, 111 passed |
| 全量 | **241 failed, 245 passed**（约 10.5 min） |
| `remaining connection slots` | 全量约 **705** 次 |
| 全量 AssertionError | **0** |

根因：`max_connections=20` + 会话级 engine 占连接。**不是业务回归。**

典型错误：

```text
FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute
```

### 5.2 Gate2（提连接后，可信）

| 套件 | 结果 | 耗时 |
| --- | --- | --- |
| 定向 | **1 failed, 121 passed** | ~4.7 min |
| 全量 | **1 failed, 485 passed, 16 warnings** | ~27 min |
| 连接槽耗尽 | **0** | — |
| doctor --strict | 非 0（WARN） | — |

唯一失败：

```text
FAILED tests/integration/test_words.py::test_edit_word_rejects_normalized_duplicate_without_merging
psycopg2.errors.AmbiguousColumn: column reference "id" is ambiguous
SELECT word, id FROM words w
JOIN word_lists wl ON wl.id = w.list_id
```

分类：**测试 SQL 未写 `w.id`**，非业务/迁移失败。

### 5.3 测试修复（仅测试文件）

文件：`tests/integration/test_words.py`

```diff
- SELECT word, id FROM words w
+ SELECT w.word, w.id FROM words w
```

单测：`1 passed in 3.74s`。未改 `app/` 业务代码。

### 5.4 Gate3（修测后重确认）

| 套件 | 结果 |
| --- | --- |
| 定向 | **122 passed in 226.17s**（`TARGET_RC=0`） |
| 全量 | 曾出现 `FULL_RC=137`（进程被 SIGKILL/OOM，不可信） |

### 5.5 Gate4（停 demo 服务 + 1.5G swap + max_connections=100，资源充足全量）

前置：停 gunicorn / cloudflared / Hermes；swap 1.5G；available 内存约 500Mi 开跑。

| 套件 | 结果 |
| --- | --- |
| 全量 `pytest -q` | **`486 passed, 16 warnings in 1506.72s (0:25:06)`**，`FULL_RC=0` |
| 连接槽耗尽 | **0** |
| AmbiguousColumn | **0** |
| doctor --strict | `DOCTOR_RC=1`（见下） |

Doctor：

```text
[OK] app/dispatch/migrate DB
[OK] migrations: e0f1a2b3c4d5
[OK] SECRET_KEY / DATA_ENCRYPTION_KEY
[OK] admin account: 1 active
[WARN] LLM correction: no provider configured
[WARN] LLM nsfw: no provider configured
[WARN] reading dictionaries: missing languages: zh, en, ja, fr
Error: doctor check failed
```

日志：`~/rememate-recovery-logs/{gate-run4,full4,doctor4,summary4}.*`

### 5.6 定向测试文件集合

```text
tests/integration/test_rls.py
tests/integration/test_write.py
tests/integration/test_square.py
tests/unit/test_moderation.py
tests/unit/test_correction.py
tests/integration/test_partners.py
tests/unit/test_partner_invites.py
tests/integration/test_words.py
tests/integration/test_review_idempotency.py
tests/integration/test_bark_reminders.py
tests/integration/test_wipe_isolation.py
tests/unit/test_llm.py
```

---

## 6. Doctor --strict

早期轮次曾无 admin。**Gate4 最终结果**：

```text
[OK] app database: connected
[OK] dispatch database: connected
[OK] migrate database: connected
[OK] migrations: e0f1a2b3c4d5
[OK] SECRET_KEY: configured
[OK] DATA_ENCRYPTION_KEY: configured
[OK] admin account: 1 active
[WARN] LLM correction: no provider configured
[WARN] LLM nsfw: no provider configured
[WARN] reading dictionaries: missing languages: zh, en, ja, fr
Error: doctor check failed
```

核心 DB/迁移/admin **OK**；WARN 仅剩测试机无 LLM / 无词典。`--strict` 因此非 0。**不替代生产 doctor。**

---

## 7. 六项修复专项对照

| # | 修复 | 提交 | 迁移/机制 | 本轮验证 |
| --- | --- | --- | --- | --- |
| 1 | OutputEntry word ownership | `26f481a` | `d9e0f1a2b3c4` | 迁移已上；write/rls 路径 Gate2 后可信 |
| 2 | NSFW 与 correction 分离 | `994362a` | nsfw provider 链 | Gate3 定向全绿 |
| 3 | 伙伴确认可恢复 | `637cd93` | 服务/路由 | Gate3 定向 partners 全绿 |
| 4 | 手动加词幂等 | `5a27f78` | 服务层 | Gate2 后仅测试 SQL 1 红，修后单测绿 |
| 5 | 归一化词唯一 | `b88ba88` | `e0f1a2b3c4d5` | 迁移已上；修 SQL 后集成断言 passed |
| 6 | Web/Bark 复习幂等 | `e410753` | review attempt 幂等 | Gate2 全量 FAILED 列表不再含相关用例 |

FORCE RLS：24 张用户数据表已确认。

---

## 8. 失败项根因分类总表

| 现象 | 分类 | 业务缺陷？ | 处理 |
| --- | --- | --- | --- |
| `remaining connection slots...SUPERUSER` 成片失败 | 环境：`max_connections=20` | 否 | 提到 100 + 清连接 |
| Gate1 大面积失败且 0 AssertionError | 同上 | 否 | 同上 |
| `AmbiguousColumn: id` | 测试 SQL | 否（测试） | `w.word, w.id` |
| doctor --strict 非 0 | 无 LLM/词典（Gate4 时 admin 已 OK） | 否（配置） | 补配置或接受测试机 WARN |
| Hermes 反复复活 | system unit Restart=always | 否 | mask 系统 unit |
| SSH/实例中断 | 运维 | 否 | 换 IP 后恢复 |

---

## 9. 日志与产物（仅 GCP）

```text
/home/iamshinypig/rememate-recovery-test/
/home/iamshinypig/rememate-pgdata/
/home/iamshinypig/mamba/envs/rememate-pg/
/home/iamshinypig/rememate-recovery-logs/
  gate-run.log / targeted.txt / full.txt / doctor.txt / summary.txt
  gate-run2.log / targeted2.txt / full2.txt / doctor2.txt / summary2.txt
  gate-run3.log / targeted3.txt / full3.txt / doctor3.txt / summary3.txt
  gate-run4.log / full4.txt / doctor4.txt / summary4.txt
  fix-ambiguous.txt
```

未把 `.venv`、测试库、`.env`、PG 数据写回 Windows。

---

## 10. 测试期间修改了什么

### Windows 权威工作区

| 路径 | 变更 | 业务代码？ |
| --- | --- | --- |
| `tests/integration/test_words.py` | `w.word, w.id` | 否（测试） |
| `app/` | 未改 | — |
| 既有 docs 未提交 | 恢复规划文档 | 文档 |

### GCP

- 代码副本、venv、`.env`、用户态 PG、`max_connections=100`
- Hermes system unit 临时 mask
- 闸门脚本与日志

### 明确未做

- 未连生产库；未 SSH 生产部署；未 `git push`；未 `git reset` 权威历史

---

## 11. 与 HANDOFF 恢复闸门对照

| 要求 | 状态 |
| --- | --- |
| 独立 `rememate_test` | 通过 |
| migration → `e0f1a2b3c4d5` | 通过 |
| 定向集成 | Gate3：**122 passed** |
| 全量 `pytest -q` | **Gate4：486 passed / 0 failed** |
| `flask doctor --strict` | DB/迁移/admin OK；LLM/词典 WARN → 非 0 |
| 可开 `feature/review-story-v1` | **pytest 闸门已绿**；doctor strict 需接受测试机 WARN 或补配置 |

---

## 12. 建议后续

1. **Gate4 已确认**：`summary4.txt` → `FULL_RC=0`（486 passed）；`DOCTOR_RC=1` 仅 LLM/词典 WARN
2. 可选：挂词典目录 / 配测试 LLM key，再跑 `flask doctor --strict` 冲 0
3. 真机测时再起 gunicorn + 隧道（§16）；测完关掉腾内存
4. 授权后可将 **仅** `tests/integration/test_words.py` 作为独立小提交；六项修复仍禁止 push 生产 origin，直到明确部署

### 环境经验

1. 1GB 机跑全量：停 Hermes、提高 max_connections、禁止并行  
2. 过低 max_connections 会制造海量假失败  
3. Hermes 可能是 **system** unit，必须 mask/stop 系统级服务  
4. RLS 下多表 join 的测试 SQL 必须表别名限定列  

---

## 13. 一页纸摘要

```text
日期: 2026-07-22
代码: master @ 5bf4c29 (ahead of production 1b72128 by 8)
迁移: e0f1a2b3c4d5 on rememate + rememate_test
PG:   16.14 user-space, max_connections 20→100
Hermes: masked during tests

Gate1 (max_conn=20):  241 failed / 245 passed   <- 连接槽假失败
Gate2 (max_conn=100):   1 failed / 485 passed   <- 仅测试 SQL 歧义
Fix test SQL only:      1 passed (single)
Gate3 targeted:       122 passed
Gate4 full:           486 passed / 0 failed (25m, swap+no demo services)
Doctor --strict:      DB/migration/admin OK; WARN LLM/dict -> non-zero

业务代码修改: 无
测试代码修改: tests/integration/test_words.py (w.word, w.id)
生产/push/部署: 无

闸门: pytest 行为全绿；doctor strict 仅剩测试机 LLM/词典 WARN
feature/review-story-v1: pytest 已可放行；doctor 需接受 WARN 或补配置
```

---

*本报告由 2026-07-22 GCP Ubuntu 恢复验收过程整理，供后续 agent 与部署决策使用。*


---

## 16. 真机公网访问问题与推荐做法（2026-07-22 补充）

### 现象

- 云机上 RemeMate 已用 gunicorn 监听 `0.0.0.0:8891`，本机 `http://127.0.0.1:8891/login` → **HTTP 200**。
- 从外网访问 `http://<公网IP>:8891` → **TCP 超时**。
- 云机访问自己的公网 IP:8891 也超时（GCP 常见不 hairpin + 防火墙未真正放行）。
- 主机 `iptables INPUT` 为 ACCEPT，**不是 OS 防火墙拦截**。
- 仅 **TCP 22** 从外网可达；8891/80/443 等均不可达。
- 在 Console「已放行 8891」后仍不通：多半是规则 **Targets/network tag/VPC/优先级/组织策略** 未真正命中该实例。
- 云机默认 compute SA **无** `compute.firewalls` 等 scope，agent 无法用 gcloud 改防火墙。

### 根因分类

**GCP VPC/防火墙路径问题**，不是 Flask/gunicorn 业务故障。

### 下次真机测前推荐流程（默认用隧道）

1. **停 Hermes**（腾内存）：mask/stop 系统级 `hermes-gateway.service`（`Restart=always`，只 pkill 不够）。
2. **确保 PG 与迁移**：用户态 PG 监听 `127.0.0.1:55432`，`max_connections>=100`，`flask db upgrade` 到 head。
3. **启动 app**（单 worker）：
   ```bash
   cd ~/rememate-recovery-test && source .venv/bin/activate && set -a && source .env && set +a
   export DATABASE_URL=postgresql://rememate:dev_app_pw@127.0.0.1:55432/rememate
   export MIGRATE_DATABASE_URL=postgresql://rememate_owner:dev_owner_pw@127.0.0.1:55432/rememate
   export DISPATCH_DATABASE_URL=postgresql://rememate_dispatch:dev_dispatch_pw@127.0.0.1:55432/rememate
   gunicorn -w 1 -b 0.0.0.0:8891 wsgi:app --timeout 120      --access-logfile /tmp/rememate-access.log --error-logfile /tmp/rememate-error.log      --pid /tmp/rememate-gunicorn.pid --daemon
   ```
4. **公网访问优先用 Cloudflare quick tunnel**（不依赖 GCP 防火墙 8891）：
   ```bash
   # 二进制可放在 ~/.local/bin/cloudflared
   cloudflared tunnel --url http://127.0.0.1:8891 --no-autoupdate
   # 日志中的 https://xxxx.trycloudflare.com 即为真机入口
   ```
5. 本机浏览器备选：`ssh -L 8891:127.0.0.1:8891 iamshinypig@<公网IP>` 后打开 `http://127.0.0.1:8891`。
6. 测完：停 cloudflared、gunicorn；按需恢复 Hermes。

### 测试账号（仅验收库，非生产）

| 邮箱 | 密码 | 角色 |
| --- | --- | --- |
| `demo@rememate.test` | `Demo1234!` | admin |
| `friend@rememate.test` | `Friend1234!` | user |

### 若坚持直连公网 IP:8891

在 GCP Console 核对：Ingress Allow、tcp:8891、正确 VPC、Targets=全部实例或实例 network tag 一致、源 IP、无组织级拒绝规则。直连成功前，**真机默认仍走 Cloudflare 隧道**。

### 资源注意

- 机器约 1GB RAM；真机 demo 时建议停 Hermes，并保留 **1.5G swap**（`/swapfile`）。
- 磁盘紧张时 cloudflared 约 36MB；全量 pytest 前应停 gunicorn + cloudflared 腾内存。

