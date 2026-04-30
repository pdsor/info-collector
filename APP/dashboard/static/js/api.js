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
    
    // SSE 流
    stream(path) {
        return new EventSource(this.base + path);
    }
};
