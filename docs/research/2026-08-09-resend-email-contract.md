# Resend 邮件发送契约（Python `requests` adapter）

> 研究日期：2026-08-09。外部事实仅来自 Resend 官方文档或官方 `resend-python` 源码；本文不含凭据。

## 官方事实

### Endpoint、认证与 headers

- 发送接口是 `POST https://api.resend.com/emails`；API 强制 HTTPS。[API introduction](https://resend.com/docs/api-reference/introduction) · [Send Email](https://resend.com/docs/api-reference/emails/send-email)
- 直接调用必须带 `Authorization: Bearer <API key>`；所有 API 请求还必须带 `User-Agent`，缺失时会返回 `403`。 [API introduction](https://resend.com/docs/api-reference/introduction)
- 官方 JSON 请求示例带 `Content-Type: application/json`；文档没有另行说明省略该 header 时的行为，因此对“是否独立强制”记为 **unknown**。[Send Email](https://resend.com/docs/api-reference/emails/send-email)
- `Idempotency-Key` 不是普通发送的必需 header，而是可选的幂等控制；其语义见下文。[Idempotency Keys](https://resend.com/docs/dashboard/emails/idempotency-keys)

### 最小 request 与成功响应

- API schema 将 `from`、`to`、`subject` 标为 required；数组形式的 `to` 最多 50 个地址。[Send Email](https://resend.com/docs/api-reference/emails/send-email)
- 官方最小发送示例再提供 `html`；`text` 是另一种内容字段，未提供时文档说明会由 HTML 生成纯文本。文档没有把 `html` 或 `text` 单独标成 required，因此“二者至少一个是否由服务端强制”是 **unknown**；模板发送另有契约。[Send Email](https://resend.com/docs/api-reference/emails/send-email)
- 文档列出 `200` 为成功状态；发送响应包含邮件 `id`。[API introduction](https://resend.com/docs/api-reference/introduction) · [Send Email](https://resend.com/docs/api-reference/emails/send-email)

### 错误结构与可分类状态

- Resend 官方错误页确认使用标准 HTTP 状态码，并按 error type 进一步分类；每个条目同时给出 status、message 和 suggested action。[Errors](https://resend.com/docs/api-reference/errors)
- 官方错误页没有给出原始 HTTP error JSON 的完整字段 schema；因此原始 body 的字段名/必选性为 **unknown**。官方 Python SDK 的 `ResendError` 则暴露 `code`、`error_type`、`message`、`suggested_action` 和 `headers`；这是 SDK 归一化后的接口，不等同于原始 body schema。[official `exceptions.py`](https://github.com/resend/resend-python/blob/main/resend/exceptions.py)
- 可按官方 type/status 做最小分类：`400`=`invalid_idempotency_key`/`validation_error`；`401`=`missing_api_key`/`restricted_api_key`；`403`=`invalid_api_key` 或发送限制类 `validation_error`；`404`=`not_found`；`405`=`method_not_allowed`；`409`=`invalid_idempotent_request`/`concurrent_idempotent_requests`；`422`=`invalid_attachment`/`invalid_from_address`/`invalid_access`/`invalid_parameter`/`invalid_region`/`missing_required_field`；`429`=`monthly_quota_exceeded`/`daily_quota_exceeded`/`rate_limit_exceeded`；`451`=`security_error`；`500`=`application_error`/`internal_server_error`。[Errors](https://resend.com/docs/api-reference/errors)

### Idempotency-Key

- 支持 `POST /emails` 和 `POST /emails/batch`；header 名为 `Idempotency-Key`，长度上限 256，且应按 API request 保持唯一。[Idempotency Keys](https://resend.com/docs/dashboard/emails/idempotency-keys)
- Resend 按最近 24 小时检查 key；同 key 的同一请求会返回相同响应且不重复发送，key 在系统中保留 24 小时。[Idempotency Keys](https://resend.com/docs/dashboard/emails/idempotency-keys)
- 同 key 搭配不同 payload 返回 `409 invalid_idempotent_request`，文档说明仅改变 key 或 payload 才有意义；同 key 请求并发处理中返回 `409 concurrent_idempotent_requests`，稍后重试是安全的。无效 key 返回 `400 invalid_idempotency_key`。[Idempotency Keys](https://resend.com/docs/dashboard/emails/idempotency-keys) · [Errors](https://resend.com/docs/api-reference/errors)
- 文档没有规定 payload 差异比较的精确算法、时钟边界或并发重试等待时长；这些均为 **unknown**。[Idempotency Keys](https://resend.com/docs/dashboard/emails/idempotency-keys)

### Rate limit、429 与客户端 timeout/retry

- 官方列出的响应 headers 是 `ratelimit-limit`、`ratelimit-remaining`、`ratelimit-reset`、`retry-after`；其含义分别是窗口上限、剩余量、重置秒数和后续请求应等待的秒数。[Usage Limits](https://resend.com/docs/api-reference/rate-limit)
- 当前文档写明默认速率为每 team 每秒 10 个请求，所有该 team 的 API key 共享；超限返回 `429`。邮件配额另有 `x-resend-daily-quota`（仅 free plan）和 `x-resend-monthly-quota` headers，超额也是 `429`。[API introduction](https://resend.com/docs/api-reference/introduction) · [Usage Limits](https://resend.com/docs/api-reference/rate-limit)
- Resend API 文档没有规定客户端必须使用的 timeout、重试次数、退避算法或哪些网络异常必须重试，均为 **unknown**。[API introduction](https://resend.com/docs/api-reference/introduction) · [Send Email](https://resend.com/docs/api-reference/emails/send-email)
- 官方 `resend-python` 的 `RequestsClient` 源码默认 timeout 为 30 秒，单次调用 `requests.request` 并返回 body/status/headers；所审文件没有 retry loop 或 `HTTPAdapter`/`Retry` 配置。这是 SDK 实现细节，不是 API 对所有客户端的规定。[official `http_client_requests.py`](https://github.com/resend/resend-python/blob/main/resend/http_client_requests.py)

## 本仓库现有 requests/HTTP adapter 风格（只读观察）

- [app/services/notifications.py](../../app/services/notifications.py#L57-L82) 的 `send_bark_payload` 通过可注入的 `post` seam 调用 `requests.post`，默认 timeout 为 5 秒，禁用 redirects；捕获 `requests.RequestException`，并将非 2xx 统一转换为 `NotificationError`。当前仓库没有通用的 `Session`/`HTTPAdapter` 重试层。

## 本项目设计建议（非 Resend 官方事实）

- 保留现有可注入 HTTP seam，但 Resend adapter 应显式设置 `Authorization`、`User-Agent`、JSON `Content-Type`，并使用项目自行决定的显式 timeout；该 timeout 不应被表述为 Resend 要求。
- 为每个逻辑邮件事件生成在 24 小时内稳定的幂等 key；对 transport failure、`429`、`5xx` 和 `409 concurrent_idempotent_requests` 做有上限的重试，并复用同一 key；`409 invalid_idempotent_request`、其他已分类 `4xx` 不自动重试。`retry-after` 若存在则优先采用。以上是本项目策略，不是官方 retry 保证。
- 适配器应保留 status、官方 error type、message 以及安全的 rate-limit headers，避免像现有 Bark helper 一样丢失分类；日志不得输出 Authorization、请求 body 或完整响应敏感内容。

## 未决项

- 原始 Resend error JSON 的确切字段 schema：**unknown**；目前只有官方错误分类页和 SDK 归一化异常契约。
- 官方 API 对 timeout/retry 的强制规则：**unknown / 未规定**；SDK 的 30 秒默认值不能升级为 API 契约。
- `retry-after` 在每一种 `429` 响应中的必然存在性、具体限流窗口算法和建议退避/jitter：**unknown**；官方只规定了 header 含义及 `429` 分类。
