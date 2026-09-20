# FASTQ 质控流水线台（FASTQ QC Pipeline Console）

从零实现的全栈演示：上传/选择小型 FASTQ → **Actor 队列流水线**质控 → 查看阶段状态与指标；
并提供 **双端配对质控子系统**：把 R1 / R2 两条读段一次送进流水线对照。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL |
| 流水线 | `ParseActor` → `QualityHistActor` → `NContentActor` → `ReportActor`（asyncio.Queue） |
| 配对 | 一个 `pair_runs` 记录挂两条 Job，R1/R2 两条 Actor 链 `asyncio.gather` 并发，单侧失败互不影响 |
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
| `bioops` | `fastq123456` | 可提交单端 / 双端配对质控作业 |
| `auditor` | `audit123456` | 只读结果，不可提交（提交接口 403、前端无提交入口） |

## 一键启动

```bash
docker compose up --build
```

镜像源：Postgres/Node/Nginx 使用 `docker.m.daocloud.io`；npm 使用 `registry.npmmirror.com`；pip 使用清华源。

启动后 seed 会写入（按名称幂等，重复启动自动补齐新样例）：

- `demo-good-r1`：合格样例（可算 `mean_quality` / `n_rate`），可作 R1
- `demo-good-r2`：合格样例，可作 R2
- `demo-broken-malformed`：损坏样例（`ParseActor` 失败，后续阶段 skipped）

> 旧版 `pgdata` 卷可直接复用：应用启动时会自动给 `jobs` 表补齐 `pair_id / pair_side / pair_side_order` 列。

## 双端配对质控

- 导航 **双端配对** → **新建配对**（仅运维可见提交入口，审计员只读）。
- R1 / R2 各支持「选一条样例」或「粘贴一段 FASTQ 文本」，一次提交。
- 服务端生成 `pair_runs` 配对记录并挂两条 Job，两侧分别执行同一条 Actor 链。
- 详情页 **左右分栏**：各自的指标卡（reads / mean_quality / n_rate）、Actor 阶段成败，
  顶栏标明 **失败侧（R1 / R2 / 两侧）**。
- **一侧解析失败时另一侧结果仍保留**：
  - 两侧皆成功 → `success`
  - 恰好一侧失败 → `partial`，`failed_side` 为 `r1` 或 `r2`
  - 两侧皆失败 → `failed`，`failed_side=both`

## Verification（验收）

1. 打开 http://localhost:3184 ，用 `bioops` / `fastq123456` 登录。
2. **样例库** 看到 3 条样例 → 选合格样例 **提交质控作业**。
3. 作业详情页看到四个 Actor 阶段均为成功，指标卡出现 `reads` / `mean_quality` / `n_rate`。
4. 再跑损坏样例：`ParseActor` = failed，其余 = skipped。
5. 进入 **双端配对 → 新建配对**：
   - **合格配损坏各一侧**（R1 选 `demo-good-r1`、R2 选 `demo-broken-malformed`，再交换一次）。
   - 详情页左右分栏：合格侧四阶段成功且指标完整；损坏侧 `ParseActor` 失败、其余 skipped；
     顶栏分别标明失败侧 R2 / R1，配对状态为「单侧失败」。
   - **验收口令：合格配损坏各一侧后能区分成败。**
6. 退出，用 `auditor` / `audit123456` 登录：可看单端历史、配对记录与详情，
   提交类接口返回 403 / 前端无提交入口。
7. 健康检查：`curl http://localhost:8184/api/health`

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`
- `GET  /api/jobs`（仅单端作业，不含配对子作业）
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/stages`
- `POST /api/pair-runs` `{ "r1": {"sampleId": 1}|{"fastqText": "..."}, "r2": {...} }`（仅运维）
- `GET  /api/pair-runs`
- `GET  /api/pair-runs/{id}`（含 `r1` / `r2` 两侧状态、指标、阶段、`failed_side`）

## 本地单测（可选）

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

覆盖：畸形 FASTQ 在 `ParseActor` 失败；正常样例产出 `mean_quality`；
两条配对链并发相互独立（一侧损坏、另一侧指标保留）；配对状态 `success/partial/failed` 推导。

## 目录结构

```
fastq-qc-pipeline/
  README.md
  docker-compose.yml
  backend/
    Dockerfile seed.py
    data/{good,good_r2,broken}.fastq
    app/
      main.py api.py auth.py models.py schemas.py config.py database.py
      pipeline/{actors,runner}.py
    tests/test_actors.py
  frontend/
    Dockerfile nginx.conf
    src/pages/
      {Login,Samples,JobSubmit,JobDetail,JobHistory}Page.vue
      {PairSubmit,PairDetail,PairHistory}Page.vue
```
