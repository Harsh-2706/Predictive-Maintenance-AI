// Thin client for the FastAPI backend (api/main.py).
const cache = new Map();

async function request(path, options) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export function get(path) {
  if (!cache.has(path)) {
    const p = request(path).catch((e) => { cache.delete(path); throw e; });
    cache.set(path, p);
  }
  return cache.get(path);
}

export const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  fleet: () => get("/fleet"),
  story: () => get("/story"),
  window: (w, s, k) => get(`/window/${w}?strategy=${s}&k=${k}`),
  machine: (id, s, k) => get(`/machine/${id}?strategy=${s}&k=${k}`),
  explain: (id, w) => get(`/machine/${id}/explain/${w}`),
  sliders: (id) => get(`/machine/${id}/sliders`),
  whatIf: (id, body) => post(`/machine/${id}/what-if`, body),
  calibration: () => get("/calibration"),
  fairness: () => get("/fairness"),
  models: () => get("/models"),
};
