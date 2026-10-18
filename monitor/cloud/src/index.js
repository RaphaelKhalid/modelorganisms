// Read-only public mirror of the modelorganisms wave-2 monitor (modelled on the neuronjury monitor).
// GET  /api/state -> latest snapshot (stored gzipped in KV, served as-is)
// POST /api/push  -> replace the snapshot; requires the x-mo-token secret
// There are no control endpoints: runs are only ever controlled from the owner's machine.
const EMPTY = JSON.stringify({ phase: "waiting", phases: [], events: [], updated: null });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/api/state") {
      const body = await env.LIVE.get("snapshot", "arrayBuffer");
      if (!body) return new Response(EMPTY, { headers: { "content-type": "application/json", "cache-control": "no-store" } });
      return new Response(body, {
        headers: { "content-type": "application/json", "content-encoding": "gzip", "cache-control": "no-store" },
        encodeBody: "manual",
      });
    }
    if (url.pathname === "/api/push") {
      if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
      if (!env.MO_PUSH_TOKEN || req.headers.get("x-mo-token") !== env.MO_PUSH_TOKEN) return new Response("forbidden", { status: 403 });
      const body = await req.arrayBuffer();
      if (body.byteLength > 4_000_000) return new Response("too large", { status: 413 });
      await env.LIVE.put("snapshot", body);
      return new Response("ok");
    }
    if (url.pathname.startsWith("/api/")) return new Response("not found", { status: 404 });
    return env.ASSETS.fetch(req);
  },
};
