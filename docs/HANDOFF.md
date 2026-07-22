# RemeMate HANDOFF

## 2026-07-22 丢盘恢复闸门

- WSL2 虚拟磁盘已丢失且不再做磁盘恢复。本地项目从闭测云机恢复到 `D:\home\RemeMate`；
  云机代码 `1b72128` 是恢复基线，线上用户数据、`.env`、`.venv` 和词典目录均未复制或覆盖。
- 本地 `master` 在生产基线之后重放了六项尚未部署的安全/数据可信度修复：
  - `26f481a`：`output_entries.word_id` 所有权 RLS，迁移 `d9e0f1a2b3c4`；
  - `994362a`：广场 NSFW 审核与批改 failover 分离，审核不可用时公开 fail-closed；
  - `637cd93`：已接受邀请但未建立反向资料时，伙伴页持续显示待确认关系；
  - `5a27f78`：同语言手动加词顺序幂等，保留首条词形、释义和 SRS 状态；
  - `b88ba88`：同词表规范化词条数据库唯一，手动并发/编辑冲突/候选批量保存点兜底，
    迁移 `e0f1a2b3c4d5`；
  - `e410753`：Web 与 Bark 对同一当前到期状态最多评分一次，重放与延迟请求不再重复推进 SRS。
- 当前本地迁移 head：`e0f1a2b3c4d5`。迁移遇到历史规范化重复词时会中止并只报告重复组数量，
  不自动合并用户数据。
- Windows 恢复环境没有 PostgreSQL，故数据库集成/全量测试尚未执行。已完成语法、JSON、迁移链、
  `git diff --check`，以及 17 个可离线运行的 SRS/批改/审核单元测试。部署前必须重建独立
  `rememate_test`，执行 migration upgrade、定向集成测试、`pytest -q` 和 `flask doctor --strict`。
- `origin` 直接指向生产工作仓库；恢复阶段禁止推送。生产仍为 `1b72128`，未收到上述六项修复。

下面的“当前状态”是 2026-07-15 云机里程碑基线，保留用于说明闭测版具备的功能，不代表六项恢复
修复已经在生产验证或部署。

> 轻量交接页。历史过程已移到 `docs/PROGRESS.md`，完整旧文档见
> `docs/archive/HANDOFF.full-2026-07-08.md`。软 bug / 延后事项统一进
> `docs/BACKLOG.md`。

## 当前状态

- 日期：2026-07-15
- 当前分支：`master`。测试基线修复与「阅读收词小优化 v1」均已提交并部署，工作树干净。
- `navigation-ia-mobile`、`i18n-foundation`、SessionPad、Bark、Landing 与词库/解释语言小修均已合入 `master`；
 现有本地分支全部已被 `master` 包含。两个附加 worktree（`backlog-vocab-language-polish`、
  `landing-public-home`）干净，但尚未清理。
- 本地数据库迁移：`c8d9e0f1a2b3 (head)`；`flask doctor --strict` 于 2026-07-15 全部 OK。
- 最近完整绿线：`457 passed, 16 warnings`（2026-07-15）；阅读收词相关定向回归
  为 `76 passed, 15 warnings`，新增 v1 回归为 `8 passed`。
- **测试基线已恢复**：原始 `314 passed, 129 failed, 11 errors` 的首个错误是
  `tests/conftest.py::_wipe` 删除 `users` 时被残留 `user_quota` 外键拦截，导致后续连锁失败。
  `_wipe` 现在仅在数据库完整性错误后以逐用户 GUC 方式重试清理，并有 3 个定向回归测试覆盖
  基础清理、双用户清理和 FK 回退路径。`rememate_dispatch` 在测试库中已核验具备 `BYPASSRLS`；
  不把问题归因于缺权限。
- **阅读收词小优化 v1 已完成并部署**：阅读器加入候选后继续停留原页，显示本篇候选词和
  轻量审核入口；候选审核与词库详情显示阅读文档名和 PDF 原句，非阅读来源不误标。删除阅读文档后
  以文件名回退；再次加入已忽略候选会恢复为待审核。来源查询保持用户隔离并以单次查询加载。
- 线上部署：`ubuntu@43.156.210.229:/srv/rememate`，服务为 `rememate.service`，gunicorn 监听
  `127.0.0.1:8891`。2026-07-15 已部署 `9ef23b8`，迁移为 `c8d9e0f1a2b3 (head)`；严格 doctor、
  服务健康检查和公网 HTTPS 首页均通过。线上工作树仅有部署前已存在的未跟踪
  `admin-initial-login.txt`。
- 线上词典：`/srv/rememate-data/dictionaries`，`zh/en/ja/fr` present。

## 闭测规则

- 闭测期间只立即修硬 bug：崩溃、数据丢失、权限/隔离、安全、无法完成核心流程。
- 软 bug、体验瑕疵、文案、排序、布局微调，先写入 `docs/BACKLOG.md`，集中分批处理。
- 新功能不要“来一个小需求做一个小需求”。先收集、归类、划切片，再开分支。
- 避免每个微需求都扩全量测试。测试策略按风险分层：
  - 文档/纯 CSS：不跑全量，说明未跑。
  - 单页面轻逻辑：跑相关 integration。
  - 服务层/权限/数据库/迁移/AI 降级：跑相关测试 + `pytest -q`。
  - 部署前基线：必须 `pytest -q` + `flask doctor --strict`。

