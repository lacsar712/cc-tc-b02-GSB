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

## 雨量闸

洞口雨量站告警后，测量员从页眉「雨量闸」进专页（阈值 / 上次开闸持续时长 / 流水 / 说明四块），填写雨量上限并开闸，整工区测缝报送一键停报：

- 阈值留空不许开闸；阈值只由测量员写入后端，前端本地值不生效。
- 闸开期间，`POST /api/logs` 在后端校验：收敛绝对值超过雨量上限的单子**整份退回**（HTTP 422），不进入待判列表；退回流水与真实拒收在同一事务写入 `rain_gate_rejections`。
- 关闸后新单不再拦截。开/关闸写入 `rain_gate_events`，关闸回写本次持续时长。
- 巡检员（只读）可查看阈值与全部流水，开闸/关闸接口返回 403。

| 接口 | 权限 | 说明 |
|------|------|------|
| `GET /api/rain-gate` | 登录 | 闸状态、当前阈值、上次开闸持续秒数 |
| `POST /api/rain-gate/open` | 测量员 | body `{"rain_limit_mm": 2.5}`，空值/非正数 400 |
| `POST /api/rain-gate/close` | 测量员 | 关闸并回写持续时长 |
| `GET /api/rain-gate/journal` | 登录 | 开/关闸与越界退回合并流水 |

