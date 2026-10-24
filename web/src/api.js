async function request(path, options = {}) {
  const opts = { headers: {}, ...options }
  if (opts.body && typeof opts.body !== 'string') {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(opts.body)
  }
  const res = await fetch(path, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail || JSON.stringify(data)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  status: () => request('/api/status'),
  detect: () => request('/api/detect'),
  startScan: (path = null, maxFiles = null) =>
    request('/api/scan', { method: 'POST', body: { path, max_files: maxFiles } }),
  scanStatus: () => request('/api/scan/status'),
  stickers: (params = {}) => {
    const clean = Object.fromEntries(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    return request('/api/stickers?' + new URLSearchParams(clean))
  },
  sticker: (id) => request(`/api/stickers/${id}`),
  setTags: (id, tags) =>
    request(`/api/stickers/${id}/tags`, { method: 'POST', body: { tags } }),
  allTags: () => request('/api/tags'),
  duplicates: () => request('/api/duplicates'),
  computeDuplicates: (threshold = 8) =>
    request('/api/duplicates/compute', { method: 'POST', body: { threshold } }),
  export: (ids, dest, naming = 'orig', includeUnknown = false, all = false) =>
    request('/api/export', {
      method: 'POST',
      body: { ids, dest, naming, include_unknown: includeUnknown, all },
    }),
}
