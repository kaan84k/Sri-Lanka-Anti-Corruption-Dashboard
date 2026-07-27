import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  AreaChart, Area, PieChart, Pie, Cell, Legend, LabelList,
} from 'recharts'
import { api } from '../api.js'
import { formatDate, weekday, fmt } from '../App.jsx'
import {
  courtColor, SERIES, SERIES_SOFT, axisTick, axisTickSm, gridStroke, axisLine,
  tooltipStyle, tooltipLabelStyle, tooltipItemStyle,
} from '../theme.js'

const shortDate = (iso) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })

export default function Overview({ onSelectDate, onDrill }) {
  const [summary, setSummary] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [trend, setTrend] = useState({ levels: [], timeline: [] })
  const [institutions, setInstitutions] = useState([])
  const [courts, setCourts] = useState([])
  const [repeats, setRepeats] = useState([])
  const [error, setError] = useState(null)
  const [barMetric, setBarMetric] = useState('suspect_count') // 'suspect_count' | 'case_count'

  useEffect(() => {
    Promise.all([
      api.summary(), api.timeline(), api.institutions(8),
      api.courtLevels(), api.repeatSuspects(), api.courtTrend(),
    ])
      .then(([s, t, i, c, r, ct]) => {
        setSummary(s)
        setTimeline(t.timeline)
        setInstitutions(i.institutions)
        setCourts(c.court_levels)
        setRepeats(r.suspects)
        setTrend(ct)
      })
      .catch((e) => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="error-note">
        Could not reach the API. Make sure it is running:{' '}
        <code>py -3 -m uvicorn api.main:app --port 8000</code>
        <br />Details: {error}
      </div>
    )
  }

  const totalCourtCases = courts.reduce((a, c) => a + c.cases, 0)
  const metricLabel = barMetric === 'suspect_count' ? 'suspect records' : 'distinct cases'
  const institutionsSorted = [...institutions].sort((a, b) => b[barMetric] - a[barMetric])

  return (
    <>
      <div className="stat-row">
        {summary ? (
          <>
            <StatCard num={summary.total_hearings} label="Court hearings tracked" />
            <StatCard num={summary.unique_cases} label="Distinct case numbers" />
            <StatCard num={summary.unique_suspects} label="Named suspects" />
            <StatCard
              num={summary.source_pdfs}
              label={`Cause lists, ${formatDate(summary.date_range.from_date)} – ${formatDate(summary.date_range.to_date)}`}
            />
          </>
        ) : (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card stat-card">
              <div className="skeleton" style={{ height: 32, width: '60%' }} />
              <div className="skeleton" style={{ height: 12, width: '90%', marginTop: 8 }} />
            </div>
          ))
        )}
      </div>

      {/* ---- Phase 1: hearings-over-time trend ---- */}
      <div className="card chart-card" style={{ marginTop: 26 }}>
        <div className="chart-head">
          <span className="chart-title">Hearings over time</span>
          <span className="chart-sub">
            {timeline.length} hearing dates · {fmt(totalTimeline(timeline))} hearings
          </span>
        </div>
        {!summary ? (
          <div className="skeleton skeleton-chart" />
        ) : timeline.length === 0 ? (
          <div className="empty-note">No hearing data yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={timeline} margin={{ left: -8, right: 12, top: 6, bottom: 0 }}>
              <defs>
                <linearGradient id="hearingFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={SERIES} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={SERIES} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={gridStroke} vertical={false} />
              <XAxis
                dataKey="hearing_date" tickFormatter={shortDate}
                tick={axisTickSm} axisLine={axisLine} tickLine={false} minTickGap={24}
              />
              <YAxis
                allowDecimals={false} tick={axisTick} axisLine={false} tickLine={false} width={34}
              />
              <Tooltip
                contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle}
                labelFormatter={(d) => `${weekday(d)} · ${formatDate(d)}`}
                formatter={(v) => [`${v} hearings`, '']}
                cursor={{ stroke: SERIES, strokeWidth: 1, strokeOpacity: 0.4 }}
              />
              <Area
                type="monotone" dataKey="hearings" stroke={SERIES} strokeWidth={2}
                fill="url(#hearingFill)"
                dot={{ r: 3, fill: SERIES, stroke: 'var(--card)', strokeWidth: 1.5 }}
                activeDot={{ r: 5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ---- Phase 6: court-level composition over time ---- */}
      {summary && trend.timeline.length > 0 && trend.levels.length > 0 && (
        <div className="card chart-card" style={{ marginTop: 16 }}>
          <div className="chart-head">
            <span className="chart-title">Court level over time</span>
            <span className="chart-sub">hearings, stacked by court</span>
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={trend.timeline} margin={{ left: -8, right: 12, top: 6, bottom: 0 }}>
              <CartesianGrid stroke={gridStroke} vertical={false} />
              <XAxis
                dataKey="hearing_date" tickFormatter={shortDate}
                tick={axisTickSm} axisLine={axisLine} tickLine={false} minTickGap={24}
              />
              <YAxis allowDecimals={false} tick={axisTick} axisLine={false} tickLine={false} width={34} />
              <Tooltip
                contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle}
                labelFormatter={(d) => `${weekday(d)} · ${formatDate(d)}`}
              />
              <Legend />
              {trend.levels.map((lvl) => (
                <Area
                  key={lvl} type="monotone" dataKey={lvl} name={lvl} stackId="courts"
                  stroke={courtColor(lvl)} strokeWidth={1.5}
                  fill={courtColor(lvl)} fillOpacity={0.55} isAnimationActive={false}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="section-label">Hearing dates — select a day to see its cases</div>
      <div className="hearing-strip">
        {timeline.map((d) => (
          <button
            key={d.hearing_date}
            className="date-tile"
            onClick={() => onSelectDate(d.hearing_date)}
          >
            <div className="d-day">{weekday(d.hearing_date)}</div>
            <div className="d-date">{formatDate(d.hearing_date)}</div>
            <div className="d-count">{d.hearings} cases</div>
          </button>
        ))}
      </div>

      <div className="grid-2" style={{ marginTop: 30 }}>
        <div className="card chart-card">
          <div className="chart-head">
            <span className="chart-title">Most implicated institutions</span>
            <div className="metric-toggle" role="group" aria-label="Rank institutions by">
              <button
                className={barMetric === 'suspect_count' ? 'on' : ''}
                onClick={() => setBarMetric('suspect_count')}
              >Suspects</button>
              <button
                className={barMetric === 'case_count' ? 'on' : ''}
                onClick={() => setBarMetric('case_count')}
              >Cases</button>
            </div>
          </div>
          {!summary ? (
            <div className="skeleton skeleton-chart" />
          ) : institutionsSorted.length === 0 ? (
            <div className="empty-note">No institution data yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(220, institutionsSorted.length * 36)}>
              <BarChart data={institutionsSorted} layout="vertical" margin={{ left: 8, right: 38 }}>
                <CartesianGrid stroke={gridStroke} horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={axisTick} axisLine={axisLine} tickLine={false} />
                <YAxis
                  type="category" dataKey="institution" width={190}
                  tick={axisTickSm} axisLine={false} tickLine={false}
                />
                <Tooltip
                  contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle}
                  cursor={{ fill: SERIES_SOFT }}
                  formatter={(_v, _n, p) =>
                    [`${p.payload.suspect_count} suspect records · ${p.payload.case_count} distinct cases`, '']}
                />
                <Bar dataKey={barMetric} fill={SERIES} radius={[0, 3, 3, 0]} barSize={18}
                  isAnimationActive={false} cursor="pointer"
                  onClick={(d) => onDrill && onDrill({ institution: d.institution })}>
                  <LabelList
                    dataKey={barMetric} position="right"
                    style={{ fill: 'var(--ink-soft)', fontSize: 11 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card chart-card">
          <div className="chart-head">
            <span className="chart-title">Cases by court level</span>
            <span className="chart-sub">click a slice to filter</span>
          </div>
          {!summary ? (
            <div className="skeleton skeleton-chart" />
          ) : courts.length === 0 ? (
            <div className="empty-note">No court-level data yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={courts} dataKey="cases" nameKey="court_level"
                  innerRadius={58} outerRadius={92} paddingAngle={2}
                  label={SliceLabel}
                  labelLine={false}
                  isAnimationActive={false}
                  cursor="pointer"
                  onClick={(d) =>
                    onDrill && d && d.court_level !== 'Unknown' &&
                    onDrill({ court_level: d.court_level })}
                >
                  {courts.map((c) => (
                    <Cell key={c.court_level} fill={courtColor(c.court_level)}
                      stroke="var(--card)" strokeWidth={2} />
                  ))}
                </Pie>
                <text
                  x="50%" y="45%" textAnchor="middle" dominantBaseline="central"
                  style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, fill: 'var(--ink)' }}
                >
                  {totalCourtCases}
                </text>
                <text
                  x="50%" y="45%" dy={18} textAnchor="middle" dominantBaseline="central"
                  style={{ fontSize: 10.5, fill: 'var(--ink-soft)' }}
                >
                  cases
                </text>
                <Legend
                  verticalAlign="bottom" height={30}
                  formatter={(value) => {
                    const row = courts.find((c) => c.court_level === value)
                    return (
                      <span style={{ color: 'var(--ink)', fontSize: 12 }}>
                        {value} <span style={{ color: 'var(--ink-soft)' }}>({row ? row.cases : 0})</span>
                      </span>
                    )
                  }}
                />
                <Tooltip
                  contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} itemStyle={tooltipItemStyle}
                  formatter={(v, n) => [`${v} cases · ${pct(v, totalCourtCases)}`, n]}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="section-label">Suspects appearing on multiple hearing dates</div>
      <div className="card">
        {repeats.length === 0 ? (
          <div className="empty-note">No repeat appearances in the current data.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Hearing dates</th><th>Case numbers</th>
                <th>First seen</th><th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {repeats.map((s) => (
                <tr key={s.name}>
                  <td style={{ fontWeight: 600 }}>{s.name}</td>
                  <td>{s.hearing_dates}</td>
                  <td>{s.case_numbers}</td>
                  <td>{formatDate(s.first_seen)}</td>
                  <td>{formatDate(s.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

const pct = (v, total) => (total ? `${Math.round((v / total) * 100)}%` : '0%')

/* Direct label for a pie slice, drawn just outside the ring.
   This has to be its own <text> element: a `style` prop on <Pie> would be
   copied onto every sector path, and an inline fill there overrides the
   per-<Cell> fill attribute — which paints the whole chart one flat color.
   Slices under 5% are left to the legend so labels do not collide. */
const LABEL_RAD = Math.PI / 180
function SliceLabel({ cx, cy, midAngle, outerRadius, percent, payload }) {
  if (percent < 0.05) return null
  const x = cx + (outerRadius + 14) * Math.cos(-midAngle * LABEL_RAD)
  const y = cy + (outerRadius + 14) * Math.sin(-midAngle * LABEL_RAD)
  return (
    <text
      x={x} y={y} textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central"
      style={{ fontSize: 11, fill: 'var(--ink)' }}
    >
      {`${payload.court_level} ${Math.round(percent * 100)}%`}
    </text>
  )
}
const totalTimeline = (t) => t.reduce((a, d) => a + d.hearings, 0)

function StatCard({ num, label }) {
  return (
    <div className="card stat-card">
      <div className="num">{fmt(num)}</div>
      <div className="label">{label}</div>
    </div>
  )
}
