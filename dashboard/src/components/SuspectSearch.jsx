import { useState } from 'react'
import { api } from '../api.js'
import { CourtBadge, formatDate } from '../App.jsx'

export default function SuspectSearch() {
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const search = async (e) => {
    e.preventDefault()
    if (q.trim().length < 2) return
    setLoading(true)
    setError(null)
    try {
      setResult(await api.searchSuspects(q.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="section-label">Search suspects by name</div>
      <div className="card">
        <form className="filter-bar" onSubmit={search}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <label htmlFor="s-q">Name or part of a name</label>
            <input
              id="s-q" type="text" style={{ width: '100%' }}
              placeholder="e.g. Rambukwella, Silva, Perera"
              value={q} onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <button className="btn" type="submit" disabled={q.trim().length < 2}>
            Search
          </button>
        </form>
      </div>

      {loading && <div className="loading">Searching ...</div>}
      {error && <div className="error-note" style={{ marginTop: 14 }}>API error: {error}</div>}

      {result && !loading && (
        <>
          <div className="section-label">
            {result.matches} suspect{result.matches === 1 ? '' : 's'} matching “{result.query}”
          </div>
          {result.matches === 0 && (
            <div className="card empty-note">
              No suspects found. Search accepts canonical names and reviewed
              aliases; try a shorter fragment such as the surname.
            </div>
          )}
          {result.suspects.map((p) => (
            <div key={p.person_id ?? p.name} className="card person-card">
              <h3>{p.name}</h3>
              {p.aliases.length > 0 && (
                <div className="alias-note">
                  Also listed as: {p.aliases.join(', ')}
                </div>
              )}
              {p.hearings.map((h, i) => (
                <div key={i} className="hearing-item">
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5 }}>
                    {formatDate(h.date)}
                  </span>
                  <span className="case-chip">{h.case_no}</span>
                  <CourtBadge level={h.court_level} />
                  <span style={{ color: 'var(--ink-soft)' }}>
                    {[h.designation, h.institution].filter(Boolean).join(', ')}
                  </span>
                  {h.source_name !== p.name && (
                    <span className="source-name">Source: {h.source_name}</span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </>
  )
}
