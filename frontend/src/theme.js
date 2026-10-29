// Single source of colour and wording. Safety yellow = "in the maintenance queue",
// signal red = "failure". Nothing else uses those two colours.
export const C = {
  bg: "#E3E5E0",
  panel: "#F3F4F0",
  ink: "#1F2328",
  muted: "#5B636B",
  rule: "#C6CAC3",
  safety: "#F2B705",
  signal: "#C0392B",
  calm: "#D4D8D1",
};

export const CLASS = {
  motor: { color: "#3D5F8F", name: "Motors", one: "motor", bay: "Motor bay" },
  pump: { color: "#2A7F6F", name: "Pumps", one: "pump", bay: "Pump house" },
  compressor: { color: "#8B4C9C", name: "Compressors", one: "compressor", bay: "Compressor room" },
};
export const CLASSES = ["motor", "pump", "compressor"];

export const STRATEGY = {
  S1_raw: { short: "Raw scores", long: "Rank by each model's raw score", color: "#9AA0A6" },
  S2_calibrated: { short: "Calibrated only", long: "Rank by calibrated failure risk", color: "#6E8FC7" },
  S3_risk_priority: { short: "Risk × consequence", long: "Calibrated risk × consequence × data freshness", color: "#1F3F8F" },
  S4_class_fair: { short: "With class safeguard", long: "Risk × consequence, plus a guaranteed slot per machine type", color: "#C77D1A" },
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
    [0, [212, 216, 209]],
    [0.15, [228, 214, 150]],
    [0.4, [230, 160, 60]],
    [0.7, [205, 90, 45]],
    [1, [168, 40, 30]],
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
  return "rgb(168,40,30)";
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
  tooltip: { backgroundColor: "#FFFFFF", borderColor: C.rule, textStyle: { color: C.ink, fontSize: 13 } },
};
export const axis = (extra = {}) => ({
  axisLine: { lineStyle: { color: C.rule } },
  axisTick: { show: false },
  axisLabel: { color: C.muted, fontSize: 12 },
  splitLine: { lineStyle: { color: "#D5D8D1", type: "dashed" } },
  nameTextStyle: { color: C.muted, fontSize: 12 },
  ...extra,
});
