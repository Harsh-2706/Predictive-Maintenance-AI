"""
Central configuration for the Multi-Machine Predictive Maintenance Platform.

Every tunable number lives here so that the simulator, models, fusion engine
and dashboard all read the same values. Change a value here, re-run main.py,
and the whole pipeline updates consistently.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_SIM_DIR = ROOT / "data" / "simulated"
DATA_PROC_DIR = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"
METRICS_DIR = RESULTS_DIR / "metrics"
PREDICTIONS_DIR = RESULTS_DIR / "predictions"
FIGURES_DIR = RESULTS_DIR / "figures"

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
SIM_START = "2026-01-01 00:00:00"
SIM_DAYS = 120                      # total simulated time span

# Target definition: a reading is labelled 1 if the machine fails
# within the next FAILURE_HORIZON_HOURS. This is the "defined failure event"
# that every model predicts and every metric is measured against.
FAILURE_HORIZON_HOURS = 24

# Each machine class deliberately differs in:
#   - sampling rate          -> "different data rates" (R&D question)
#   - number of machines     -> different alert volumes
#   - mean cycle length      -> different failure prevalence
#   - signal-to-noise        -> different model difficulty / calibration
#   - dropout probability    -> stale readings (data freshness)
MACHINE_CLASSES = {
    "motor": {
        "n_machines": 30,
        "sample_every_min": 15,
        "mean_cycle_days": 8,
        "sensors": ["temperature", "vibration", "rpm"],
        "noise_scale": 1.0,
        "dropout_prob": 0.01,
    },
    "pump": {
        "n_machines": 18,
        "sample_every_min": 30,
        "mean_cycle_days": 10,
        "sensors": ["pressure", "flow_rate", "temperature"],
        "noise_scale": 1.3,
        "dropout_prob": 0.03,
    },
    "compressor": {
        "n_machines": 12,
        "sample_every_min": 60,
        "mean_cycle_days": 12,
        "sensors": ["temperature", "pressure", "vibration"],
        "noise_scale": 1.8,   # weakest signal -> hardest class
        "dropout_prob": 0.06,
    },
}

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
# Rolling windows are defined in TIME, not in number of rows, so that a
# motor (every 10 min) and a compressor (every 60 min) summarise the same
# physical duration. This is how we handle different data rates at the
# feature level.
ROLLING_WINDOWS = ["2h", "6h"]

# ---------------------------------------------------------------------------
# Train / validation / test split (chronological, no shuffling)
# ---------------------------------------------------------------------------
# Validation set is used by the fusion engine for probability calibration.
# Test set must stay untouched until final evaluation.
TRAIN_FRAC = 0.60
VAL_FRAC = 0.20
TEST_FRAC = 0.20

# ---------------------------------------------------------------------------
# Models: one specialised model per machine class
# ---------------------------------------------------------------------------
MODEL_CHOICE = {
    "motor": "random_forest",
    "pump": "gradient_boosting",
    "compressor": "logistic_regression",
}
MODEL_VERSION = "v1.0"

# Threshold used to turn a probability into an alert (model-level metrics).
ALERT_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Fusion engine settings
# ---------------------------------------------------------------------------
# Severity weight per class = relative consequence of an unplanned failure
# (downtime, repair cost, safety). ASSUMED values for the prototype, to be
# replaced by plant data (e.g. downtime cost per hour) in deployment:
#   compressor 1.0  - feeds several lines; failure stops pneumatic supply
#   pump       0.9  - process-critical, but often has a standby unit
#   motor      0.7  - most numerous, individually least critical
SEVERITY_WEIGHTS = {
    "motor": 0.7,
    "pump": 0.9,
    "compressor": 1.0,
}

# Freshness factor = 0.5 ** (reading_age_min / FRESHNESS_HALF_LIFE_MIN).
# A reading that is 2 h old counts half as much as a live one.
FRESHNESS_HALF_LIFE_MIN = 120

# Maintenance review cycle: every REVIEW_WINDOW_HOURS the team looks at the
# queue and can act on TOP_K machines (crew capacity).
REVIEW_WINDOW_HOURS = 6
TOP_K = 8

# Strategy S4 (class-fair) safeguard: each class gets at least
# MIN_SLOTS_PER_CLASS slots IF it has a machine with calibrated risk
# >= MIN_ELIGIBLE_RISK. Below that bar a slot is not forced.
MIN_SLOTS_PER_CLASS = 1
MIN_ELIGIBLE_RISK = 0.20

# Bootstrap resamples (over review windows) for confidence intervals.
BOOTSTRAP_ITERS = 1000

STRATEGIES = {
    "S1_raw": "Raw model score",
    "S2_calibrated": "Calibrated risk",
    "S3_risk_priority": "Calibrated risk x severity x freshness",
    "S4_class_fair": "S3 + class-coverage safeguard",
}
