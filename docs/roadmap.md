# 演进路线

| 阶段 | 周次 | 主题 | 交付物 | 验收标准 |
|---|---|---|---|---|
| **P0 骨架** | W1 | LLM 对话 | FastAPI + /chat + Streamlit | 能跑通 Hello-LLM |
| **P1 RAG** | W2-3 | 知识库 | 文档上传/检索/引用 | 答案带引用，召回率≥0.7 |
| **P2 Agent** | W4 | 工具调用 | web_search + calculator + db_query | 复杂问题可拆解并执行 |
| **P3 工程化** | W5-6 | 鉴权/观测/评估 | JWT、Langfuse、eval 集 | 单元测试≥60% 覆盖 |
| **P4 集成** | W7+ | IM / 多租户 | 飞书/钉钉、RBAC | 真实用户跑通 |
| **P5 规模化** | 持续 | 性能/成本 | k8s、缓存、prompt 优化 | p95 ≤ 3s，成本降 30% |

## 当前进度
- [x] P0 骨架
- [x] P1 RAG
- [x] P2 Agent
- [ ] P3 工程化
- [ ] P4 集成

## 决策记录（ADR）
- **ADR-001**：向量库选 pgvector 而非 Milvus
  - 理由：组件少、运维简单；后续如向量 > 1e8 迁移
- **ADR-002**：Agent 框架用 LangGraph
  - 理由：可观测、状态清晰；后续可能自研以减依赖
- **ADR-003**：前端用 Streamlit 而非 React
  - 理由：MVP 验证期，先快后好
- **ADR-004**：代码布局采用**顶层多包**（`api/ core/ llm/ services/ rag/ agents/ memory/ guardrails/ observability/ db/ schemas/ ui/`）
  - 理由：与 `onboarding.md`、`architecture.md` 的模块心智一致
  - 影响：`security.md` 中历史遗留的 `app/core`、`app/guardrails`、`app/observability` 路径已统一为顶层包
  - 新增包说明：`core/`（横切能力）、`llm/`（模型适配层）、`schemas/`（DTO）、`ui/`（前端）