## 下一阶段方向

三个月第一性目标：证明用户会因为“自己真实遇到的词和句子被 RemeMate 帮他记住并用出来”，而每天回来。详见 `docs/strategy/2026-07-09-three-month-focus.md`。

1. 闭测观察：SessionPad 已完成真实双人闭环测试；线上继续只修硬 bug，软反馈进入 BACKLOG。
2. 阅读收词小优化 v1 已完成，进入真机闭测观察；继续保持「阅读收词入口」定位，不扩成专业阅读器。
3. SessionPad 后续仅按闭测证据成批处理：模块切换说明、重复发送策略等已有 BACKLOG；
   不做 guest、聊天室或实时协作。
4. Bark 能力已完成闭环：保存、测试推送、到期词提醒、签名链接打开三按钮评分回流均已在 `master`。
5. 公开门面：未登录访问 `/` 显示中英双语 Landing，登录用户仍直接进入复习首页；登录页同步双语切换。
6. 导航信息架构已完成：桌面一级导航为首页、写一写、语言伙伴、词库、我的；
   造句/历史/广场成为写作域同级视图，收到的反馈归入伙伴域；移动端使用固定底部五图标导航，
   品牌与语言/主题控件保持在同一顶栏。
7. 全站国际化已完成：`i18n-foundation` 建立独立 `ui_locale`、服务端翻译目录和全局切换路由；
   第一批覆盖导航、登录、首页复习/每日任务和设置；第二批覆盖造句、三行日记、
   AI/HTMX 状态、历史和广场；第三批覆盖生词本、词条详情/编辑、手动加词、
   文本抽词、CSV 导入和候选词审核；第四批覆盖伙伴列表、邀请与双向确认、复盘信纸、
   AI 总结、反馈包、感谢和候选词采纳；第五批覆盖阅读收词、阅读器、管理页、独立复习页和
   Bark 回流卡。全站模板与路由漏译审计已完成，Landing 保留自身明确的中英双语切换，详见
   `docs/strategy/2026-07-12-app-i18n.md`。

## 架构速记

- Flask + Jinja2 + HTMX；无前端框架。
- 三角色数据库隔离：
  - `rememate`：app 角色，FORCE RLS。
  - `rememate_dispatch`：后台写入，BYPASSRLS。
  - `rememate_owner`：DDL / migration。
- RLS 依赖 `app.current_user_id` GUC，`before_request` 设置。
- 服务层在 `app/services/*.py`，不要依赖请求上下文。
- 阅读收词归入词库：生词本、手动加词、文本抽词、阅读收词、CSV 导入。
- 生产词典外置：`DICTIONARY_DATA_DIR=/srv/rememate-data/dictionaries`。
- Bark 回流链接：`/bark/review/<token>` 免登录打开单词三按钮页。token 由
  `app/services/review_links.py` 用 `SECRET_KEY` HMAC 签名，包含 `user_id + word_id + exp`；
  路由用 `DISPATCH_DATABASE_URL` 读取/评分这一张卡，并用 `push_log` 防止同一链接重复评分。
  生产需设置 `PUBLIC_BASE_URL=https://rememate.com`，否则通知不会带可点击回流链接。
- SessionPad B1 使用 `language_partners` 表；记录只属于创建者，服务层所有查询显式传
  `user_id`，数据库启用 FORCE RLS。后续 B4-B12 已建立账号绑定、不可变反馈包、一次性感谢、
  接收方私有候选词采纳与 AI 辅助摘要；当前产品以双人、非实时的语言交换复盘为边界。
- SessionPad B2 使用 `partner_recaps` + `partner_recap_items`；信纸和条目同样 FORCE RLS，
  复合外键把 owner 贯穿伙伴、信纸、条目。`private_note` 只允许 `for_me`，`correction`
  只允许 `for_partner`。B3 通过 `intake_source_id` + `candidate_id` 接到现有候选词管道；
  只有 `for_me` 的 `expression` / `natural_phrase` 可加入，复盘仍是作者私有草稿，
  没有任何发送行为。B4 在 `language_partners` 增加 `linked_user_id` 和待确认令牌哈希；邀请令牌
  绑定目标邮箱指纹，确认跨越两个用户边界时只允许 `partner_invites` 服务通过 BYPASSRLS 事务
  更新这一条关系。迁移 head 为 `6d2e3f4a5b7c`。
  B5 使用 `partner_packets` + `partner_packet_items`；包只允许绑定关系中的发送者创建，发送者和
  接收者可读但都不能修改/删除。包保存标题、日期、双方显示名和条目正文快照，不向接收方开放
  原始复盘。迁移 head 为 `7e3f4a5b6c8d`。
  B6 使用独立 `partner_packet_thanks` 表保存一次性感谢；复合外键确保感谢者就是包接收方，
  FORCE RLS 允许双方查看、只允许接收方创建，不提供更新或删除策略。当前迁移 head 为
  `8f4a5b6c7d9e`。
  B7 在反馈包上固化 `language_code`，并使用 `partner_packet_intakes` +
  `partner_packet_item_adoptions` 保存接收方私有的候选词来源和采纳链接；发送者受 RLS 隔离，
  看不到对方是否采纳。当前迁移 head 为 `9a5b6c7d8e0f`。

