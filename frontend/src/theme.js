// Single source of colour and wording. Safety yellow = "in the maintenance queue",
// signal red = "failure". Nothing else uses those two colours.
export const C = {
  bg: "#F6F2EA",
  panel: "#FFFCF6",
  ink: "#1E2422",
  muted: "#5D625F",
  rule: "#D8D1C5",
  safety: "#F2B705",
  signal: "#D94A38",
  cobalt: "#3346C7",
  calm: "#E2DDD3",
};

export const CLASS = {
  motor: { color: "#365CC8", name: "Motors", one: "motor", bay: "Motor bay" },
  pump: { color: "#007D73", name: "Pumps", one: "pump", bay: "Pump house" },
  compressor: { color: "#973DA7", name: "Compressors", one: "compressor", bay: "Compressor room" },
};
export const CLASSES = ["motor", "pump", "compressor"];

export const STRATEGY = {
  S1_raw: { short: "Raw scores", long: "Rank by each model's raw score", color: "#8D938F" },
  S2_calibrated: { short: "Calibrated only", long: "Rank by calibrated failure risk", color: "#6682B7" },
  S3_risk_priority: { short: "Risk × consequence", long: "Calibrated risk × consequence × data freshness", color: "#3346C7" },
  S4_class_fair: { short: "With class safeguard", long: "Risk × consequence, plus eligible class coverage", color: "#A86818" },
};
export const STRATEGIES = Object.keys(STRATEGY);

export const MODEL_NAME = {
  random_forest: "Random Forest",
  gradient_boosting: "Gradient Boosting",
  logistic_regression: "Logistic Regression",
};

// Risk 0..1 -> fill colour: calm grey, through amber, to red.
export function riskColor(r) {
  if (r == null) return "#BFC3BC";
  const stops = [
    [0, [226, 221, 211]],
    [0.15, [239, 218, 139]],
    [0.4, [233, 168, 63]],
    [0.7, [217, 103, 63]],
    [1, [217, 74, 56]],
  ];
  for (let i = 1; i < stops.length; i++) {
    if (r <= stops[i][0]) {
      const [a, ca] = stops[i - 1];
      const [b, cb] = stops[i];
      const t = (r - a) / (b - a);
      const c = ca.map((v, j) => Math.round(v + (cb[j] - v) * t));
      return `rgb(${c.join(",")})`;
    }
  }
  return "rgb(217,74,56)";
}

export const pct = (x, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
export const fmtTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
export const sensorName = (s) =>
  ({ temperature: "Temperature", vibration: "Vibration", rpm: "Speed (rpm)", pressure: "Pressure",
     flow_rate: "Flow rate", minutes_since_last: "Data gaps" }[s] || s);
export const sensorUnit = (s) =>
  ({ temperature: "°C", vibration: "mm/s", rpm: "rpm", pressure: "bar", flow_rate: "m³/h" }[s] || "");

// Shared ECharts styling.
export const chartBase = {
  textStyle: { fontFamily: "Barlow, sans-serif", color: C.ink },
  grid: { left: 48, right: 16, top: 28, bottom: 36, containLabel: false },
  tooltip: { backgroundColor: C.panel, borderColor: C.rule, textStyle: { color: C.ink, fontSize: 13 } },
};
export const axis = (extra = {}) => ({
  axisLine: { lineStyle: { color: C.rule } },
  axisTick: { show: false },
  axisLabel: { color: C.muted, fontSize: 12 },
  splitLine: { lineStyle: { color: "#E2DDD3", type: "dashed" } },
  nameTextStyle: { color: C.muted, fontSize: 12 },
  ...extra,
});
