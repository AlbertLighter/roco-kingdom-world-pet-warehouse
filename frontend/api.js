let rocoToken = "";

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