## 本机与线上命令

```bash
cd /root/rememate

# 本地测试
.venv/bin/python -m pytest -q
.venv/bin/flask doctor --strict

# 本地 gunicorn
fuser -k 8891/tcp 2>/dev/null || true
.venv/bin/gunicorn -w 2 -b 0.0.0.0:8891 wsgi:app \
  --access-logfile /tmp/gunicorn-access.log \
  --error-logfile /tmp/gunicorn-error.log \
  --pid /tmp/gunicorn.pid --daemon

# 线上健康检查
ssh -i E:\\hermes.pem ubuntu@43.156.210.229 \
  'cd /srv/rememate && .venv/bin/flask doctor --strict'
```

## 部署注意

- 不覆盖 `.env`、`.venv`、数据库、`/srv/rememate-data`。
- 部署前先备份：
  - 代码：`/home/ubuntu/rememate-backups/rememate-code-*.tgz`
  - 数据库：用 `sudo -u postgres pg_dump -Fc rememate`，app/owner 角色会被 FORCE RLS 拦住。
- 当前公网入口曾确认：
  - 服务内部 `127.0.0.1:8891/login` OK。
  - nginx 内部 `Host: demo.rememate.com` OK。
  - 外部 80/443 若连不上，优先查腾讯云安全组 / DNS，而不是 Flask。

## 踩坑索引

详细原文见 `docs/archive/HANDOFF.full-2026-07-08.md`。

1. migration 跨分支污染 `alembic_version`：实验迁移必须用独立测试库。
2. 测试库 `rememate` 角色无 CREATE 权限：自动迁移需 owner 角色 `TEST_MIGRATE_DATABASE_URL`。
3. migration 要可重入：失败重试、手工 schema、跨分支 stamp 都会触发。
4. `datetime.utcnow()` 是 naive：时区计算前必须标 UTC 或用 aware UTC。
5. 时区测试别用带 DST 的城市名；固定偏移用 `Etc/GMT+9` 这类。
6. Windows/WSL 复杂 shell 引号容易炸；复杂操作写脚本，少堆一行命令。
7. Windows 文件系统可能让 SQL 文件只变 mode 位；看 `git diff` 再处理。
8. 查询计数测试访问 `db.engine` 要 `app.app_context()`。
9. UI 改造先纠职责，再调视觉；不要只换皮。
10. 词表是隐式内部概念，用户只管理语言。
11. 造/重置到期词时要用和 service 一致的 Python UTC 表盘。
12. lapse 10 分钟冷却是算法设计，UI 需要说明，不要改算法。
13. 语言切换器应保持当前页面语境，不要跳首页。
14. 设置页语言/母语选择要收起展示，避免常驻多选框扰乱页面。
15. 管理员创建账号不需要预设学习语言/母语。
16. 临时 API key 不要写入文档或提交。
17. CSS 改动易受浏览器缓存影响；必要时硬刷新或版本化静态资源。
18. WSL 服务要监听 `0.0.0.0`，真机访问用 WSL IP。
19. 真机看到和 Playwright 不一致时，先查缓存/端口/旧进程。
20. CSV 导入 AI 不可用要降级为原始列值，不要让 SSE 崩。
21. CJK 阅读文本不能全局去空格，只对 `zh/ja` 合并字间空白。
22. 中日拖选优先于单击分词，避免 3/4 字词被拆成 2 字。
23. 阅读不是专业阅读器路线，定位是“阅读收词”。
24. 生产词典数据不要进 git，放 `DICTIONARY_DATA_DIR`。
25. 候选词 ignored 只代表本批次；全局“永不建议”要另建表。
26. 每日任务卡 v2 暂停，别在当前闭测阶段继续扩大。
27. 含 CJK 字面量的 Python 文件别用 Edit 多行替换，可能出现 Unicode 弯引号。
28. `git checkout` 单文件前先 `git diff`，防止丢未提交变更。
29. 不要并行跑 integration 测试；测试库清理/事务会互相卡。
30. CJK PDF 视觉换行会污染选词；修复必须带语言守卫。
31. 8891 旧 gunicorn/pidfile 会让“重启了但没生效”；必要时 `fuser -k 8891/tcp`。

## Backlog 规则

- `docs/BACKLOG.md` 是唯一待办池。
- 已修复项不要继续留在 BACKLOG；用 git 历史和 `docs/PROGRESS.md` 查。
- 闭测软反馈先写 BACKLOG，不马上开工。
- 硬 bug 可以直接修，但修前仍要判断最小测试集。
