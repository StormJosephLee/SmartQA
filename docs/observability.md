# 可观测性规范

> 横切关注点。覆盖三大模型适配层（LLM / Embedding / Rerank）的调用 I/O 日志、Trace 传播、PII 脱敏与可观测接入。
>
> 当本文档与 [`architecture.md`](./architecture.md) "## 1. 设计原则" 第 4 条「全链路可观测」冲突时，以 [`spec.md`](../spec.md) 为准。

## 1. 目标与范围

| 维度 | 目标 |
|---|---|
| 可调试 | 任意一次失败的 LLM/Embedding/Rerank 调用，能在 5 分钟内定位：哪条请求、用的什么模型、传的什么入参、拿到了什么返回 |
| 可度量 | 三个适配层的成功率 / p50 / p95 / 重试率 可直接由结构化字段聚合 |
| 可回溯 | 全链路 trace_id 一致，可与 Langfuse trace 对齐 |
| 合规 | 入参/返回中的 PII（手机/身份证/邮箱）在日志侧完成脱敏，不外泄 |

**范围内**：`llm/chat.py`、`llm/embedding.py`、`llm/rerank.py`、`observability/tracing.py`、`core/middleware.py`。
**范围外**：业务侧日志（参考各模块设计文档）、运维告警（参考 [`deployment.md`](./deployment.md) §5）。

## 2. 设计原则

