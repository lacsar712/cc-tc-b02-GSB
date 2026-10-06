# 隧道收敛测缝台

测量员登记里程桩号与收敛毫米值。接口进程内后台线程认领待判行（不另起 worker 容器），按绝对值是否不超过 3.0 mm 给出合格或超限。页面是 Svelte。

## 技术栈

- 后端：Flask、Gunicorn、SQLAlchemy、进程内认领线程
- 前端：Svelte、Vite、nginx 反代 `/api`
- 数据库：PostgreSQL 16

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3201 |
| 接口 | http://localhost:8201 |
| PostgreSQL | localhost:54401（库名 `tunnelconv`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| surveyor | surv123456 | 可提交 |
| inspector | insp123456 | 只读 |

## 启动

```bash
cd projects/21-tunnel-convergence-desk
docker compose up --build
```

健康检查：`GET http://localhost:8201/api/health`

## 种子

| 桩号 | 收敛 | 结论 |
|------|------|------|
| K12+180 | 1.2 mm | 合格 |
| K18+040 | 5.6 mm | 超限 |

## 雨量闸（洞口雨量站停报）

页眉「雨量闸」进入专页，分四块：**阈值、上次开闸持续时长、流水、说明**。

- 测量员（surveyor）写下雨量上限后**开闸**：阈值留空不许开闸（后台 400 强制，非前端做样子）。
- 开闸期间每份报送必须随附**洞口雨量**；后台采到雨量超过上限，整份报送**真实退回**（HTTP 403，不入库、不进待判），并在**同一事务**写入一条「越界拒收」流水。
- **关闸**后新单不再拦截；关闸结算上次开闸持续时长。
- 巡检员（inspector）可看阈值与开闸/拒收流水，不能扳开关（写接口 403）。

接口：`GET /api/gate`、`POST /api/gate/open`（body `threshold_mm`）、`POST /api/gate/close`。
交单 `POST /api/logs` 开闸期间需带 `rainfall_mm`。

无 Docker/Postgres 时可用 SQLite 跑端到端验收：

```bash
DATABASE_URL=sqlite:////tmp/t.db python backend/e2e_gate.py
```
