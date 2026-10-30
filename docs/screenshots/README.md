# Web-app screenshot capture guide

No verified current-app screenshots were present when the README gallery was added.
Capture these from the running React/FastAPI application at `http://localhost:8000`,
using the built application after `npm run build`.

| File | Route | Capture state | Caption |
|---|---|---|---|
| `control-room.png` | `#/control` | S3, 8 crew slots, reveal-off | Live, capacity-constrained maintenance queue. |
| `fairness-lab.png` | `#/fairness` | Compressors, S3, 8 crew slots | Strategy-versus-capacity experiment with class-level outcomes. |
| `models-calibration.png` | `#/models` | Calibrated-risk curve selected | Model identities, calibration evidence, and held-out metrics. |
| `machine-detail.png` | `#/machine/C-08` | A reporting shift | Risk history, sensor traces, and the live what-if controls. |
| `method.png` | `#/method` | Top of page | The inspectable six-stage engineering pipeline. |

Use a 1440px-wide desktop viewport, exclude browser chrome, and do not edit or crop
the product UI in a way that changes what the app displayed. Save the PNGs in this
directory; the README references these exact relative paths.
