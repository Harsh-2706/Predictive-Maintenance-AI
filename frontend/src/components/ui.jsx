import React from "react";
import ReactECharts from "echarts-for-react";
import { CLASS, STRATEGY, STRATEGIES } from "../theme.js";

export function Chart({ option, height = 300, onEvents, group }) {
  return (
    <ReactECharts option={option} style={{ height, width: "100%" }} notMerge lazyUpdate
                  onEvents={onEvents} opts={{ renderer: "canvas" }}
                  onChartReady={group ? (c) => { c.group = group; } : undefined} />
  );
}

export function Notice({ title, children, tone = "info" }) {
  return (
    <div className={`notice ${tone}`} role={tone === "error" ? "alert" : "note"}>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

export function ClassTag({ cls }) {
  return <span className="class-tag" style={{ "--c": CLASS[cls].color }}>{CLASS[cls].one}</span>;
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} role="radio" aria-checked={value === o.value}
                className={value === o.value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function StrategyPicker({ strategy, setStrategy, compact }) {
  return (
    <label className="field">
      <span>Ranking rule</span>
      <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
        {STRATEGIES.map((s) => (
          <option key={s} value={s}>{compact ? STRATEGY[s].short : STRATEGY[s].long}</option>
        ))}
      </select>
    </label>
  );
}

export function CrewSlider({ k, setK, min = 2, max = 16 }) {
  return (
    <label className="field crew">
      <span>Crew can inspect <b>{k}</b> machines per 6-hour shift</span>
      <input type="range" min={min} max={max} value={k} onChange={(e) => setK(Number(e.target.value))} />
    </label>
  );
}

export function Loading({ what = "Loading" }) {
  return <div className="loading"><div className="spinner" />{what}…</div>;
}

export function ErrorState({ title = "Something went wrong", error, onRetry, children }) {
  const detail = error instanceof Error ? error.message : String(error || "");
  return (
    <Notice title={title} tone="error">
      {children && <div>{children}</div>}
      {detail && <p className="fine error">Details: {detail}</p>}
      {onRetry && <button type="button" className="btn ghost" onClick={onRetry}>Try again</button>}
    </Notice>
  );
}

export function Bar({ value, color, max = 1 }) {
  return (
    <span className="bar" aria-hidden="true">
      <span style={{ width: `${Math.max(0, Math.min(1, value / max)) * 100}%`, background: color }} />
    </span>
  );
}
