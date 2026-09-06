# Practice voice controls 对齐记录

代码锚点：0fc53f4a830eb29858b200384b779e6e2d7fdd24，master。

来源：本会话工具返回与用户验收。此文件为脱敏摘要，不是重新运行测试，也不是原始日志归档。

- git：用户批准后提交 0fc53f4，fast-forward 合并 master；origin/master 本地引用为 83fc2b5，ahead 1。
- 新云机 `python -m pytest tests/integration/test_practice.py -q`：49 passed。
- 相关单元 `test_practice.py`、`test_practice_voices.py`、`test_i18n.py`：24 passed。
- `node tests/unit/test_practice_voices.js`：ok；`node --check app/static/practice.js`：通过。
- 功能全量 pytest：871 passed / 8 failed；83fc2b5 干净基线：870 passed / 相同 8 failed。
- 用户在预览后表示“没问题。可以合并”。
- 8894 服务最后检查 active，登录成功，Practice 页面 200 且控件存在；共享 staging 数据库，非独立数据环境。
- 未 push / 未部署本次语音控制；本次 handoff 对齐未连接生产。
- 时间相关失败根因尚未证实；凭据与测试角色变更遗留见 docs/HANDOFF.md，不保存敏感原始输出。
