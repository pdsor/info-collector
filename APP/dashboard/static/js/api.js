const API = {
    base: "/api",

    async get(path) {
        const r = await fetch(this.base + path);
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async post(path, body) {
        const r = await fetch(this.base + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async patch(path, body) {
        const r = await fetch(this.base + path, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async put(path, body) {
        const r = await fetch(this.base + path, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async delete(path) {
        const r = await fetch(this.base + path, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    // SSE 流 — url 直接使用完整路径（不含 base 前缀）
    sse(url, handlers) {
        const es = new EventSource(url);
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'heartbeat') return;
                handlers.onData?.(data);
            } catch {}
        };
        es.addEventListener('done', (e) => {
            try {
                const data = JSON.parse(e.data);
                handlers.onData?.(data);
            } catch {}
        });
        es.onerror = (e) => { handlers.onError?.(e); };
        return es;
    }
};
