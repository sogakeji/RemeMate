# D01：可信测试与发布守卫

> 状态：实现与验证完成，待用户决定是否提交/合并；未 push、未部署。
> 基准：12ad2e5（修剪独立提交，产品代码基准仍为 0fc53f4）；分支：feature/d01-test-release-guards。
> 修剪提交未合并 master、未 push；D01 不混入删除提交。

## 目标

建立不依赖共享 staging/生产配置的可重建测试环境；把现有 8 个失败分类并按真实合同修正；在可信基线上接迁移守卫。不得靠删除、skip 或宽泛白名单掩盖失败。

## 已确认的测试 seams

| Seam | 可观察行为 | 验收 |
| --- | --- | --- |
| A. 测试启动与配置入口 | 独立子进程加载测试配置/启动 pytest，在连接数据库前验证 URL | 两个测试 URL 都严格解析；错库、错角色、端点不一致或不符合隔离配置均拒绝；stdout/stderr 无完整凭据；不自动加载未知 .env |
| B. 原有业务公开服务与 HTTP | 认证挑战到期、Review Story 回执、公开页面索引 | 原失败用例及最小回归 red→green；不同数据库 session 时区结果一致；不改未确认的产品规则 |
| C. 迁移/测试运行器 CLI | 单一 head、隔离 PG fresh upgrade、最后一版往返、metadata 报告 | 正确配置成功；分叉/无效迁移/真实漂移有清晰非零退出码；RLS/角色权限另由现有测试覆盖 |

每次只写一条失败测试，再最小实现；不 mock 内部 helper，不批量预写所有用例。

## 切片

### D01-A：先堵住测试误连与错误日志泄密

旧版 conftest 仅检查 app URL 是否含 rememate_test 子串，不检查 dispatch URL，拒绝信息包含原 URL；当前工作区已在 create_engine/清库之前校验两个 URL 的确切库名、角色、明确端点及连接选项，错误只报字段类别。接手者保留现有实现，不从旧版重做。

提供可单独运行、不依赖数据库的配置回归测试。不能接受 URL 查询参数覆盖已检查的库/host/role。

### D01-B：独立 PostgreSQL 运行方式

- 优先临时 PostgreSQL 16 容器，owner/app/BYPASSRLS 三角色仅在该容器创建。
- 明确项目专用容器身份与随机临时凭据，临时存储/端口仅属该次运行；不挂载现有 PG 数据目录，不绑定共享 55432。
- 本机尚未发现 docker CLI；先完成无数据库的 A。需要容器执行时只读检查新云机能力；若没有容器运行时，不擅自安装或更改系统服务，停下确认替代方案。
- 正常/失败/中断后只清理本次运行创建的资源，不清理其他容器、数据库或预览账号。
- 不重用 .env、staging 配置、云端 API key；不改共享角色密码或 venv。

### D01-C：基线失败分类

- 3 个认证过期：先在 UTC/Asia-Shanghai session 对照验证 fixture 写入与应用 naive UTC 语义；不得预判实际认证漏洞。
- 2 个 Review Story receipt：复现用户可观察失败，区分日期夹具、页面职责变化与真实行为问题。
- 3 个 SEO：区别正式内容可收录与临时 fixture noindex；各保留其配置合同，不一律改成 index。
- 如确认为应用安全/核心错误，单独最小修复并扩大回归；不借机改产品调度或 UI。

### D01-D：迁移守卫与 CI

- 单一 head（无数据库也可检查）；临时 PG fresh upgrade；最后一版 downgrade/upgrade 往返。
- metadata 差异报告后只为明确手写对象保留窄例外；不能生成 DROP 或自动修复生产 schema。
- CI 最小权限，仅 checkout、依赖、临时测试服务与检查；不配置部署凭据，不自动部署。
- 现有安全、RLS、迁移测试继续保留；全量 pytest 必须如实报告。

## 非目标与停止条件

不 push、merge、部署、生产迁移、凭据轮换、历史 migration squash、重算用户数据、依赖大升级。宿主机 Docker/系统包安装、共享云机数据库权限配置或测试 seam 改变均需另确认。创建本次专用临时容器及其内部测试角色属于已批准的 B 范围，不能扩展为修改宿主机已有集群。遇到 schema 漂移无法判定时先列证据，不创建投机性迁移。

## 完成定义

独立环境至少两次可重建运行；原 8 个失败均有分类和证据；目标测试及 pytest -q 通过；负例能让配置/迁移守卫失败；日志不含凭据；git diff --check 通过。若环境阻塞，仅交付已验证切片，不称 D01 完成。

## 进度与验证

