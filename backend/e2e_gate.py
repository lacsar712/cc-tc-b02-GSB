"""端到端验收：雨量闸全流程。用 SQLite 跑真实 WSGI 栈 + 真实后台认领线程。"""
import os
import sys
import time

DB_PATH = "/tmp/tunnelconv_e2e.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import app  # noqa: E402

client = app.test_client()

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {extra}")


def login(username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


surveyor = login("surveyor", "surv123456")
inspector = login("inspector", "insp123456")

# 1. 巡检员能看阈值和开闸记录
r = client.get("/api/gate", headers=auth(inspector))
body = r.get_json()
check("巡检员 GET /api/gate 200", r.status_code == 200)
check("初始闸为关", body["state"]["is_open"] is False)
check("初始阈值为空", body["state"]["threshold_mm"] is None)

# 2. 巡检员不能扳开关
r = client.post("/api/gate/open", headers=auth(inspector), json={"threshold_mm": 10})
check("巡检员开闸被 403", r.status_code == 403, str(r.status_code))
r = client.post("/api/gate/close", headers=auth(inspector))
check("巡检员关闸被 403", r.status_code == 403, str(r.status_code))

# 3. 阈值留空不许开闸
r = client.post("/api/gate/open", headers=auth(surveyor), json={})
check("缺字段开闸 400", r.status_code == 400, r.get_json().get("detail", ""))
r = client.post("/api/gate/open", headers=auth(surveyor), json={"threshold_mm": "   "})
check("空白阈值开闸 400", r.status_code == 400, r.get_json().get("detail", ""))
r = client.post("/api/gate/open", headers=auth(surveyor), json={"threshold_mm": "abc"})
check("非数字阈值开闸 400", r.status_code == 400, r.get_json().get("detail", ""))

# 4. 压到极低阈值开闸
r = client.post("/api/gate/open", headers=auth(surveyor), json={"threshold_mm": 0.1})
st = r.get_json()["state"]
check("极低阈值(0.1mm)开闸 200", r.status_code == 200 and st["is_open"] is True)
check("阈值落库为 0.1", st["threshold_mm"] == 0.1, str(st["threshold_mm"]))

# 5. 越界交单应失败（真实拒收：403 + 不入库 + 拒收流水同事务写入）
r = client.post(
    "/api/logs",
    headers=auth(surveyor),
    json={"chainage": "K20+050", "delta_mm": 1.2, "rainfall_mm": 5.0},
)
rej = r.get_json()
check("越界交单 403", r.status_code == 403, str(r.status_code))
check("403 回执带退回原因", bool(rej.get("detail")) and "退回" in rej["detail"], rej.get("detail", ""))

time.sleep(0.5)
r = client.get("/api/logs", headers=auth(surveyor))
chainages = [row["chainage"] for row in r.get_json()]
check("被退回的单没有进入报送列表（真实拒收）", "K20+050" not in chainages, str(chainages))

r = client.get("/api/gate", headers=auth(surveyor))
events = r.get_json()["events"]
rejects = [e for e in events if e["kind"] == "reject"]
check("拒收流水已写入", len(rejects) == 1)
if rejects:
    ev = rejects[0]
    check(
        "拒收流水带阈值/雨量/桩号/操作人",
        ev["threshold_mm"] == 0.1 and ev["rainfall_mm"] == 5.0
        and ev["chainage"] == "K20+050" and ev["actor"] == "surveyor",
        str(ev),
    )

# 6. 开闸期间不带雨量 -> 400（后台真实校验，不是前端做样子）
r = client.post("/api/logs", headers=auth(surveyor), json={"chainage": "K20+051", "delta_mm": 1.0})
check("开闸期间缺洞口雨量 400", r.status_code == 400, r.get_json().get("detail", ""))

# 7. 开闸期间界内单可正常进入并被认领
r = client.post(
    "/api/logs",
    headers=auth(surveyor),
    json={"chainage": "K20+052", "delta_mm": 1.1, "rainfall_mm": 0.05},
)
check("界内交单 201", r.status_code == 201, str(r.status_code))
new_id = r.get_json()["id"]

# 8. 关闸
time.sleep(0.2)
r = client.post("/api/gate/close", headers=auth(surveyor))
st = r.get_json()["state"]
check("关闸 200 且状态关闭", r.status_code == 200 and st["is_open"] is False)
check(
    "上次开闸持续时长已结算(秒, >=0)",
    st["last_open_seconds"] is not None and st["last_open_seconds"] >= 0,
    str(st["last_open_seconds"]),
)
r = client.get("/api/gate", headers=auth(inspector))
kinds = [e["kind"] for e in r.get_json()["events"]]
check("巡检员可见开/关闸/拒收流水", set(["open", "close", "reject"]).issubset(set(kinds)), str(kinds))

# 9. 关上闸后送原被退回的单（不带雨量也应成功）
r = client.post(
    "/api/logs",
    headers=auth(surveyor),
    json={"chainage": "K20+050", "delta_mm": 1.2},
)
check("关闸后原单重交 201", r.status_code == 201, str(r.status_code))

# 10. 等后台认领，两张界内单都应判完
deadline = time.time() + 8
done = set()
while time.time() < deadline:
    rows = client.get("/api/logs", headers=auth(surveyor)).get_json()
    done = {row["chainage"] for row in rows if row["status"] == "done"}
    if {"K20+050", "K20+052"}.issubset(done):
        break
    time.sleep(0.3)
check("两张界内单被后台认领判完", {"K20+050", "K20+052"}.issubset(done), str(sorted(done)))

# 11. 再开闸可改新阈值，且拒收流水与真实拒收始终成对
r = client.post("/api/gate/open", headers=auth(surveyor), json={"threshold_mm": 20})
check("重新开闸改阈值 20mm", r.status_code == 200)
r = client.post(
    "/api/logs",
    headers=auth(surveyor),
    json={"chainage": "K20+060", "delta_mm": 9.0, "rainfall_mm": 25},
)
check("新阈值下越界仍 403", r.status_code == 403, str(r.status_code))
rows = client.get("/api/logs", headers=auth(surveyor)).get_json()
check("新拒收单同样未入库", all(row["chainage"] != "K20+060" for row in rows))
evs = client.get("/api/gate", headers=auth(surveyor)).get_json()["events"]
check("拒收流水累计 2 条", len([e for e in evs if e["kind"] == "reject"]) == 2)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
