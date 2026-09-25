let page = 1;
let pageSize = 40;
let total = 0;
let selectedId = null;
let lastJson = "";

const bodyEl = document.getElementById("packetBody");
const pageInfo = document.getElementById("pageInfo");
const detailTitle = document.getElementById("detailTitle");
const detailMeta = document.getElementById("detailMeta");
const detailView = document.getElementById("detailView");
const jobLog = document.getElementById("jobLog");

function setBusy(busy) {
    ["importBtn", "recordBtn", "replayBtn", "clearBtn", "parseBtn", "serializeBtn"].forEach((id) => {
        const node = document.getElementById(id);
        if (node && id !== "parseBtn" && id !== "serializeBtn") node.disabled = busy;
    });
}

async function loadIfaces() {
    const select = document.getElementById("iface");
    select.innerHTML = "";
    try {
        const res = await fetch("/api/capture_ifaces");
        const data = await res.json();
        const rows = data.ifaces || [];
        if (!rows.length) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "没有可用网卡";
            select.appendChild(option);
            return;
        }
        rows.forEach((row) => {
            const option = document.createElement("option");
            option.value = row.name;
            option.textContent = row.detail ? `${row.name}  ${row.detail}` : row.name;
            select.appendChild(option);
        });
    } catch (error) {
        jobLog.textContent = "网卡列表加载失败";
    }
}

async function loadPackets() {
    const params = new URLSearchParams({
        page: String(page),
        pageSize: String(pageSize),
        direction: document.getElementById("direction").value,
        opcode: document.getElementById("opcode").value.trim(),
        q: document.getElementById("query").value.trim(),
    });
    const res = await fetch("/api/packets?" + params.toString());
    const data = await res.json();
    total = data.total || 0;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    pageInfo.textContent = `第 ${data.page} / ${pages} 页，共 ${total} 条`;
    bodyEl.innerHTML = "";
    (data.data || []).forEach((row) => {
        const tr = document.createElement("tr");
        if (row.id === selectedId) tr.className = "active";
        tr.innerHTML = `<td>${row.ts || ""}</td><td class="dir-${row.direction}">${row.direction || ""}</td><td>${row.opcode_name || row.opcode_hex}<br><small>${row.opcode_hex}</small></td><td>${row.summary || ""}</td>`;
        tr.addEventListener("click", () => openPacket(row.id));
        bodyEl.appendChild(tr);
    });
    if (!data.data || !data.data.length) {
        bodyEl.innerHTML = `<tr><td colspan="4">还没有记录。可以载入 data 导出，或开始抓包。</td></tr>`;
    }
}

async function openPacket(id) {
    selectedId = id;
    lastJson = "";
    const res = await fetch(`/api/packets/${id}`);
    if (!res.ok) {
        detailView.textContent = "读取失败";
        return;
    }
    const item = await res.json();
    detailTitle.textContent = `${item.opcode_name}  ${item.opcode_hex}`;
    detailMeta.innerHTML = [
        ["时间", item.ts],
        ["方向", item.direction],
        ["连接", item.session || ""],
        ["来源", item.source || ""],
        ["长度", `${item.body_len || 0} 字节${item.truncated ? "（已截断）" : ""}`],
        ["摘要", item.summary || ""],
    ].map(([name, value]) => `<span>${name}</span><div>${value || ""}</div>`).join("");
    const hex = item.app_body_hex || "";
    detailView.textContent = hex ? `载荷 hex（前 512 字符）\n${hex.slice(0, 512)}${hex.length > 512 ? "\n…" : ""}` : "这条消息没有应用层载荷";
    document.getElementById("parseBtn").disabled = false;
    document.getElementById("serializeBtn").disabled = false;
    document.getElementById("applyBtn").disabled = item.opcode !== 0x1346;
    document.getElementById("copyBtn").disabled = true;
    document.getElementById("downloadBtn").disabled = true;
    if (item.decoded) {
        lastJson = JSON.stringify(item.decoded, null, 2);
        detailView.textContent = lastJson;
        document.getElementById("copyBtn").disabled = false;
        document.getElementById("downloadBtn").disabled = false;
    }
    loadPackets();
}