- 修剪已按批准独立提交：12ad2e5；D01 分支从此新建，D01 工作区仍未提交。
- A：双 URL 的库名/driver/角色/回环端点/密码/query 与 PG* 覆盖均 fail closed；错误脱敏，不加载 `.env`。Python 3.12 目标环境含 dotenv 行为共 17 个配置用例通过；CLI 契约 5 个单测通过。
- B：`scripts/run_isolated_tests.py` 使用 `postgres:16`、随机角色密码/名称/label/回环端口和 512 MiB tmpfs；显式验证 database/user/superuser/BYPASSRLS/schema CREATE 合同。成功、pytest 失败和迁移检查后均按准确 ID 清理，容器与 volume 计数回零；不读取共享 55432 或宿主数据库/密钥环境。
- C：原 8 节点在隔离 UTC 环境为 5 passed / 3 SEO 旧断言失败。两条 Receipt 无产品问题；3 条认证失败根因是测试用 SQL `now()` 将 session 本地时间写入 naive UTC 列，改为绑定 `utc_now()` 后 UTC 与 Asia/Shanghai 各通过；3 条 SEO 只更新正式已发布内容的 indexable/sitemap 预期，临时 catalog noindex 与产品页 noindex 测试保留。最终原 8 节点 8 passed。
- D：单一 head `e9f0a1b2c3d4`；fresh upgrade、`d7a8b9c0d1e2` downgrade/upgrade 往返、metadata clean。分叉、无效 parent 和真实新增列漂移均安全非零。metadata 对齐补齐普通索引/FK/server defaults；窄例外仅 3 个明确手写索引。
- CI：`.github/workflows/test.yml` 使用最小 `contents: read` 权限、Python 3.12、Node 20 和同一隔离运行器；无部署或生产凭据。
- `onlytest` 最终验证：原 8 节点 8 passed；Asia/Shanghai 认证 3 passed；全量 `902 passed, 16 warnings`（318.01s）；迁移检查与最终 `git diff --check` 通过。

## 实施合同与完成记录

### 0. 恢复与未提交资产

1. 从 `.reme/handoff.md` 恢复，对比 HEAD 应为 `12ad2e58d5d00679faae982856a5e0dbcb707f38`，分支为 `feature/d01-test-release-guards`。有新变化则先比较，不覆盖。
2. 下列未提交代码是已写且验证过的 A，不是临时垃圾：
   - `tests/database_config.py`：双 URL 防误配检查，无数据库连接。
   - `tests/conftest.py`：移除隐式 dotenv，先验证配置再构造 fixture。
   - `tests/unit/test_test_database_config.py`：16 个子进程配置用例。
   - `docs/dev-setup.md`：新变量合同，旧测试初始化命令不再作日常入口。
3. D01 计划与 `.reme`/HANDOFF/BACKLOG 的交接更新也未提交。当前 master 仍是 `0fc53f4`；不得自行合并或 push。
4. 接手时先重跑无数据库命令；最终扩展为配置/CLI 22 passed。不要直接对旧 TEST_* 环境运行全量。

### 1. A 的后续验证项（不是已完成声明）

- 在 `onlytest` 的独立 Python 3.12 环境验证相同配置用例；当前本机 Python 为 3.14，不能以此替代目标运行时测试。
- 检查目标 python-dotenv 是否支持 PYTHON_DOTENV_DISABLED，并经测试确认后续 config.py 导入不会读取未知配置；当前配置用例主要覆盖收集阶段。
- 目前非空 PG* 全部拒绝，CI 中不可用 PGTZ 偷设时区；时区对照用临时 PG 配置或明确的 SQL session 设置。
- 若确需支持额外连接选项，必须以能证明不可覆盖 host/dbname/user 的白名单契约与负例取代，不能简单去掉 query 检查。
- URL 匹配不等于隔离证明：只有 B 创建并持有的实例才可执行清库 fixture。不要为了绕过校验而把共享 55432 填为显式端口。

### 2. B 的建议落地接口与执行顺序

建议新增 `scripts/run_isolated_tests.py`（CLI seam；具体内部拆分由实现决定），让本地/Linux CI/新云机使用同一入口，退出码反映测试或守卫失败。

已实现命令形态：

```text
python scripts/run_isolated_tests.py -- <pytest arguments>
python scripts/run_isolated_tests.py --migration-check
```

- 不接受任意外部数据库 URL，不继承宿主 DATABASE_URL/DISPATCH/MIGRATE/TEST_*、PG*、真实 AI/mail/push 密钥。
- 创建 postgres:16 专用容器：随机名称、明确归属 label、返回并持有准确 ID；不挂宿主数据目录，不使用现有 volume。容器内部创建 owner/app/dispatch，只有 dispatch BYPASSRLS；app 不得成为 owner/superuser。
- 两种执行布局选一种并固定：宿主已有 Python 只读运行＋容器随机回环端口，或临时 Python 测试容器共享该 PG 容器网络命名空间（仍用 loopback）。不得为了安装依赖修改共享 venv；需要新环境时用独立、可销毁的容器。
- ready 检查成功后 bootstrap rememate_test、schema ownership/default grants，再用 owner 迁移；app 与 dispatch URL 用本次随机凭据，验证 current_database/current_user/权限符合合同。
- URL/密码不写 repo、命令日志或失败报告；必要错误以阶段/退出码摘要报告。子进程输出也需脱敏，不能只脱敏自己打印的命令。
- 正常、失败及可捕获中断时 finally 只清理准确 ID；首次创建失败不能转而按通配符删容器。硬中断可能留资源，报告 label/ID 供人工确认，禁止 prune 全局资源。
- `onlytest` 上迁入的 55432 集群和 8892 服务不属于本次一次性资源，启动前后只读核对，不改动；旧机的 webdav 和 8894 未迁入。用户要求继续 D01 后已安装 Docker 29.1.3 与腾讯云镜像源，仅供一次性测试容器。

