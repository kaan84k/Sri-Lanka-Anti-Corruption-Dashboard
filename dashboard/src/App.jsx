import { useState } from 'react'
import Overview from './components/Overview.jsx'
import CasesTable from './components/CasesTable.jsx'
import SuspectSearch from './components/SuspectSearch.jsx'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'cases', label: 'Cases' },
  { id: 'suspects', label: 'Suspect search' },
]

export default function App() {
  const [tab, setTab] = useState('overview')
  // When something on Overview is clicked, jump to Cases pre-filtered.
  // Filter is a partial of { date_from, date_to, court_level, institution }.
  const [caseFilter, setCaseFilter] = useState(null)

  const openCases = (filter) => {
    setCaseFilter(filter)
    setTab('cases')
  }
  // Date tiles / timeline dots hand off a single day.
  const openCasesForDate = (date) => openCases({ date_from: date, date_to: date })

  return (
    <>
      <header className="site-header">
        <h1>Sri Lanka Anti-Corruption Case Tracker</h1>
        <div className="subtitle">
          Court hearings from CIABOC cause lists, parsed and searchable
        </div>
        <div className="source-note">
          SOURCE: Commission to Investigate Allegations of Bribery or Corruption, Colombo 07
        </div>
      </header>

      <nav className="tabs" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'active' : ''}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
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

/* ---------- shared bits used by multiple components ---------- */

export function CourtBadge({ level }) {
  const cls =
    level === 'HC' ? 'court-HC' :
    level === 'MC' ? 'court-MC' :
    level === 'CA/SC' ? 'court-CASC' : 'court-UNK'
  return <span className={`court-badge ${cls}`}>{level || 'N/A'}</span>
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
