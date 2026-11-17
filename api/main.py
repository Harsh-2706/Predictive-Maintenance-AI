"""
Web API + web app server.

    uvicorn api.main:app --port 8000        # then open http://localhost:8000

Serves the JSON API under /api and the built React app (frontend/dist) at /.
Interactive API docs: http://localhost:8000/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from api.service import PlantService

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    # Load models and data once at startup, and warm up the default ranking,
    # so the first page load is fast.
    s = svc()
    s.ranked("S3_risk_priority", config.TOP_K)
    yield


app = FastAPI(title="Predictive Maintenance Platform API", version="1.1", lifespan=lifespan)
# Allow the Vite dev server (npm run dev) to call the API.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

_service: PlantService | None = None


def svc() -> PlantService:
    global _service
    if _service is None:
        _service = PlantService()
    return _service


def _guard(fn, *args):
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(422, str(e))


Strategy = Query("S3_risk_priority", description="S1_raw | S2_calibrated | S3_risk_priority | S4_class_fair")
CrewSize = Query(config.TOP_K, ge=1, le=30, description="Machines the crew can inspect per review window")


@app.get("/api/health")
def health():
    s = svc()
    return {"status": "ok", "machines": len(s.machine_class), "windows": len(s.windows)}


@app.get("/api/fleet")
def fleet():
    return svc().fleet()


@app.get("/api/story")
def story():
    return svc().story()


@app.get("/api/window/{w}")
def window(w: int, strategy: str = Strategy, k: int = CrewSize):
    return _guard(svc().window, w, strategy, k)


@app.get("/api/machine/{machine_id}")
def machine(machine_id: str, strategy: str = Strategy, k: int = CrewSize):
    return _guard(svc().machine, machine_id, strategy, k)


@app.get("/api/machine/{machine_id}/explain/{w}")
def explain(machine_id: str, w: int):
    return _guard(svc().explain, machine_id, w)


@app.get("/api/machine/{machine_id}/sliders")
def sliders(machine_id: str):
    return _guard(svc().slider_ranges, machine_id)


class WhatIf(BaseModel):
    window: int
    deltas: dict[str, float] = Field(default_factory=dict, description="sensor -> change in sensor units")
    strategy: str = "S3_risk_priority"
    k: int = Field(config.TOP_K, ge=1, le=30)


@app.post("/api/machine/{machine_id}/what-if")
def what_if(machine_id: str, body: WhatIf):
    return _guard(svc().what_if, machine_id, body.window, body.deltas, body.strategy, body.k)


@app.get("/api/calibration")
def calibration():
    return svc().calibration()


@app.get("/api/fairness")
def fairness():
    return svc().fairness()


@app.get("/api/models")
def models():
    return svc().models()


# ---------------------------------------------------------------------------
# Upgrades: baselines + savings, remaining life, model health, feedback, CSV scoring
# ---------------------------------------------------------------------------
@app.get("/api/baselines")
def baselines():
    return svc().baselines()


class Costs(BaseModel):
    downtime_cost_per_hour: float = Field(..., ge=0, description="INR lost per hour a machine is stopped")
    breakdown_downtime_hours: float = Field(..., ge=0, le=720)
    planned_downtime_hours: float = Field(..., ge=0, le=720)
    breakdown_repair_cost: float = Field(..., ge=0)
    planned_repair_cost: float = Field(..., ge=0)
    inspection_cost: float = Field(..., ge=0)
    period_days: float = Field(30, ge=1, le=366)


@app.post("/api/savings")
def savings(body: Costs):
    costs = body.model_dump()
    days = costs.pop("period_days")
    return _guard(svc().savings, costs, days)


@app.get("/api/rul")
def rul_metrics():
    return svc().rul_metrics()


@app.get("/api/health/model")
def model_health(inject_class: str | None = None, inject_sensor: str | None = None,
                 inject_pct: float = Query(0, ge=-50, le=50), inject_from_week: int = Query(2, ge=0, le=10)):
    inject = None
    if inject_class and inject_sensor and inject_pct:
        inject = {"cls": inject_class, "sensor": inject_sensor, "pct": inject_pct, "from_week": inject_from_week}
    return _guard(svc().health, inject)


class Feedback(BaseModel):
    window: int
    outcome: str = Field(..., description="fault_found | no_fault | not_checked")
    note: str = Field("", max_length=300)
    strategy: str = "S3_risk_priority"
    k: int = Field(config.TOP_K, ge=1, le=30)


@app.post("/api/machine/{machine_id}/feedback")
def add_feedback(machine_id: str, body: Feedback):
    return _guard(svc().add_feedback, machine_id, body.window, body.outcome, body.note, body.strategy, body.k)


@app.get("/api/feedback")
def feedback_summary():
    return svc().feedback_summary()


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.post("/api/score-csv")
async def score_csv(file: UploadFile = File(...), k: int = CrewSize):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 10 MB.")
    return _guard(svc().score_csv, data, k)


@app.get("/api/sample-csv", response_class=PlainTextResponse)
def sample_csv(window: int | None = None):
    text = _guard(svc().sample_csv, window)
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="sample_sensor_readings.csv"'})


# ---------------------------------------------------------------------------
# Built React app (frontend/dist). Any non-API path returns index.html.
# ---------------------------------------------------------------------------
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Unknown API route")
    target = DIST / path
    if path and target.is_file():
        return FileResponse(target)
    index = DIST / "index.html"
    if not index.exists():
        raise HTTPException(503, "Frontend not built. Run `npm run build` in frontend/.")
    return FileResponse(index)
