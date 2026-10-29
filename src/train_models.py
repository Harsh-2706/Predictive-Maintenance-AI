"""
Train one specialised model per machine class.

Why one model per class?  Each class has different sensors (a pump has
flow_rate, a motor has rpm) and different failure behaviour, so a single
shared model would need to handle mismatched feature sets.

Why these algorithms?
  motor       -> Random Forest            (robust non-linear baseline)
  pump        -> Gradient Boosting        (strong on tabular data)
  compressor  -> Logistic Regression      (simple, interpretable baseline)
Using three different algorithms is intentional: their probability outputs
are calibrated differently, which is exactly the problem the fusion engine
(src/fusion_engine.py) has to solve.

class_weight="balanced" is used because failures are rare. It improves recall
but pushes predicted probabilities upwards (over-confidence). That distortion
is measured in evaluation.py and corrected by calibration in src/fusion_engine.py.
"""
import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import config
from src.data_preprocessing import feature_columns, load_processed


def build_model(name):
    seed = config.RANDOM_SEED
    if name == "random_forest":
        clf = RandomForestClassifier(n_estimators=150, max_depth=12, min_samples_leaf=5,
                                     class_weight="balanced", n_jobs=-1, random_state=seed)
        return Pipeline([("clf", clf)])
    if name == "gradient_boosting":
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_depth=6,
                                             class_weight="balanced", random_state=seed)
        return Pipeline([("clf", clf)])
    if name == "logistic_regression":
        clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
        return Pipeline([("scale", StandardScaler()), ("clf", clf)])
    raise ValueError(f"Unknown model: {name}")


def model_path(machine_class):
    return config.MODELS_DIR / f"{machine_class}_model.pkl"


def train_class(machine_class, df=None):
    df = load_processed(machine_class) if df is None else df
    sensors = config.MACHINE_CLASSES[machine_class]["sensors"]
    features = feature_columns(sensors)
    train = df[df["split"] == "train"]

    model_name = config.MODEL_CHOICE[machine_class]
    model = build_model(model_name)
    model.fit(train[features], train["failure_label"])

    bundle = {
        "model": model,
        "model_name": model_name,
        "machine_class": machine_class,
        "features": features,
        "model_version": config.MODEL_VERSION,
        "train_rows": len(train),
        "train_positive_rate": float(train["failure_label"].mean()),
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
    }
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path(machine_class))
    return bundle


def load_model(machine_class):
    return joblib.load(model_path(machine_class))


def train_all(processed=None):
    processed = processed or {}
    return {c: train_class(c, processed.get(c)) for c in config.MACHINE_CLASSES}


if __name__ == "__main__":
    for c, b in train_all().items():
        print(f"{c:<11} {b['model_name']:<20} rows={b['train_rows']} pos_rate={b['train_positive_rate']:.3f}")
