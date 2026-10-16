# 部署方案

## 1. 环境划分
| 环境 | 用途 | 域名 |
|---|---|---|
| dev | 本地 / 内网 | localhost |
| staging | 集成测试 | staging.smartqa.xxx |
| prod | 生产 | smartqa.xxx |

## 2. 本地开发
```bash
docker compose up -d postgres redis
make run-api
make run-ui
```

## 3. 单机部署（docker compose）
- 服务器：8C16G 起，建议独立 PG / Redis
- 启动：
  ```bash
  git clone <repo> && cd SmartQA
  cp .env.example .env  # 修改
  docker compose up -d
  ```
- 数据备份：`pg_dump` 每日一次；Redis 关闭持久化（仅缓存）

## 4. 集群部署（k8s，参考）
- `deploy/k8s/api-deployment.yaml`（3 副本 + HPA）
- `deploy/k8s/streamlit-deployment.yaml`
- `deploy/k8s/ingress.yaml`（Nginx Ingress）
- 外部依赖：托管 PG / Redis（云厂商）

## 5. 监控
- Langfuse：Trace、Token、延迟
- Prometheus + Grafana：CPU/内存/请求量（可选项）
- 告警：LLM 错误率 > 5% / p95 延迟 > 5s

## 6. 回滚
- 镜像 tag 化，每次部署带版本号
- 蓝绿或滚动更新，保留前一个版本至少 24h

## 7. 常见操作
| 操作 | 命令 |
|---|---|
| 查日志 | `docker logs -f smartqa-api` |
| 进容器 | `docker exec -it smartqa-api bash` |
| 备份 PG | `pg_dump -U smartqa smartqa > backup.sql` |
| 恢复 PG | `psql -U smartqa smartqa < backup.sql` |
