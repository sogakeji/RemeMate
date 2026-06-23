# LLM Provider 故障转移设计

> 记录日期：2026-06-22
> 状态：架构预埋，P1 实现

---

## 背景

RemeMate 的 AI 功能（批改、抽词、对话、清洗、翻译）全部调 DeepSeek。高并发或 DeepSeek 服务故障时，无 fallback 会导致核心功能全线挂掉。需在 LLM 服务层预埋 provider 抽象，支持自动故障转移。

---

## Provider 优先级

| 优先级 | Provider | 用途 | 成本 |
|---|---|---|---|
| 1（主） | DeepSeek | 所有功能 | 最低 |
| 2（备） | OpenAI GPT-4o-mini | 流式对话 + 批改 | 中 |
| 3（备） | Groq（llama3/mixtral） | 非流式清洗 + 抽词 | 低，限速 |

具体 provider 组合可按上线时价格/可用性调整，关键是抽象层在 P1 就要有。

---

## 架构：Provider 抽象层

```python
# services/llm.py — 唯一对外接口，调用方不感知底层 provider

def chat(messages, stream=False, task='general') -> str | Generator:
    for provider in get_provider_chain(task):
        if circuit_breaker.is_open(provider):
            continue
        try:
            return provider.call(messages, stream=stream)
        except (Timeout, ProviderError) as e:
            circuit_breaker.record_failure(provider)
            continue
    raise AllProvidersDown()
```

所有 AI 功能（批改、抽词、对话、NSFW 检测、翻译）统一走 `llm.chat()`，不直接调 DeepSeek SDK。

---

## 熔断器（Circuit Breaker）

- 单 provider 连续失败 N 次（建议 N=3）→ 标记为 DOWN，跳过 T 分钟（建议 T=5）
- T 分钟后自动进入 HALF-OPEN，试探一次
- 成功 → 恢复 CLOSED；失败 → 重新 OPEN T 分钟
- **状态存内存即可**：P1 部署为 `gunicorn -k gevent -w 2`（见 v0.1 §2.2/§6）。gevent 单进程内协程共享内存，熔断状态一致；`-w 2` 下是 2 个独立熔断器，差异可接受（最坏一个 worker 多试探一次）。不引入 Redis。P2 若升多进程/多节点再上 Redis 共享状态

---

## 各功能的降级策略

| 功能 | 全部 provider DOWN 时 |
|---|---|
| 造句批改 | 提示"AI 暂时不可用，稍后重试"，句子保存草稿 |
| /extract 抽词 | 提示排队，写入待处理队列，恢复后自动处理 |
| 词汇清洗（导入） | 同上，导入任务进队列 |
| AI 对话 | 提示"AI 助教暂时休息中" |
| NSFW 检测 | 默认 is_nsfw=True（**fail-closed**，保守隐藏公开按钮），记录 flag 待事后审核；公开社交内容不可 fail-open |
| 句子翻译 | 跳过翻译，广场卡片只显示目标语言句 |

---

## Token 计费兼容

- 用户自带 key 的请求：key 绑定 provider（DeepSeek key 只走 DeepSeek）
  - DeepSeek DOWN 时：提示用户"您的 DeepSeek key 当前不可用"，不自动切换（避免用系统 key 消耗）
- 系统 key 的请求：按优先级自动 failover，计费记到对应 provider 的系统成本

---

## 各 task 的 provider 链（显式）

NSFW 检测只挂 DeepSeek，无备用 provider。DeepSeek DOWN 时直接走 fail-closed（is_nsfw=True），不路由到 GPT/Groq（它们的内容审核能力和 prompt 格式未验证）。

| task | provider 链 |
|---|---|
| 造句批改 / 翻译 / NSFW | DeepSeek → GPT-4o-mini（NSFW 除外，NSFW 仅 DeepSeek） |
| /extract 抽词 / 词汇清洗 | DeepSeek → GPT-4o-mini → Groq |
| AI 对话（流式） | DeepSeek → GPT-4o-mini |

---

## 流式响应的 failover 限制

首 token 已下发后，**不支持中途切换 provider**——SSE 流已经开写，切换会导致响应截断。

已知限制（接受）：
- 流式中途断流 → 提示用户"响应中断，请重试"，不自动切 provider
- 预流式失败（调用即抛异常）→ 正常 failover 到下一 provider

---

## 请求级总超时

链式 failover 最坏情况（每 provider 各超时）会累计到不可接受的等待时间。规则：

- **单 provider 超时**：10s
- **请求级总 deadline**：25s（跨所有 provider 共享）
- 超过 25s 抛 `AllProvidersDown`，不再尝试

---

## 实现优先级

- **P1 必须有**：Provider 抽象层 + 至少一个备用 provider 配置（即使不启用，接口要在）；25s 总超时；NSFW fail-closed
- **P1 建议有**：简单熔断器（内存版；`-w 2` 下每 worker 各一份，单 worker 内 gevent 协程共享状态一致，跨 2 worker 的微小差异可接受，不需要 Redis）
- **P2**：Redis 熔断状态（若将来升多进程）、provider 成本监控面板
