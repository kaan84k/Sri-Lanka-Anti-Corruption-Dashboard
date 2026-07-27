import { useEffect, useState } from 'react'
import Overview from './components/Overview.jsx'
import CasesTable from './components/CasesTable.jsx'
import SuspectSearch from './components/SuspectSearch.jsx'
import { api } from './api.js'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'cases', label: 'Cases' },
  { id: 'suspects', label: 'Suspect search' },
]

export default function App() {
  const [tab, setTab] = useState('overview')
  const [meta, setMeta] = useState(null) // header stats: totals + date range
  // When something on Overview is clicked, jump to Cases pre-filtered.
  // Filter is a partial of { date_from, date_to, court_level, institution }.
  const [caseFilter, setCaseFilter] = useState(null)

  useEffect(() => {
    api.summary().then(setMeta).catch(() => {})
  }, [])

  const openCases = (filter) => {
    setCaseFilter(filter)
    setTab('cases')
  }
  // Date tiles / timeline dots hand off a single day.
  const openCasesForDate = (date) => openCases({ date_from: date, date_to: date })

  return (
    <>
      <header className="site-header">
        <div className="masthead">
          <Emblem />
          <div className="masthead-text">
            <h1>Sri Lanka Anti-Corruption Case Tracker</h1>
            <div className="subtitle">
              Court hearings from CIABOC cause lists, parsed and searchable
            </div>
            <div className="source-note">
              SOURCE: Commission to Investigate Allegations of Bribery or Corruption, Colombo 07
            </div>
          </div>
        </div>
        {meta && (
          <div className="masthead-meta">
            <span><b>{fmt(meta.total_hearings)}</b> hearings</span>
            <span className="dot">·</span>
            <span><b>{fmt(meta.unique_cases)}</b> cases</span>
            <span className="dot">·</span>
            <span>Data through <b>{formatDate(meta.date_range.to_date)}</b></span>
          </div>
        )}
      </header>

      <nav className="tabs" aria-label="Sections">
        <div className="tabs-inner">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? 'active' : ''}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="page">
        {tab === 'overview' && (
          <Overview onSelectDate={openCasesForDate} onDrill={openCases} />
        )}
        {tab === 'cases' && (
          <CasesTable initialFilter={caseFilter} onConsumedFilter={() => setCaseFilter(null)} />
        )}
        {tab === 'suspects' && <SuspectSearch />}
      </main>
    </>
  )
}

/* ---------- masthead marks ---------- */

function Emblem() {
  // Scales of justice — neutral civic mark, not a state seal.
  return (
    <svg className="emblem" viewBox="0 0 32 32" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 6v20M9 26h14M6 11h20" />
        <path d="M6 11l-2.5 5h5zM26 11l-2.5 5h5z" />
      </g>
      <circle cx="16" cy="6" r="1.7" fill="currentColor" />
    </svg>
  )
}

/* ---------- shared bits used by multiple components ---------- */

export function CourtBadge({ level }) {
  const cls =
    level === 'HC' ? 'court-HC' :
    level === 'MC' ? 'court-MC' :
    level === 'CA/SC' ? 'court-CASC' :
    level === 'N/A' ? 'court-NA' : 'court-UNK'
  // A null court_level is 'Unknown' (never located), which the API's pie data
  // already labels that way — it is not the same thing as a literal 'N/A' row.
  return <span className={`court-badge ${cls}`}>{level || 'Unknown'}</span>
}

export function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function weekday(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase()
}

// Thousands-separated integer formatting for headline figures.
export function fmt(n) {
  return typeof n === 'number' ? n.toLocaleString('en-GB') : n
}
