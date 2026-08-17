# RemeMate FAQ 图文文档（工作区）

> 日期：2026-08-17 · 状态：草稿待审（定稿后正文与图片将按线上呈现方式落位，见文末）

## 内容

| 文件 | 说明 |
|---|---|
| `outline.md` | FAQ 大纲：8 节 40 问，四段式（一句话结论/功能解释/注意事项/故障怎么办）+ 截图清单 + 写作约束 |
| `faq.zh.md` | 中文 FAQ 全文（grok 按大纲撰写，含全部截图引用） |
| `faq.en.md` | 英文 FAQ 全文（与中文成对） |
| `images/` | 40 张截图：`faq-<编号>-<页面>-<语言>.png`（zh 20 张 + en 20 张），全部来自测试新云机 staging |
| `scripts/` | 截图与 PDF 生成脚本（可复现） |

## 截图来源

- 环境：测试新云机 `staging.rememate.com`（159.75.35.39 上的 `rememate-staging.service`，独立 staging 库，**非生产**）
- 截图方式：SSH 隧道 → 本地 headless Chrome（playwright），1440×900，zh/en 双界面
- 测试账号：`faq-test@example.com`（staging 独立库内创建；数据：法语 11 词、1 位语伴、1 份阅读文档）
- 注册页截图期间临时打开过 staging 的 `OPEN_REGISTRATION_ENABLED`，拍完已恢复 `false` 并重启验证（服务正常、/register 回 404）
- 生产机（`/srv/rememate`）全程未动

## 复现

```bash
# 1) 建隧道
ssh -N -L 8892:127.0.0.1:8892 tencent-new
# 2) 截图（zh 全流程 + en 全流程）
python docs/FAQ/scripts/capture3.py      # zh，含数据流（quick-add→候选→入库→复习→故事）
python docs/FAQ/scripts/story_capture.py # 补拍故事（需当天复习 ≥10 词）
python docs/FAQ/scripts/en_capture.py    # en（复用已造数据；注册页需临时开注册开关）
python docs/FAQ/scripts/make_pdf.py      # 阅读用测试 PDF（pypdf 本地验证）
```

## 定稿落位（待与用户确认呈现形态）

- 图片最终移到 `app/static/public/qa/<stable-key>/`（若进公开 `/qa` 页，代码强制该 scope；blog 才用 `public/blog/<slug>/`）
- 正文最终形态二选一：进 `content/en/qa.yaml` + `content/zh/qa.yaml`（公开 FAQ 页，可收录），或作为站内帮助文档
- 本目录仅作草稿工作区，不入生产服务
