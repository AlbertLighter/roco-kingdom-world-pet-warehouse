let rocoToken = "";

function setCaptureVisibility(node, enabled) {
    const shown = node.getAttribute("data-capture-display");
    if (enabled) {
        node.hidden = false;
        if (shown) node.style.display = shown;
        else node.style.removeProperty("display");
    } else {
        node.hidden = true;
        node.style.display = "none";
    }
}

async function applyCaptureMode() {
    let enabled = false;
    try {
        const res = await fetch("/api/runtime");
        if (res.ok) {
            const body = await res.json();
            enabled = !!body.capture_enabled;
        }
    } catch (_err) {
        enabled = false;
    }
    window.rocoCaptureEnabled = enabled;
    document.querySelectorAll("[data-capture-only]").forEach((node) => {
        setCaptureVisibility(node, enabled);
    });
    document.querySelectorAll("[data-capture-disabled]").forEach((node) => {
        node.hidden = enabled;
    });
}

async function rocoFetch(url, options) {
    const settings = options ? { ...options } : {};
    const method = String(settings.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
        if (!rocoToken) {
            const tokenResponse = await fetch("/api/token");
            const tokenBody = await tokenResponse.json();
            rocoToken = tokenBody.token || "";
        }
        const headers = new Headers(settings.headers || {});
        headers.set("X-Roco-Token", rocoToken);
        settings.headers = headers;
    }
    return fetch(url, settings);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { applyCaptureMode(); });
} else {
    applyCaptureMode();
}
