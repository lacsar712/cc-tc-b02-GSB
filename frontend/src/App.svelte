<script>
  let session = null;
  let logs = [];
  let gate = null;
  let journal = [];
  let view = "logs";
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let threshold = ""; // 仅用于“开闸”时提交给后端，不作为当前阈值的展示来源
  let error = "";
  let gateError = "";
  let loading = false;
  let gateBusy = false;
  let timer;

  $: isWriter = session?.role === "writer";

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refreshJournal() {
    if (!session) return;
    const res = await fetch("/api/rain-gate/journal", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) journal = await res.json();
  }

  async function refresh() {
    if (!session) return;
    const [lr, gr] = await Promise.all([
      fetch("/api/logs", { headers: headers() }),
      fetch("/api/rain-gate", { headers: headers() }),
    ]);
    if (lr.status === 401 || gr.status === 401) {
      logout();
      return;
    }
    if (lr.ok) logs = await lr.json();
    if (gr.ok) gate = await gr.json();
    if (view === "gate") await refreshJournal();
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
      await refresh();
      timer = setInterval(refresh, 2000);
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
    journal = [];
    view = "logs";
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  async function openGate() {
    gateError = "";
    const raw = threshold.trim();
    if (!raw) {
      gateError = "雨量阈值不能为空，留空不许开闸";
      return;
    }
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0) {
      gateError = "雨量阈值必须是大于 0 的数字";
      return;
    }
    gateBusy = true;
    try {
      const res = await fetch("/api/rain-gate/open", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ rain_limit_mm: value }),
      });
      const data = await res.json();
      if (!res.ok) {
        gateError = data.detail || "开闸失败";
        return;
      }
      threshold = "";
      await refresh();
    } catch {
      gateError = "开闸时网络异常";
    } finally {
      gateBusy = false;
    }
  }

  async function closeGate() {
    gateError = "";
    gateBusy = true;
    try {
      const res = await fetch("/api/rain-gate/close", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: "{}",
      });
      const data = await res.json();
      if (!res.ok) {
        gateError = data.detail || "关闸失败";
        return;
      }
      await refresh();
    } catch {
      gateError = "关闸时网络异常";
    } finally {
      gateBusy = false;
    }
  }

  function go(v) {
    view = v;
    gateError = "";
    if (v === "gate") refreshJournal();
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  function fmtDuration(sec) {
    if (sec === null || sec === undefined) return "尚无记录";
    if (sec < 60) return `${Number(sec).toFixed(1)} 秒`;
    const total = Math.round(sec);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return `${h} 时 ${m} 分 ${s} 秒`;
    return `${m} 分 ${s} 秒`;
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
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
  .topbar {
    max-width: 960px; margin: 0 auto; padding: 1rem 1.5rem 0;
    display: flex; align-items: center; gap: 1.25rem;
  }
  .brand { color: #fbbf24; font-weight: 700; font-size: 1.15rem; text-decoration: none; cursor: pointer; }
  nav { display: flex; gap: 0.75rem; margin-left: auto; }
  nav a {
    color: #d6d3d1; text-decoration: none; font-size: 0.9rem; cursor: pointer;
    padding: 0.25rem 0.6rem; border-radius: 6px; border: 1px solid #44403c;
  }
  nav a.active { color: #fbbf24; border-color: #d97706; }
  .dot { display: inline-block; width: 0.55rem; height: 0.55rem; border-radius: 50%; margin-left: 0.3rem; }
  .dot-open { background: #fb7185; box-shadow: 0 0 6px #fb7185; }
  .dot-closed { background: #57534e; }
  h1 { color: #fbbf24; margin: 0 0 0.25rem; font-size: 1.35rem; }
  h2 { font-size: 1rem; margin: 0 0 0.75rem; color: #fbbf24; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  .inline-row { display: flex; gap: 0.6rem; align-items: flex-start; }
  .inline-row input { margin-bottom: 0; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600; white-space: nowrap;
  }
  button.danger { background: #b91c1c; }
  button.secondary { background: #57534e; }
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  .err { color: #fb7185; }
  .hint { color: #a8a29e; font-size: 0.85rem; line-height: 1.6; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .gate-open { background: #7f1d1d; color: #fca5a5; }
  .gate-closed { background: #44403c; color: #d6d3d1; }
  .ev-open { background: #713f12; color: #fde68a; }
  .ev-close { background: #1e3a5f; color: #bfdbfe; }
  .ev-reject { background: #7f1d1d; color: #fca5a5; }
  ul.notes { margin: 0; padding-left: 1.2rem; color: #d6d3d1; font-size: 0.9rem; line-height: 1.8; }
  .metric { font-size: 1.6rem; font-weight: 700; color: #fafaf9; }
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
    <div class="topbar">
      <a class="brand" on:click={() => go("logs")}>隧道收敛测缝台</a>
      <nav>
        <a class:active={view === "logs"} on:click={() => go("logs")}>报送列表</a>
        <a class:active={view === "gate"} on:click={() => go("gate")}>
          雨量闸
          {#if gate}
            <span class="dot {gate.is_open ? 'dot-open' : 'dot-closed'}"></span>
          {/if}
        </a>
      </nav>
    </div>

    {#if view === "gate"}
      <section>
        <h2>阈值</h2>
        {#if gate?.is_open}
          <p>
            当前状态：<span class="tag gate-open">闸已开启 · 报送一键停报</span>
          </p>
          <p class="metric">雨量上限 {gate.rain_limit_mm} mm</p>
          <p class="hint">
            开闸人：{gate.opened_by ?? "—"}　开启时间：{fmtTime(gate.opened_at)}<br />
            闸开期间，收敛读数绝对值超过该上限的报送将被后端整份退回，不进入待判列表。
          </p>
          {#if isWriter}
            <button class="danger" disabled={gateBusy} on:click={closeGate}>关闸（恢复收单）</button>
          {:else}
            <p class="hint">巡检员只读：可查看阈值与开闸记录，不能扳动开关。</p>
          {/if}
        {:else}
          <p>
            当前状态：<span class="tag gate-closed">闸已关闭</span>
            　报送正常受理，后台按 ±3.0 mm 判定。
          </p>
          {#if isWriter}
            <label>开闸雨量上限（mm，必填，留空不许开闸）</label>
            <div class="inline-row">
              <input
                type="number"
                min="0"
                step="0.1"
                placeholder="例如 2.5"
                bind:value={threshold}
                on:keydown={(e) => e.key === "Enter" && openGate()}
              />
              <button disabled={gateBusy} on:click={openGate}>开闸并写入上限</button>
            </div>
          {:else}
            <p class="hint">巡检员只读：可查看阈值与开闸记录，不能扳动开关。</p>
          {/if}
        {/if}
        {#if gateError}<p class="err">{gateError}</p>{/if}
      </section>

      <section>
        <h2>上次开闸持续时长</h2>
        <p class="metric">{fmtDuration(gate?.last_open_duration_seconds)}</p>
        <p class="hint">取最近一次关闸流水回写的本次开闸持续时间；尚未关过闸时显示“尚无记录”。</p>
      </section>

      <section>
        <h2>流水</h2>
        <table>
          <thead>
            <tr><th>时间</th><th>类型</th><th>操作人</th><th>详情</th><th>持续时长</th></tr>
          </thead>
          <tbody>
            {#each journal as item}
              <tr>
                <td>{fmtTime(item.created_at)}</td>
                <td>
                  {#if item.kind === "rejection"}
                    <span class="tag ev-reject">越界退回</span>
                  {:else if item.action === "open"}
                    <span class="tag ev-open">开闸</span>
                  {:else}
                    <span class="tag ev-close">关闸</span>
                  {/if}
                </td>
                <td>{item.operator ?? "—"}</td>
                <td>
                  {#if item.kind === "rejection"}
                    桩号 {item.chainage}，读数 {item.delta_mm} mm ＞ 上限 {item.rain_limit_mm} mm；{item.reason}
                  {:else if item.action === "open"}
                    写入雨量上限 {item.rain_limit_mm} mm
                  {:else}
                    本次开闸上限 {item.rain_limit_mm ?? "—"} mm，已关闸
                  {/if}
                </td>
                <td>
                  {#if item.kind === "gate" && item.action === "close"}
                    {fmtDuration(item.duration_seconds)}
                  {:else}—{/if}
                </td>
              </tr>
            {/each}
            {#if journal.length === 0}
              <tr><td colspan="5" class="hint">暂无开闸、关闸或退回流水。</td></tr>
            {/if}
          </tbody>
        </table>
      </section>

      <section>
        <h2>说明</h2>
        <ul class="notes">
          <li>洞口雨量站拉响告警后，测量员在本页填写雨量上限并开闸，整工区测缝报送一键停报。</li>
          <li>阈值留空不许开闸；阈值只能由测量员在本页写入后端，以前端本地值冒充服务端阈值无效。</li>
          <li>闸开期间，后台收到绝对收敛值超过雨量上限的单子会整份退回（交单直接失败），不会进入待判列表。</li>
          <li>每一次真实拒收都会与退回流水在同一事务落库；只改页面开关、后台仍收单或流水与拒收不一致均视为未生效。</li>
          <li>关闸后新单不再拦截，恢复正常受理与判定。</li>
          <li>巡检员可查看阈值与开闸、关闸、退回记录，但不能扳动开关。</li>
        </ul>
      </section>
    {:else}
      <p class="sub">已登录：{session.username}（{isWriter ? "可提交" : "只读"}）</p>
      <section>
        <button class="secondary" on:click={logout}>退出</button>
        <button class="secondary" disabled={loading} on:click={refresh}>刷新列表</button>
        {#if gate?.is_open}
          <a on:click={() => go("gate")} style="color:#fca5a5;cursor:pointer;margin-left:0.5rem;">
            雨量闸开启中（上限 {gate.rain_limit_mm} mm），越界报送会被退回 →
          </a>
        {/if}
      </section>
      {#if isWriter}
        <section>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
        </section>
      {/if}
      <section>
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
    {/if}
  {/if}
</main>