1. **结构化优先**：每个模型调用必须用 `logger.info/warning/error` 打**一条**主日志，附标准字段（见 §4），不允许仅 `print`。
2. **一次请求 = 一条 trace**：trace_id 在 HTTP 入口由 `core/middleware.TraceIdMiddleware` 注入，所有下游日志通过 `core.logging.get_logger` 自带的 `_TraceFilter` 自动带上 `trace=<id>`；后台任务（入库 / Rerank 队列）使用独立 trace。
3. **入参精简**：只记录**判断行为必需**的元数据（数量、长度、模型、参数键名）；长文本按策略截断。
4. **返回量化**：不打印完整 embedding 数组（动辄上千维），只打印维度与耗时。
5. **失败带 detail**：抛 `BizError` 时把 `upstream_status` / `upstream_code` / `transient` 放进 `detail`（已由 [`llm/embedding.py`](../llm/embedding.py) 落地）。
6. **PII 兜底**：所有可能含用户内容的字段在落入日志前调用 [`core.logging.mask_pii`](./security.md#4-数据安全) 脱敏。

## 3. 三大模型调用的 I/O 日志规范

### 3.1 LLM 文本生成（`llm/chat.py`）

| 阶段 | 级别 | 关键内容 |
|---|---|---|
| 请求发起 | INFO | `llm.complete -> model=<model> attempt=<n> messages=<count> chars=<sum>`；含模型回退时附加 `fallback_model=<m>` |
| 请求成功 | INFO | `llm.complete OK model=<m> attempt=<n> chars=<len> tokens=p/c/t cost=<ms>`；`tokens` 来自 `usage` 字段 |
| 瞬时失败重试 | WARNING | `llm call failed model=<m> attempt=<n>: <exc>` |
| 最终失败 | ERROR | `llm.complete failed model=<m>: <exc>`（`BizError.llm_upstream` 抛出） |
| 流式首块 | DEBUG | `llm.stream -> model=<m> first_chunk=<ms>` |

**入参打印规则**：
- `messages` 列表：只打印**条数**与**总字符数**，禁止打印单条 `content`。
- 单条 `content` > 2k 时仅打印前 200 字符 + `...<truncated N chars>...`，调用 `mask_pii`。
- `temperature` / `top_p` 等控制参数：完整打印。
- `tools`（function calling）：打印工具名列表，不打印 schema 全文。

**返回打印规则**：
- 首段文本长度 + 是否流空（流式时按累计）。
- token 三件套：`prompt_tokens / completion_tokens / total_tokens`（注意 PII：可能含系统提示原文 → 视为非敏感）。
- 严禁打印 `choices[0].message` 全文超过 500 字符。

### 3.2 Embedding（`llm/embedding.py`）

| 阶段 | 级别 | 关键内容 |
|---|---|---|
| 请求发起 | INFO | `embedding -> model=<m> base_url=<u> texts=<n> chars=<sum> dimensions=<d or None>` |
| 降级（服务端不支持 dimensions） | WARNING | `embedding 服务端不支持 dimensions=<d>,降级为原生维度后继续重试: <exc>` |
| 维度不符（非严格模式） | WARNING | `embedding 维度不符: got=<g>, expected=<e>...` |
| 维度不符（严格模式 / 抛错） | ERROR | 同上 + 抛 `BizError(status=400)` |
| 瞬时失败重试 | WARNING | `embedding 瞬时失败 model=<m> upstream_status=<s> upstream_code=<c> attempt=<i>/<n>, <w>s 后重试: <msg>` |
| 最终失败 | ERROR | `embedding 失败 model=<m> upstream_status=<s> upstream_code=<c>: <masked msg>` |
| 成功 | INFO | `embedding OK model=<m> count=<n> dim=<d> dimensions=<d or None> strict=<bool> cost=<ms>` |

**入参打印规则**：
- `texts`：仅打印**条数**和**总字符数**；禁止打印单条文本。
- `model` / `base_url` / `dimensions`：完整打印。

**反参打印规则**：
- **不打印** `embedding` 数组本体；只打印维度。
- 打印重试次数（`attempts`）。
- 严格模式命中时，附带 `detail={got, expected, requested}` 入参数。

### 3.3 Rerank（`llm/rerank.py`）

| 阶段 | 级别 | 关键内容 |
|---|---|---|
| 模块导入时（一次性校验） | WARNING | `rerank provider=<v> 不在合法值 [...] 中,自动按 none 处理` |
| 关闭分支（disabled） | _静默_ | 已由启动期日志覆盖；调用期不再打 INFO，避免噪声 |
| 请求发起 | DEBUG | `rerank -> model=<m> base_url=<u> docs=<n> top_n=<k>`（默认 DEBUG 可关） |
| 服务端错误降级 | WARNING | `rerank failed, fallback to fusion order: <exc>` |
| 返回空配对 | WARNING | `rerank returned no valid pairs, keep fusion order` |
| 成功 | INFO | `rerank OK model=<m> docs=<n> top_n=<k> hits=<h> cost=<ms>` |

**入参打印规则**：
- `query`：只打印**前 30 字符** + `len=<N>`，调用 `mask_pii`。
- `documents`：只打印**条数**；单条 `>500` 字符时仅打印首 80 字符并 mask。

**反参打印规则**：
- `hits`：返回条数。
- **不回**原始下标-分数完整列表（量大）。

## 4. 日志结构与字段

```
<时间> <LEVEL-7s> [<module>] trace=<id or ->-<>> <message>
```

**标准字段**（key=value 形式附加在 message 中，便于 grep / logfmt 聚合）：

| 字段 | 含义 | 必备 |
|---|---|---|
| `model` | 调用的模型名 | ✓ |
| `attempt` / `i/n` | 当前/总尝试次数 | 重试相关日志 |
| `cost=<ms>` | 单次调用耗时 | 成功/最终失败 |
| `tokens=p/c/t` | prompt/completion/total | LLM 特有 |
| `dim` / `dim` / `dimensions` | embedding 维度或请求值 | embedding 特有 |
| `docs` / `top_n` / `hits` | 文档数 / 取 Top-N / 命中数 | Rerank 特有 |
| `upstream_status` | 上游 HTTP 状态码 | 失败日志 |
| `upstream_code` | 上游业务 code（OpenAI `error.code`） | 失败日志 |
| `transient=true/false` | 是否为可重试错误 | 失败日志 |

> 已部分实现于 [`core/logging.py`](../core/logging.py)；后续接入 logfmt/JSON 渲染时按本表字段对齐。

## 5. 日志级别矩阵

| 场景 | 级别 |
|---|---|
| 正常成功 | INFO |
| 瞬时失败但计划重试 | WARNING |
| 降级（服务端不支持 dims / Rerank 关闭） | WARNING（启动期一次性）|
| 业务校验失败（输入超长、维度不符严格模式） | ERROR |
| 最终失败（重试耗尽 / 客户端 4xx / 连接拒绝） | ERROR（同时抛 `BizError`）|
| 调试详情（流式首块、首字节、prompt 截断） | DEBUG（生产默认关闭）|

## 6. PII 脱敏

- 适配层在拼装日志 message 前**必须**对可能含用户输入的字段调用 `mask_pii()`。
- 范围（与 [`security.md` §4](./security.md#4-数据安全) 对齐）：
  - 手机号（中国大陆 11 位）→ `***PHONE***`
  - 身份证号（17 位 + 校验位）→ `***IDNO***`
  - 邮箱 → `***EMAIL***`
- 已实现于 [`core/logging.py:mask_pii`](../core/logging.py)；三个适配层必须复用，禁止自写正则。

## 7. Trace 传播

- HTTP 请求进入时由 [`core/middleware.TraceIdMiddleware`](../core/middleware.py) 生成或透传 `X-Trace-Id`，写入 `request.state.trace_id`，并在响应头回写。
- 日志通过 `_TraceFilter` 自动追加 `trace=<id>` 字段；后台任务（如 `services/kb_service.run_ingestion`）应**自行生成**独立 trace_id（如 `f"bg-{uuid.uuid4().hex}"`）以便隔离。
- `BizError.detail` 不必携带 trace_id（已由响应头 + 日志双通道记录）。

## 8. Langfuse 接入

- 配置：`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`（详见 `.env.example`）。
- 未配置时 [`observability/tracing.py:trace_span`](../observability/tracing.py) 退化为 no-op，业务代码无需分支。
- 关键埋点：
  - LLM 调用整体（`agent_design.md` 中每一轮 Planner / Reflector / Answer）
  - RAG 主链（`rag_design.md` 中 Embedding → Vector Recall → Rerank）
  - 工具调用（`web_search` / `db_query`）
- **禁止把 PII 直接喂给 Langfuse metadata**；metadata 中只放 `model / latency / tokens / dims` 等结构化字段。

## 9. 配置开关

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `LOG_LEVEL` | 全局日志级别 | `INFO` |
| `LLM_MAX_RETRIES` | LLM/Embedding/Rerank 瞬时错误重试次数 | `3` |
| `LLM_RETRY_BACKOFF` | 初始退避秒数（指数增长）| `1.0` |
| `EMBEDDING_STRICT_DIM` | 维度不符时是否严格抛错 | `false` |
| `LANGFUSE_*` | Langfuse 接入（留空则 no-op） | _空_ |
| `RERANK_PROVIDER` | `none` / `http`，非法值启动期告警 | `none` |

详见 [`.env.example`](../.env.example)。

## 10. 示例日志

```
2026-10-20 14:25:01,221 INFO    [llm.chat] trace=3f9c1b… llm.complete -> model=deepseek-chat attempt=0 messages=4 chars=1820
2026-10-20 14:25:01,884 INFO    [llm.chat] trace=3f9c1b… llm.complete OK model=deepseek-chat attempt=0 chars=312 tokens=248/118/366 cost=663ms
2026-10-20 14:25:02,001 INFO    [llm.embedding] trace=3f9c1b… embedding -> model=BAAI/bge-m3 base_url=https://api.siliconflow.cn/v1 texts=5 chars=2408 dimensions=1024
2026-10-20 14:25:02,107 WARNING [llm.embedding] trace=3f9c1b… embedding 瞬时失败 model=BAAI/bge-m3 upstream_status=500 upstream_code=server_overloaded attempt=1/4，1.5s 后重试: Service load is too high
2026-10-20 14:25:03,901 INFO    [llm.embedding] trace=3f9c1b… embedding OK model=BAAI/bge-m3 count=5 dim=1024 dimensions=1024 strict=False cost=1900ms
2026-10-20 14:25:04,012 INFO    [llm.rerank] trace=3f9c1b… rerank OK model=BAAI/bge-reranker-v2-m3 docs=20 top_n=5 hits=5 cost=87ms
```

## 11. 何时升级为告警

与 [`deployment.md` §5](./deployment.md#5-监控) 对齐。本规范内的"何时 PagerDuty/飞书"由运维侧定义；本规范只规定**日志必含字段**，确保告警规则可写。

## 12. 反模式（不要做的事）

1. ❌ 在 `print()` 中输出 embedding / LLM 返回全文 → 必须走 logger
2. ❌ 把 API Key / JWT Token 写进日志（mask_pii 不覆盖这些，需要在写入前自行过滤）
3. ❌ 把 `messages[*].content` 完整打印（即使脱敏后也不允许，超长）
4. ❌ 每条 query 都打 "rerank disabled" INFO 日志（启动期一次性即可）
5. ❌ 把 `upstream_status` / `upstream_code` 拼到 message 字符串后丢失结构（必须独立字段）
6. ❌ 后台任务不复用 `get_logger`、不附加 trace_id
7. ❌ Langfuse metadata 直接传用户输入 → 仅传结构化字段