async function readSse(url, options) {
    const res = await fetch(url, options);
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "请求失败");
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const event = JSON.parse(line.slice(6));
            if (event.error) throw new Error(event.error);
            if (event.message) jobLog.textContent = event.message;
            if (event.done) return event.result || {};
        }
    }
    return {};
}

document.getElementById("searchBtn").addEventListener("click", () => { page = 1; loadPackets(); });
document.getElementById("prevBtn").addEventListener("click", () => { if (page > 1) { page -= 1; loadPackets(); } });
document.getElementById("nextBtn").addEventListener("click", () => {
    if (page * pageSize < total) { page += 1; loadPackets(); }
});

document.getElementById("parseBtn").addEventListener("click", async () => {
    if (!selectedId) return;
    const res = await fetch(`/api/packets/${selectedId}/parse`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) { detailView.textContent = data.detail || "解析失败"; return; }
    lastJson = JSON.stringify(data, null, 2);
    detailView.textContent = lastJson;
    document.getElementById("copyBtn").disabled = false;
    document.getElementById("downloadBtn").disabled = false;
    loadPackets();
});

document.getElementById("serializeBtn").addEventListener("click", async () => {
    if (!selectedId) return;
    const res = await fetch(`/api/packets/${selectedId}/serialize`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) { detailView.textContent = data.detail || "序列化失败"; return; }
    lastJson = data.json || JSON.stringify(data.export_entry, null, 2);
    detailView.textContent = lastJson;
    document.getElementById("copyBtn").disabled = false;
    document.getElementById("downloadBtn").disabled = false;
});

document.getElementById("copyBtn").addEventListener("click", async () => {
    if (!lastJson) return;
    await navigator.clipboard.writeText(lastJson);
    jobLog.textContent = "已复制 JSON";
});

document.getElementById("downloadBtn").addEventListener("click", () => {
    if (!lastJson) return;
    const blob = new Blob([lastJson], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `packet-${selectedId}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
});

document.getElementById("applyBtn").addEventListener("click", async () => {
    if (!selectedId) return;
    const res = await fetch(`/api/packets/${selectedId}/apply`, { method: "POST" });
    const data = await res.json();
    jobLog.textContent = res.ok ? `已写入仓库：新增 ${data.new || 0}，更新 ${data.updated || 0}` : (data.detail || "写入失败");
});

document.getElementById("importBtn").addEventListener("click", async () => {
    setBusy(true);
    jobLog.textContent = "正在载入导出…";
    try {
        const res = await fetch("/api/packets/import_exports", { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "载入失败");
        jobLog.textContent = `已从 ${data.files} 个文件载入 ${data.saved} 条`;
        page = 1;
        await loadPackets();
    } catch (error) {
        jobLog.textContent = error.message;
    }
    setBusy(false);
});

document.getElementById("recordBtn").addEventListener("click", async () => {
    setBusy(true);
    try {
        const result = await readSse("/api/packets/record", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mode: "live",
                iface: document.getElementById("iface").value,
                seconds: Number(document.getElementById("seconds").value) || 120,
            }),
        });
        jobLog.textContent = `记录结束，共 ${result.saved || 0} 条`;
        page = 1;
        await loadPackets();
    } catch (error) {
        jobLog.textContent = error.message;
    }
    setBusy(false);
});

document.getElementById("replayBtn").addEventListener("click", async () => {
    setBusy(true);
    try {
        const result = await readSse("/api/packets/record", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: "pcap", path: document.getElementById("pcapPath").value.trim() }),
        });
        jobLog.textContent = `回放结束，共 ${result.saved || 0} 条`;
        page = 1;
        await loadPackets();
    } catch (error) {
        jobLog.textContent = error.message;
    }
    setBusy(false);
});

document.getElementById("clearBtn").addEventListener("click", async () => {
    if (!window.confirm("清空全部抓包记录？")) return;
    await fetch("/api/packets", { method: "DELETE" });
    selectedId = null;
    detailTitle.textContent = "选择一条消息";
    detailMeta.innerHTML = "";
    detailView.textContent = "解析结果和序列化 JSON 会显示在这里。";
    page = 1;
    loadPackets();
});

loadIfaces();
loadPackets();
