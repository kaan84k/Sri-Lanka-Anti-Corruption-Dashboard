import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { CourtBadge, formatDate } from '../App.jsx'

const PAGE_SIZE = 25

const EMPTY = { date_from: '', date_to: '', court_level: '', case_no: '', institution: '' }

export default function CasesTable({ initialFilter, onConsumedFilter }) {
  const [filters, setFilters] = useState({ ...EMPTY, ...initialFilter })
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [error, setError] = useState(null)

  // consume the filter handed off from Overview exactly once
  useEffect(() => {
    if (initialFilter) onConsumedFilter()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    setError(null)
    api
      .cases({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then(setData)
      .catch((e) => setError(e.message))
  }, [filters, page])

  const update = (key) => (e) => {
    setPage(0)
    setExpanded(null)
    setFilters((f) => ({ ...f, [key]: e.target.value }))
  }

  const clear = () => {
    setFilters({ ...EMPTY })
    setPage(0)
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <>
      <div className="section-label">Filter hearings</div>
      <div className="card">
        <div className="filter-bar">
          <div>
            <label htmlFor="f-from">From date</label>
            <input id="f-from" type="date" value={filters.date_from} onChange={update('date_from')} />
          </div>
          <div>
            <label htmlFor="f-to">To date</label>
            <input id="f-to" type="date" value={filters.date_to} onChange={update('date_to')} />
          </div>
          <div>
            <label htmlFor="f-court">Court level</label>
            <select id="f-court" value={filters.court_level} onChange={update('court_level')}>
              <option value="">All courts</option>
              <option value="MC">Magistrate's Court (MC)</option>
              <option value="HC">High Court (HC)</option>
              <option value="CA/SC">Appeal / Supreme (CA/SC)</option>
            </select>
          </div>
          <div>
            <label htmlFor="f-case">Case number</label>
            <input
              id="f-case" type="text" placeholder="e.g. 425/2025"
              value={filters.case_no} onChange={update('case_no')}
            />
          </div>
          <button className="btn ghost" onClick={clear}>Clear filters</button>
        </div>
        {filters.institution && (
          <div className="active-filter">
            Institution:
            <span className="af-chip">
              {filters.institution}
              <button
                aria-label="Remove institution filter"
                onClick={() => { setPage(0); setFilters((f) => ({ ...f, institution: '' })) }}
              >×</button>
            </span>
          </div>
        )}
      </div>

      {error && <div className="error-note" style={{ marginTop: 14 }}>API error: {error}</div>}
      {!data && !error && <div className="loading">Loading cases ...</div>}

      {data && (
        <>
          <div className="section-label">
            {data.total} hearing{data.total === 1 ? '' : 's'} found — select a row for details
          </div>
          <div className="card" style={{ padding: 0 }}>
            {data.cases.length === 0 ? (
              <div className="empty-note">
                No hearings match these filters. Clear filters to see everything.
              </div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Date</th><th>Case no.</th><th>Court</th>
                    <th>Suspects</th><th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {data.cases.map((c) => (
                    <CaseRow
                      key={c.id} c={c}
                      expanded={expanded === c.id}
                      onToggle={() => setExpanded(expanded === c.id ? null : c.id)}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {totalPages > 1 && (
            <div className="pager">
              <button className="btn ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span>page {page + 1} of {totalPages}</span>
              <button
                className="btn ghost" disabled={page + 1 >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </>
  )
}

function CaseRow({ c, expanded, onToggle }) {
  return (
    <>
      <tr className="case-row" onClick={onToggle}>
        <td style={{ whiteSpace: 'nowrap' }}>{formatDate(c.hearing_date)}</td>
        <td><span className="case-chip">{c.case_no}</span></td>
        <td><CourtBadge level={c.court_level} /></td>
        <td>
          {c.suspects.slice(0, 2).map((s) => s.name).join(', ')}
          {c.suspects.length > 2 && ` +${c.suspects.length - 2} more`}
        </td>
        <td style={{ fontSize: 12, color: 'var(--ink-soft)' }}>{c.source_pdf}</td>
      </tr>
      {expanded && (
        <tr className="expand-row">
          <td colSpan={5}>
            <div style={{ marginBottom: 8 }}>
              {c.file_nos.map((f) => (
                <span key={f} className="file-chip">FILE {f}</span>
              ))}
            </div>
            {c.suspects.map((s, i) => (
              <div key={i} className="suspect-line">
                <span className="s-name">{s.name}</span>
                {s.source_name !== s.name && (
                  <span className="source-name">listed as {s.source_name}</span>
                )}
                {(s.designation || s.institution) && (
                  <span className="s-meta">
                    {' — '}
                    {[s.designation, s.institution].filter(Boolean).join(', ')}
                  </span>
                )}
              </div>
            ))}
          </td>
        </tr>
      )}
    </>
  )
}
