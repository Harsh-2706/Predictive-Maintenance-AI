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
  baselines: () => get("/baselines"),
  savings: (body) => post("/savings", body),
  rul: () => get("/rul"),
  health: (inject) => request(`/health/model${inject ? `?inject_class=${inject.cls}&inject_sensor=${inject.sensor}&inject_pct=${inject.pct}&inject_from_week=${inject.from_week}` : ""}`),
  feedback: () => request("/feedback"),
  addFeedback: (id, body) => post(`/machine/${id}/feedback`, body),
  scoreCsv: (file, k) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/score-csv?k=${k}`, { method: "POST", body: form });
  },
};
