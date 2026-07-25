/* ============================================================
   Chart theme — single source of truth for all Recharts visuals.
   Colors reference CSS variables (index.css) so light/dark mode
   is handled by the cascade, not by JS. Court hues intentionally
   match the .court-badge colors: color follows the entity.
   ============================================================ */

// Categorical hues, keyed by court level. These are brand-locked
// identity colors (same as the badges); always paired with a legend
// and direct labels as secondary encoding.
export const COURT_COLORS = {
  HC: 'var(--court-HC)',
  MC: 'var(--court-MC)',
  'CA/SC': 'var(--court-CASC)',
  Unknown: 'var(--court-UNK)',
}

export const courtColor = (level) => COURT_COLORS[level] || 'var(--court-UNK)'

// Single-series (magnitude) hue for bars and the timeline area.
export const SERIES = 'var(--chart-series)'
export const SERIES_SOFT = 'var(--chart-series-soft)'

// Shared axis / grid / tick styling. Tokens resolve per color scheme.
export const axisTick = { fontSize: 12, fill: 'var(--chart-tick)' }
export const axisTickSm = { fontSize: 11.5, fill: 'var(--chart-tick)' }
export const gridStroke = 'var(--chart-grid)'
export const axisLine = { stroke: 'var(--chart-axis)' }

// Tooltip container styling passed to Recharts <Tooltip contentStyle>.
export const tooltipStyle = {
  background: 'var(--tooltip-bg)',
  border: '1px solid var(--tooltip-border)',
  borderRadius: 6,
  fontSize: 12.5,
  color: 'var(--ink)',
  fontFamily: 'var(--font-body)',
  boxShadow: '0 4px 14px rgba(0,0,0,0.12)',
}
export const tooltipLabelStyle = { color: 'var(--ink-soft)', fontWeight: 600 }
export const tooltipItemStyle = { color: 'var(--ink)' }
