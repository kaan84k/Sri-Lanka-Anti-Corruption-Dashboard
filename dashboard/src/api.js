// All backend calls go through here.
// In dev, "/api" is proxied by Vite to http://127.0.0.1:8000 (see vite.config.js).
// In production, set VITE_API_URL to your deployed API, e.g. https://api.yourdashboard.lk
const BASE = import.meta.env.VITE_API_URL || '/api'

async function get(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null)
  ).toString()
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`)
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

export const api = {
  summary: () => get('/stats/summary'),
  cases: (params) => get('/cases', params),
  searchSuspects: (q) => get('/suspects/search', { q }),
  institutions: (limit = 10) => get('/stats/institutions', { limit }),
  repeatSuspects: () => get('/stats/repeat-suspects'),
  timeline: () => get('/stats/hearings-per-date'),
  courtLevels: () => get('/stats/court-levels'),
  courtTrend: () => get('/stats/court-trend'),
}
