<script>
  let session = null;
  let logs = [];
  let gate = null; // { state, events }
  let view = "desk"; // desk | gate
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let rainfallMm = "";
  let thresholdInput = "";
  let error = "";
  let gateError = "";
  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";
  $: gateOpen = gate?.state?.is_open === true;

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", { hour12: false });
  }

  function fmtDuration(sec) {
    if (sec === null || sec === undefined) return "暂无（尚未完成过一次开闸）";
    if (sec < 60) return `${Math.round(sec)} 秒`;
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${m} 分 ${s} 秒（共 ${Math.round(sec)} 秒）`;
  }

  async function refreshLogs() {
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
  }

  async function refreshGate() {
    const res = await fetch("/api/gate", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) gate = await res.json();
  }

  async function refreshAll() {
    if (!session) return;
    await Promise.all([refreshLogs(), refreshGate()]);
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refreshAll();
      timer = setInterval(refreshAll, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    gate = null;
    view = "desk";
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const payload = { chainage, delta_mm: Number(deltaMm) };
      if (rainfallMm.trim() !== "") payload.rainfall_mm = Number(rainfallMm);
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        error = gateOpen && res.status === 403
          ? `雨量闸退回：${data.detail || "洞口雨量越界，整份报送已退回"}`
          : data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      rainfallMm = "";
      await refreshLogs();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  async function openGate() {
    gateError = "";
    // 阈值留空不许开闸（后台同样强制，前端不能只做个样子）
    if (thresholdInput.trim() === "") {
      gateError = "雨量上限不能为空：阈值留空着不许开闸";
      return;
    }
    const value = Number(thresholdInput);
    if (!Number.isFinite(value) || value < 0) {
      gateError = "雨量上限必须是不小于 0 的数字";
      return;
    }
    try {
      const res = await fetch("/api/gate/open", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ threshold_mm: value }),
      });
      const data = await res.json();
      if (!res.ok) {
        gateError = data.detail || "开闸失败";
        return;
      }
      thresholdInput = "";
      await refreshGate();
    } catch {
      gateError = "开闸时网络异常";
    }
  }

  async function closeGate() {
    gateError = "";
    try {
      const res = await fetch("/api/gate/close", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
      });
      const data = await res.json();
      if (!res.ok) {
        gateError = data.detail || "关闸失败";
        return;
      }
      await refreshGate();
    } catch {
      gateError = "关闸时网络异常";
    }
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refreshAll();
      timer = setInterval(refreshAll, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 960px; margin: 0 auto; padding: 1.5rem; }
  .pagemast {
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; flex-wrap: wrap;
  }
  h1 { color: #fbbf24; margin: 0; font-size: 1.4rem; }
  nav { display: flex; gap: 0.5rem; }
  nav a {
    cursor: pointer; color: #fbbf24; text-decoration: none;
    border: 1px solid #57534e; border-radius: 6px; padding: 0.35rem 0.8rem;
    font-size: 0.9rem; background: #292524;
  }
  nav a.active { background: #d97706; color: #fff; border-color: #d97706; }
  .sub { color: #a8a29e; margin: 0.25rem 0 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  h2 { font-size: 1.05rem; margin: 0 0 0.75rem; color: #fde68a; }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  .row { display: flex; gap: 0.75rem; align-items: flex-end; flex-wrap: wrap; }
  .row > div { flex: 1; min-width: 180px; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.danger { background: #b91c1c; }
  button.secondary { background: #57534e; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .err { color: #fb7185; }
  .gatebanner {
    background: #450a0a; border: 1px solid #b91c1c; color: #fecaca;
    border-radius: 8px; padding: 0.7rem 1rem; margin-bottom: 1rem; font-size: 0.92rem;
  }
  .kv { display: grid; grid-template-columns: 9.5rem 1fr; gap: 0.35rem 0.75rem; font-size: 0.92rem; }
  .kv .k { color: #a8a29e; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .open { background: #7f1d1d; color: #fecaca; }
  .closed { background: #14532d; color: #86efac; }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  .note { color: #d6d3d1; font-size: 0.9rem; line-height: 1.7; margin: 0; }
  .note b { color: #fde68a; }
  .readonly-hint { color: #a8a29e; font-size: 0.85rem; }
</style>

<main>
  {#if !session}
    <h1>隧道收敛测缝台</h1>
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <div class="pagemast">
      <h1>隧道收敛测缝台</h1>
      <nav>
        <a class:active={view === "desk"} on:click={() => (view = "desk")}>测缝报送</a>
        <a class:active={view === "gate"} on:click={() => (view = "gate")}>雨量闸</a>
        <a on:click={logout}>退出</a>
      </nav>
    </div>
    <p class="sub">已登录：{session.username}（{isWriter ? "可提交 / 可扳雨量闸" : "巡检员只读"}）</p>

    {#if view === "desk"}
      {#if gateOpen}
        <div class="gatebanner">
          雨量闸已开启（洞口雨量上限 {gate.state.threshold_mm} mm，开闸人 {gate.state.opened_by}）：
          交单须填洞口雨量，后台采到越界将把整份报送退回，本单不会进入待判列表。
        </div>
      {/if}
      <section>
        <button class="secondary" disabled={loading} on:click={refreshAll}>刷新列表</button>
      </section>
      {#if isWriter}
        <section>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <div class="row">
            <div>
              <label>收敛（毫米，可正可负）</label>
              <input type="number" step="0.1" bind:value={deltaMm} />
            </div>
            <div>
              <label>洞口雨量（毫米）{gateOpen ? "· 开闸期间必填" : "· 关闸时可不填"}</label>
              <input type="number" step="0.1" min="0" bind:value={rainfallMm} />
            </div>
          </div>
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
        </section>
      {/if}
      <section>
        <h2>测缝报送流水</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td>{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <!-- 雨量闸专页：阈值 / 上次开闸持续时长 / 流水 / 说明 四块 -->
      <section>
        <h2>① 阈值（洞口雨量上限）</h2>
        {#if gate?.state}
          <div class="kv">
            <span class="k">当前雨量上限</span>
            <span>{gate.state.threshold_mm === null || gate.state.threshold_mm === undefined ? "未设置" : gate.state.threshold_mm + " mm"}</span>
            <span class="k">闸状态</span>
            <span>
              <span class="tag {gate.state.is_open ? 'open' : 'closed'}">{gate.state.is_open ? "开闸中：新单受检" : "关闸：新单不拦"}</span>
            </span>
            <span class="k">开闸人</span><span>{gate.state.opened_by ?? "—"}</span>
            <span class="k">本次开闸时间</span><span>{fmtTime(gate.state.opened_at)}</span>
          </div>
          {#if isWriter}
            <div class="row" style="margin-top:0.85rem">
              <div>
                <label>写雨量上限后开闸（留空不许开闸）</label>
                <input type="number" step="0.1" min="0" placeholder="例如 10" bind:value={thresholdInput} />
              </div>
              <div style="flex:0">
                {#if gate.state.is_open}
                  <button class="danger" on:click={closeGate}>关闸（新单不再拦）</button>
                {:else}
                  <button on:click={openGate} disabled={thresholdInput.trim() === ""}>开闸</button>
                {/if}
              </div>
            </div>
            {#if gateError}<p class="err">{gateError}</p>{/if}
          {:else}
            <p class="readonly-hint" style="margin-bottom:0">巡检员可查看阈值与开闸记录，不能扳动开关。</p>
          {/if}
        {/if}
      </section>

      <section>
        <h2>② 上次开闸持续时长</h2>
        {#if gate?.state}
          <div class="kv">
            <span class="k">上次开闸</span><span>{fmtTime(gate.state.opened_at)}</span>
            <span class="k">上次关闸</span><span>{fmtTime(gate.state.closed_at)}</span>
            <span class="k">持续时长</span>
            <span>
              {#if gate.state.is_open}
                开闸进行中，关闸后结算时长
              {:else}
                {fmtDuration(gate.state.last_open_seconds)}
              {/if}
            </span>
          </div>
        {/if}
      </section>

      <section>
        <h2>③ 流水（开闸 / 关闸 / 越界拒收）</h2>
        <table>
          <thead>
            <tr><th>时间</th><th>类型</th><th>操作人</th><th>阈值mm</th><th>洞口雨量mm</th><th>桩号</th><th>说明</th></tr>
          </thead>
          <tbody>
            {#each gate?.events ?? [] as ev}
              <tr>
                <td>{fmtTime(ev.created_at)}</td>
                <td><span class="tag {ev.kind === 'reject' ? 'bad' : (ev.kind === 'open' ? 'open' : 'closed')}">{ev.kind_cn}</span></td>
                <td>{ev.actor}</td>
                <td>{ev.threshold_mm ?? "—"}</td>
                <td>{ev.rainfall_mm ?? "—"}</td>
                <td>{ev.chainage ?? "—"}</td>
                <td>{ev.detail}</td>
              </tr>
            {/each}
            {#if (gate?.events ?? []).length === 0}
              <tr><td colspan="7" class="readonly-hint">暂无流水。</td></tr>
            {/if}
          </tbody>
        </table>
      </section>

      <section>
        <h2>④ 说明</h2>
        <p class="note">
          <b>用途：</b>洞口雨量站拉响后，整工区测缝报送可一键停报——测量员在此页写下雨量上限并开闸。<br />
          <b>开闸期间：</b>每份报送必须随附洞口雨量；后台采到雨量超过上限，就把整份报送退回（HTTP 403），该单不入库、不进入待判，同时在本页流水写入一条「越界拒收」。退回流水与真实拒收在后台同一事务写入，缺一不可。<br />
          <b>关闸后：</b>新单不再拦截，可正常提交。<br />
          <b>权限：</b>仅测量员（surveyor）能开闸 / 关闸；巡检员（inspector）只能查看阈值与开闸记录。<br />
          <b>校验：</b>阈值留空不许开闸（后台强制，前端按钮也会置灰），阈值以后台落库值为准。
        </p>
      </section>
    {/if}
  {/if}
</main>
