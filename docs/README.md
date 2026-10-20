# SmartQA 文档中心

> 所有团队协作文档的统一入口。新人请按顺序阅读。
> **所有设计/实现与 [`spec.md`](../spec.md) 不一致时，以 `spec.md` 为准。**

## 必读（按顺序）
1. [onboarding.md](./onboarding.md)         新人 30 分钟上手
2. [architecture.md](./architecture.md)     系统架构总览
3. [dataflow.md](./dataflow.md)             一次问答的端到端数据流
4. [api.md](./api.md)                       HTTP 接口规范

## 设计参考
- [rag_design.md](./rag_design.md)          RAG 模块设计
- [agent_design.md](./agent_design.md)      Agent 模块设计
- [security.md](./security.md)              安全 / 权限 / 合规
- [observability.md](./observability.md)    横切可观测规范（日志结构 / LLM I/O / Trace / 脱敏）
- [deployment.md](./deployment.md)          部署与运维
- [roadmap.md](./roadmap.md)                演进路线与里程碑

## 其它
- [faq.md](./faq.md)                        常见问题

## 文档维护
- 修改前先开 issue 讨论（避免冲突）
- 任何架构调整必须同步更新 architecture.md 与对应子模块设计文档
- 用 Mermaid 画图，保证在 GitHub/IDE 中可直接渲染
