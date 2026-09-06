# D01 前仓库修剪计划

> 基准：master@0fc53f4；工作分支：chore/pre-d01-repo-pruning。
> 用户已批准：推荐路线、D01 前债务修剪及推荐执行边界（工具问答确认）。
> 状态：首轮修剪完成，工作区未提交；测试基线问题交 D01，不在本票删除失败用例。
> 此前 handoff/决策票的未提交改动原样保留，不丢弃、不混入删除提交。

## 目标与安全边界

降低重复资源、过时入口和一次性操作脚本的维护成本，不改变产品功能或通过删除失败用例制造绿灯。
仅处理 Git 工作树；不改写 Git 历史，不 push、部署，不读取或修改 .env/.venv、云机数据库/账号、词典及生产数据。
数据库清理不属于本票。若后续要回收云机测试目录或数据，需另列对象、依赖、备份与批准。

## 只读盘点结论

- Git 中 docs 有 139 个文件，约 6.14 MiB；tests 有 94 个文件，约 0.81 MiB。
- 发现 55 张 docs 图片与 app/static 中图片 SHA-256 完全一致，共 5,502,389 字节（约 5.25 MiB）：FAQ 44 张、blog 研究图片 11 张。
- 运行时 app/static 副本保留。docs 引用、截图生成脚本的输出路径必须随去重同步，否则不能删。
- .pi 下跟踪了 6 个历史远程操作脚本/报告，需逐份审查用途及引用；不能只因为位于 .pi 就全部删除。
- tests Python 文件未发现同文件顶层测试函数重名覆盖。测试按语言、RLS、迁移分开不等于重复。
- docs/FAQ/README.md 仍写草稿/待落位，但公开 FAQ 已在 Git 代码中落地；需改为当前内容源说明和历史制作参考。

## 分批操作

### A — 重复资源去重

- 逐文件确认相同哈希，保留 app/static 正式资源。
- 更新 Markdown 与制作脚本引用，只删除被证明冗余的 docs 副本。
- 不删除正式图片、许可证、第三方归属或研究事实来源。
- 验证修改过的相对链接、脚本语法、内容相关测试以及 git diff --check。

### B — 文档与操作脚本

- 当前事实集中在恢复入口、HANDOFF、BACKLOG 与代码；最初定位/产品原则和关键安全设计保留。
- 过时大计划先剥离当前权威身份；仍被代码/测试/设计引用的契约不直接删。
- 无复用价值的一次性调试/远程操作脚本列具体清单后移除，必要经验压缩到文档；禁止运行这些脚本验证其价值。
- 保留历史 migration 文件，不 squash、不删除；保留有效 fixture、样例数据及截图制作必要输入。

### C — 测试审计

- 输出“用例 → 公开行为 → 是否有等效覆盖”清单，再决定参数化、合并或删除。
- 保留安全、RLS、额度、认证、迁移、并发、幂等和核心流程回归。
- 不因当前失败、耗时或名字过时就删除；8 个基线失败继续交 D01 分类排查。
- 测试行为变化运行对应套件；需要数据库时使用 D01 的隔离方案，不自行重设共享角色凭据。

## 完成定义

每项删除有路径与依据；没有新增断链；运行时资源不变；测试覆盖去留可解释；当前未提交交接改动保留；D01 前待办边界清晰。
本计划不是“大扫除式”重构授权；审计若找不到可安全删除的测试，就保留并明确报告。

## 本轮结果与删除依据

### 实际删除 69 个 Git 文件

- `docs/FAQ/images/*.png`：44 张，与 `app/static/public/qa/{en,zh}/` 对应图片 SHA-256 相同。正式资源未动，历史 Markdown 已改用相对链接。
- `docs/research/polyglot-columns/images/*.jpg`：11 张，与 `app/static/public/blog/<slug>/` 对应图片 SHA-256 相同。研究文章与来源保留，图片引用更新。
- `.pi/bark_real_push.sh`、`.pi/bark_real_verify.sh`：一次性测试账号 SQL、真实推送和用户/Bark 配置输出；正常功能已有 dispatch runner 和集成测试，不保留危险示范入口。
- `.pi/rerun-migrate-check.sh`、`.pi/rerun-write-tests.sh`、`.pi/tencent-dispatch-test.sh`：旧固定云机目录的重复运行/同步脚本；存在覆盖共享工作区、输出凭据或弱退出码信号的风险，不能当作 D01 基础。历史 report 保留并显式标为不可直接执行。
- `docs/FAQ/scripts/{capture,capture2,capture3,en_capture,probe,story_capture}.py`：一次性截图/数据准备；六份包含硬编码测试密码，绑定旧路径与账号，只有旧 FAQ README 引用。全部移除，不执行。
- `docs/FAQ/scripts/to_qa_yaml.py`：一次性草稿转换，顶层执行覆盖正式 YAML 且固定 indexable=false；正式正文现直接维护，删除防止误覆盖。
- `docs/FAQ/scripts/make_pdf.py`、`sample-fr.pdf`：只供上述旧截图脚本使用，仓库外部引用审计未发现运行时/测试依赖；随消费者删除。

图片去重节省 5,502,389 字节（约 5.25 MiB）工作树空间；这不等于 Git 历史体积减少。历史凭据也不会因删除工作树文件而失效，轮换需单独批准。

### 测试审计：保留，不盲删

| 用例/资产 | 判断 | 处理 |
| --- | --- | --- |
| Python 顶层同名测试 | 未发现同文件覆盖 | 不改 |
| Python 顶层测试 AST 正文完全重复 | 未发现相同正文组；这只是机械筛查，不等于所有测试都有独立价值 | 不自动删除 |
| public_content 临时 catalog 的 noindex 测试 | 验证配置为 false 时的行为，与正式页面允许索引并不矛盾 | 保留 |
| public_content 正式资源旧 placeholder 断言 | 在 Git 已允许 index 时仍断言 false，需 D01 校正合同 | 保留失败信号，不跳过 |
| Practice 的 fr/ja/zh、HTTP、RLS、migration 测试 | 表面结构重复但语言/权限/状态行为不同 | 保留 |
| fixture 数据、迁移历史、研究来源与初始产品目标 | 无充分证据表明无用 | 保留 |

不为了达到删测数量而修改测试。D01 分类失败后再讨论参数化或替代覆盖。

### 验证

- 71 处修改 Markdown 的图片引用存在，无缺图。
- `git diff HEAD -- app content tests migrations` 为空：正式代码/资源、测试和迁移未变。
- `python -m pytest tests/unit/test_public_content.py --noconftest -q`：10 passed / 2 failed；失败为已有 `test_repo_placeholders_load`、`test_public_routes_render_placeholders` 的 indexable/noindex 断言，不是资源丢失。
- 本轮未运行全量或数据库集成测试，未连接云机、不重设角色、不删账号、不触及词典/生产数据。
- `.pi/quiet-tools/` 加入 ignore，仅防止误提交，不批量删除已有工具输出。
- 交接入口已同步当前分支及批准顺序，旧 draft README 已改为正式内容源与历史参考边界。