**先做一条红绿闭环：** CLI 错误参数/依赖缺失返回安全非零；随后做成功创建→目标测试→清理，以及故意失败→非零→仅清理自身。不要先堆完整 CI 再找生命周期错误。

远端同步到 `onlytest` 时只传 `git archive HEAD` 加当前明确的 D01 新增/修改文件；HEAD archive 不包含未提交 A，必须补齐并校验文件哈希。不要 tar 整个工作区，避免带入 .env、工具日志、私有导出。使用全新目录，不覆盖迁入的 `/home/ubuntu/rememate-test`。

### 3. C 的精确反馈循环

已知失败节点（来自此前新云机同环境基线对照，不保证新隔离环境仍同样失败）：

```text
tests/integration/test_account_access.py::test_expired_and_missing_challenges_use_one_invalid_error_without_mutation
tests/integration/test_password_reset_routes.py::test_invalid_expired_and_consumed_reset_tokens_are_uniform
tests/integration/test_registration_activation_routes.py::test_registration_verify_invalid_expired_and_logged_in_are_safe
tests/integration/test_review_story_receipt.py::test_last_grade_response_adds_receipt_without_generating
tests/integration/test_review_story_receipt.py::test_story_is_available_after_threshold_with_due_words_remaining
tests/integration/test_public_content_routes.py::test_public_placeholder_pages_are_previewable_and_not_indexed
tests/unit/test_public_content.py::test_repo_placeholders_load
tests/unit/test_public_content.py::test_public_routes_render_placeholders
```

先跑这八条并保存脱敏结果，再按类别逐个处理：

- 时间：比较 SQL now() 写 naive 列与 Python utc_now 的值；同一用例在 UTC 和 Asia/Shanghai session 下重跑。若是 fixture 错误，修 fixture 并验证真实过期拒绝，不改业务规则来迎合错误时间。
- Receipt：读取实际首页/词卡回执契约与生成条件。失败可能是时间条件也可能是实现错误，先记录实际行为再改。
- SEO：Git 正式内容已有 indexable=true；调整确已过时的正式内容预期，同时保留临时 catalog indexable=false、私有产品页 noindex、sitemap 过滤等独立行为测试。
- 每条记录：症状、原因分类、最小改动、回归命令、结果。不能把没有复现的失败写成“修好了”。

### 4. D 的迁移守卫细节

1. 静态 single-head 检查不应构造 Flask app 或读取数据库配置；多 head 负例在临时 migration fixture 上构造，不污染正式 migrations。
2. 空实例 owner upgrade 到 head，检查版本与当前模型；失败即停，不能 stamp head 绕过。
3. 最后一版往返为 e9f0a1b2c3d4 → d7a8b9c0d1e2 → e9f0a1b2c3d4（若实施时 HEAD 已变，动态由 Alembic 解析，不硬编码旧值）。继续运行已有 Practice blocked 状态/RLS migration 测试，不以空库往返替代含数据场景。
4. metadata 比较复用/核对 migrations/env.py 的手写对象边界。最终窄例外为表达式/原始 SQL 管理的 `uq_users_email_lower`、`uq_words_list_normalized_word`、`ix_output_entries_writerecent`；差异报告不能含行数据、URL 或凭据。RLS 不在 autogenerate 证明范围内。
5. 先获得可解释基线，再设置真实新增漂移非零；不能为消除差异直接修改数据库或输出自动 DROP 脚本。
6. CI 配置放 `.github/workflows/`，Linux/Python 3.12，最小 read 权限；使用同一运行器，失败报告脱敏。没有部署、SSH 生产凭据、pull_request_target 等额外授权。

### 5. 交付与停止

- 目标＋全量 pytest、迁移正反例、至少两次干净实例复跑；记录实际数字，不沿用旧 871/8。
- 检查 D01-A 配置负例在整个测试环境下仍有效，测试子进程不会继承实际数据库 URL。
- 更新本计划、dev-setup、handoff、state/evidence；提交前列清代码/文档，保留用户所有额外变更。
- 若环境或迁移无法安全推进，写清已完成/未完成/需要的具体批准，停止；不要更改生产、共享凭据或现有服务来换取绿灯。
