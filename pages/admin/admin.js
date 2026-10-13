(() => {
    "use strict";
    const $ = (id) => document.getElementById(id);
    const state = { table: "messages", page: 1, pageSize: 50, query: "", tables: [], generation: 0 };
    const labels = { row_id: "记录编号", email: "邮箱", username: "账号", create_time: "创建时间", expire_time: "过期时间", time: "时间", ip: "IP 地址", user: "账号", path: "访问路径", method: "方法", status: "状态", question: "问题", "record.answer": "回答内容", "record.model": "模型", "record.status": "生成状态", key: "键", value: "值", "record.username": "昵称", "record.content": "留言内容", "record.ip": "IP 地址", "record.create_time_str": "留言时间", record: "数据", password: "密码", session_id: "会话令牌" };
    const displayColumns = { messages: ["row_id", "record.username", "record.content", "record.ip", "record.create_time_str"], visits: ["row_id", "time", "ip", "user", "method", "path", "status"], users: ["username", "email", "password"], sessions: ["email", "expire_time", "session_id"], ai_questions: ["row_id", "time", "user", "ip", "record.model", "question", "record.answer", "record.status"] };
    const number = (value) => Number(value).toLocaleString("zh-CN");
    function element(tag, text) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; }
    function showAlert(text) { $("adminAlert").textContent = text; $("adminAlert").hidden = !text; }
    function clearPrivateData() {
        $("dataBody").replaceChildren(); $("recordDetail").textContent = "";
        if ($("recordDialog").open) $("recordDialog").close();
        $("tableList").replaceChildren(); $("schemaPanel").replaceChildren();
        for (const id of ["totalRecords", "messageCount", "userCount", "visitCount", "ipSummary", "rowCount", "pageLabel"]) $(id).textContent = "—";
        $("previousPage").disabled = $("nextPage").disabled = true;
    }
    async function request(path) {
        const session = localStorage.getItem("session_id");
        const response = await fetch(path, { credentials: "include", cache: "no-store", headers: session ? { Authorization: `Session ${session}` } : {} });
        if (response.status === 401 || response.status === 403) {
            clearPrivateData(); $("loginLink").hidden = false;
            throw new Error(response.status === 401 ? "登录已过期，请重新登录 hyper 账号。" : "当前账号没有管理后台权限。");
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "读取失败，请重试。");
        return data;
    }
    function renderSidebar() {
        $("tableList").replaceChildren(...state.tables.map((table) => {
            const button = element("button"); button.type = "button";
            button.setAttribute("aria-current", String(table.name === state.table));
            button.append(element("span", table.label), element("small", number(table.count)));
            button.addEventListener("click", () => { state.table = table.name; state.page = 1; state.query = ""; $("searchInput").value = ""; renderSidebar(); loadRows(); });
            return button;
        }));
    }
    async function loadOverview() {
        const data = await request("/api/admin/tables");
        state.tables = data.tables;
        const count = (name) => state.tables.find((table) => table.name === name)?.count || 0;
        $("totalRecords").textContent = number(state.tables.reduce((sum, table) => sum + table.count, 0));
        $("messageCount").textContent = number(count("messages"));
        $("userCount").textContent = number(count("users")); $("visitCount").textContent = number(count("visits"));
        const ips = data.message_ips;
        $("ipSummary").textContent = `IP 已记录 ${ips.recorded} · 已补回 ${ips.backfilled} · 未知 ${ips.total - ips.recorded}`;
        renderSidebar();
    }
    function renderSchema() {
        const table = state.tables.find((item) => item.name === state.table);
        const node = element("table"); const head = element("thead"), header = element("tr");
        for (const label of ["字段", "类型", "主键", "允许空值"]) header.append(element("th", label));
        head.append(header); node.append(head);
        const body = element("tbody");
        for (const field of table?.schema || []) {
            const row = element("tr");
            for (const value of [field.name, field.type, field.pk ? "是" : "否", field.notnull || field.pk ? "否" : "是"]) row.append(element("td", value));
            body.append(row);
        }
        node.append(body); $("schemaPanel").replaceChildren(node);
    }
    function format(row, key) {
        let value = key.split(".").reduce((obj, part) => obj?.[part], row);
        if (key === "record.answer" && value === undefined) return "旧记录未保存回答";
        if (key === "record.status") value = ({ pending: "等待生成", streaming: "生成中", completed: "已完成", interrupted: "已中断", error: "失败", question_only: "仅提问" })[value] || value;
        if (value === null || value === undefined || value === "") return key.endsWith("ip") ? "未记录" : "—";
        if (["create_time", "expire_time"].includes(key)) return new Date(Number(value) * 1000).toLocaleString("zh-CN", { hour12: false });
        return typeof value === "object" ? JSON.stringify(value) : String(value);
    }
    function renderRows(data) {
        const columns = displayColumns[data.table] || data.columns;
        const header = element("tr"); for (const key of columns) header.append(element("th", labels[key] || key));
        header.append(element("th", "详情")); $("dataHead").replaceChildren(header);
        $("dataBody").replaceChildren(...data.rows.map((record) => {
            const row = element("tr");
            for (const key of columns) { const td = element("td"), cell = element("span", format(record, key)); cell.className = "cell"; td.dataset.key = key; td.append(cell); row.append(td); }
            const td = element("td"), button = element("button", "查看记录 ↗"); button.type = "button";
            button.addEventListener("click", () => { $("recordDetail").textContent = JSON.stringify(record, null, 2); $("recordDialog").showModal(); });
            td.append(button); row.append(td); return row;
        }));
        $("tableTitle").textContent = data.label; $("tableName").textContent = data.table.toUpperCase();
        $("rowCount").textContent = `共 ${number(data.total)} 条${state.query ? "匹配记录" : "记录"}`;
        $("pageLabel").textContent = `第 ${data.page} / ${data.pages} 页`;
        $("previousPage").disabled = data.page <= 1; $("nextPage").disabled = data.page >= data.pages;
        $("emptyState").hidden = data.rows.length !== 0; state.page = data.page; renderSchema();
    }
    async function loadRows() {
        const generation = ++state.generation;
        showAlert(""); $("tableScroll").setAttribute("aria-busy", "true");
        $("previousPage").disabled = $("nextPage").disabled = true;
        $("rowCount").textContent = "正在加载数据…"; $("dataBody").replaceChildren(); $("emptyState").hidden = true;
        try {
            const params = new URLSearchParams({ table: state.table, page: state.page, page_size: state.pageSize, q: state.query });
            const data = await request(`/api/admin/rows?${params}`);
            if (generation === state.generation) renderRows(data);
        } catch (error) { if (generation === state.generation) { showAlert(error.message); $("rowCount").textContent = "读取失败"; } }
        finally { if (generation === state.generation) $("tableScroll").setAttribute("aria-busy", "false"); }
    }
    $("searchForm").addEventListener("submit", (event) => { event.preventDefault(); state.query = $("searchInput").value.trim(); state.page = 1; loadRows(); });
    $("pageSize").addEventListener("change", () => { state.pageSize = Number($("pageSize").value); state.page = 1; loadRows(); });
    $("previousPage").addEventListener("click", () => { state.page--; loadRows(); });
    $("nextPage").addEventListener("click", () => { state.page++; loadRows(); });
    $("schemaButton").addEventListener("click", () => { $("schemaPanel").hidden = !$("schemaPanel").hidden; $("schemaButton").setAttribute("aria-expanded", String(!$("schemaPanel").hidden)); });
    $("closeDialog").addEventListener("click", () => $("recordDialog").close());
    $("recordDialog").addEventListener("click", (event) => { if (event.target === $("recordDialog")) { const r = $("recordDialog").getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) $("recordDialog").close(); } });
    async function refresh() {
        $("refreshButton").disabled = true;
        try { await loadOverview(); await loadRows(); }
        catch (error) { showAlert(error.message); $("tableScroll").setAttribute("aria-busy", "false"); }
        finally { $("refreshButton").disabled = false; }
    }
    $("refreshButton").addEventListener("click", refresh); refresh();
})();
