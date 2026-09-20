# FASTQ 质控流水线台（FASTQ QC Pipeline Console）

从零实现的全栈演示：上传/选择小型 FASTQ → **Actor 队列流水线**质控 → 查看阶段状态与指标。
支持**双端配对质控**：R1/R2 两条读段一次送进流水线，各自独立跑 Actor 链，左右分栏对照指标与失败阶段。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL |
| 流水线 | `ParseActor` → `QualityHistActor` → `NContentActor` → `ReportActor`（asyncio.Queue），配对作业双侧并发各跑一条链 |
| 前端 | Vue 3 · Vite · Quasar · 中文 UI · nginx `/api` 反代 |
| 基建 | docker compose（db / backend / seed / frontend） |

## 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3184 |
| Backend API | http://localhost:8184 |
| PostgreSQL | localhost:54384 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| `bioops` | `fastq123456` | 可提交单端/配对质控作业 |
| `auditor` | `audit123456` | 只读结果，不可提交 |

## 一键启动

```bash
cd projects/09-fastq-qc-pipeline
docker compose up --build
```

镜像源：Postgres/Node/Nginx 使用 `docker.m.daocloud.io`；npm 使用 `registry.npmmirror.com`；pip 使用清华源。

启动后 seed 会写入：

- `demo-good-r1`：合格样例（可算出 `mean_quality` / `n_rate`）
- `demo-broken-malformed`：损坏样例（`ParseActor` 失败，后续阶段 skipped）

## 双端配对质控

- 导航栏「配对质控」进入：每侧可各选一条 seed 样例，或各贴一段 FASTQ 文本（选样例优先）。
- 服务端生成一条配对记录（`pair_jobs`），R1/R2 两侧**各自独立**执行 Actor 链（`asyncio.gather` 并发，队列与上下文互不影响）。
- 详情页左右分栏对照：每侧展示指标卡（`reads` / `mean_quality` / `n_rate`）与四个 Actor 阶段状态；失败侧红框标注「失败侧」并给出失败原因。
- 一侧解析失败时另一侧结果完整保留：整体状态 = `success`（双侧成功）/ `partial`（单侧失败）/ `failed`（双侧失败）。
- 权限：运维（bioops）可开跑，审计员（auditor）只读（POST 返回 403，前端无提交入口）。

## Verification（验收）

1. 打开 http://localhost:3184 ，用 `bioops` / `fastq123456` 登录。
2. **样例库** 看到 2 条样例 → 选合格样例 **提交质控作业**。
3. 作业详情页看到四个 Actor 阶段均为成功，指标卡出现 `reads` / `mean_quality` / `n_rate`。
4. 再跑损坏样例：`ParseActor` = failed，其余 = skipped。
5. **配对验收口令**：导航进「配对质控」→ 新建配对作业 → R1 选 `demo-good-r1`、R2 选 `demo-broken-malformed`（或反向）→ 启动。详情页整体状态为「部分成功」，合格侧四阶段全绿且指标保留，损坏侧标「失败侧」且 `ParseActor` = failed、其余 skipped —— 成败可区分。
6. 退出，用 `auditor` / `audit123456` 登录：可看历史与详情（含配对），提交作业接口返回 403 / 前端无提交入口。
7. 健康检查：`curl http://localhost:8184/api/health`

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`
- `GET  /api/jobs`
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/stages`
- `POST /api/pairs` `{ "r1": { "sampleId": 1 }, "r2": { "fastqText": "..." } }`（每侧 sampleId / fastqText 二选一）
- `GET  /api/pairs`
- `GET  /api/pairs/{id}`
- `GET  /api/pairs/{id}/stages`

## 本地单测（可选）

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

覆盖：畸形 FASTQ 在 `ParseActor` 失败；正常样例产出 `mean_quality`；配对链路「合格 + 损坏」时好侧指标保留、坏侧标明失败阶段、整体 `partial`；审计员提交配对返回 403（API 级，SQLite 兜底，无需 Postgres）。

## 目录结构

```
09-fastq-qc-pipeline/
  PRD.md
  README.md
  docker-compose.yml
  backend/
    Dockerfile
    seed.py
    data/{good,broken}.fastq
    app/
      main.py api.py auth.py models.py schemas.py
      pipeline/{actors,runner}.py
    tests/{test_actors,test_pair,test_pair_api}.py
  frontend/
    Dockerfile nginx.conf
    src/pages/{Login,Samples,JobSubmit,JobDetail,JobHistory,PairSubmit,PairHistory,PairDetail}Page.vue
```
