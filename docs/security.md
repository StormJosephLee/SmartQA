# 安全与权限

## 1. 鉴权
- 登录：`/api/v1/auth/login`，颁发 JWT（HS256，TTL 12h）
- 中间件：除白名单外强制校验
- 刷新：MVP 暂未实现，token 过期重新登录

## 2. 授权（RBAC）
| 角色 | 权限 |
|---|---|
| `guest` | 只能问公开知识库 |
| `user` | 自己部门知识库 |
| `kb_admin` | 上传/删除指定知识库 |
| `admin` | 全部 |

实现位置：`core/security.py` + `rag/permissions.py` + `kb.visibility` 字段

## 3. 提示注入防御
- 输入侧：`guardrails/input_filter.py` 关键词 + 规则
- 系统提示：明确"仅基于上下文回答"
- 输出侧：正则/分类器复核关键事实

## 4. 数据安全
- 文档上传只允许内网用户
- 对象存储目录不进 Git
- PII 字段在输出侧脱敏（`output_filter.check`）
- 日志脱敏（手机/身份证/邮箱，详见 [observability.md §6](./observability.md#6-pii-脱敏)）

## 5. 审计
- 所有 `messages`、`feedback` 持久化
- `observability/tracing.py` 记录全链路 trace（`X-Trace-Id` 由 `core/middleware.py` 注入）
- 关键操作（登录、上传、删除）落 `audit_log` 表

## 6. 合规清单
- [ ] 用户协议与隐私政策
- [ ] 数据保留策略（默认 180 天）
- [ ] 用户可申请删除自己的数据
- [ ] 模型 API 调用方合规（与 LLM 服务商签 DPA）
