const BASE = '/api'

export async function uploadExcel(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/batches/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function startAnalyze(batchId) {
  const res = await fetch(`${BASE}/batches/${batchId}/analyze`, { method: 'POST' })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function getBatches() {
  const res = await fetch(`${BASE}/batches`)
  return res.json()
}

export async function getBatch(batchId) {
  const res = await fetch(`${BASE}/batches/${batchId}`)
  return res.json()
}

export function downloadUrl(batchId) {
  return `${BASE}/batches/${batchId}/download`
}

export async function getBatchStats(batchId) {
  const res = await fetch(`${BASE}/batches/${batchId}/stats`)
  return res.json()
}

export function quarterlyReportUrl(from, to) {
  const q = new URLSearchParams()
  if (from) q.set('from', from)
  if (to) q.set('to', to)
  const qs = q.toString()
  return `${BASE}/reports/quarterly/download${qs ? '?' + qs : ''}`
}

export async function getDepartments() {
  const res = await fetch(`${BASE}/departments`)
  return res.json()
}

export async function createDepartment(data) {
  const res = await fetch(`${BASE}/departments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function updateDepartment(id, data) {
  const res = await fetch(`${BASE}/departments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function deleteDepartment(id) {
  await fetch(`${BASE}/departments/${id}`, { method: 'DELETE' })
}

export async function getSettings() {
  const res = await fetch(`${BASE}/settings`)
  return res.json()
}

export async function updateSettings(data) {
  const res = await fetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function getDocs() {
  const res = await fetch(`${BASE}/docs`)
  return res.json()
}

export async function uploadDoc(title, file, url) {
  const form = new FormData()
  form.append('title', title)
  if (file) form.append('file', file)
  if (url) form.append('url', url)
  const res = await fetch(`${BASE}/docs`, { method: 'POST', body: form })
  if (!res.ok) throw new Error((await res.json()).detail)
  return res.json()
}

export async function deleteDoc(id) {
  await fetch(`${BASE}/docs/${id}`, { method: 'DELETE' })
}

/* ===== 수집(Monitor) 계열 — Phase 5 통합 ===== */

export async function getCrawlSources() {
  const res = await fetch(`${BASE}/crawl/sources`)
  return res.json()
}

export async function runCrawl(sourceIds) {
  const res = await fetch(`${BASE}/crawl/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(sourceIds ? { source_ids: sourceIds } : {}),
  })
  if (!res.ok) throw new Error((await res.json()).detail || '수집 실행 실패')
  return res.json()
}

export async function getCrawlStatus() {
  const res = await fetch(`${BASE}/crawl/status`)
  return res.json()
}

export async function getBacklog() {
  const res = await fetch(`${BASE}/crawl/backlog`)
  return res.json()
}

export async function runAnalyzeBacklog(limit) {
  const res = await fetch(`${BASE}/crawl/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ limit }),
  })
  if (!res.ok) throw new Error((await res.json()).detail || '분류 실행 실패')
  return res.json()
}

/* ===== 담당자·실행 이력 ===== */

export async function getOperator() {
  const res = await fetch(`${BASE}/operator`)
  return res.json()
}

export async function setOperator(name) {
  const res = await fetch(`${BASE}/operator`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error((await res.json()).detail || '저장 실패')
  return res.json()
}

export async function getRuns(limit = 50) {
  const res = await fetch(`${BASE}/runs?limit=${limit}`)
  return res.json()
}

/* ===== 보고서 ===== */

export async function getQuarterlySummary(from, to) {
  const qs = new URLSearchParams()
  if (from) qs.set('from', from)
  if (to) qs.set('to', to)
  const res = await fetch(`${BASE}/reports/quarterly/summary${qs.toString() ? '?' + qs : ''}`)
  if (!res.ok) throw new Error((await res.json()).detail || '집계 조회 실패')
  return res.json()
}

export function quarterlyDownloadUrl(from, to) {
  const qs = new URLSearchParams()
  if (from) qs.set('from', from)
  if (to) qs.set('to', to)
  return `${BASE}/reports/quarterly/download${qs.toString() ? '?' + qs : ''}`
}

/* ===== 검수·재분류 (Phase 6) ===== */

export async function getReviewQueue({ action_type, response_status, limit = 100 } = {}) {
  const qs = new URLSearchParams()
  if (action_type) qs.set('action_type', action_type)
  if (response_status) qs.set('response_status', response_status)
  qs.set('limit', limit)
  const res = await fetch(`${BASE}/review/queue?${qs}`)
  return res.json()
}

export async function getEditableFields() {
  const res = await fetch(`${BASE}/review/fields`)
  return res.json()
}

export async function reclassify(table, id, changes, reason) {
  const res = await fetch(`${BASE}/review/${table}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ changes, reason }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '재분류 실패')
  return data
}

export async function getItemHistory(table, id) {
  const res = await fetch(`${BASE}/review/${table}/${id}/history`)
  return res.json()
}

export async function registerExclusion(table, targetId, ruleType, reason) {
  const res = await fetch(`${BASE}/review/exclusions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table, target_id: targetId, rule_type: ruleType, reason }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '제외 규칙 등록 실패')
  return data
}

export async function getExclusions() {
  const res = await fetch(`${BASE}/review/exclusions`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '제외 규칙 조회 실패')
  return data
}

export async function deactivateExclusion(id) {
  const res = await fetch(`${BASE}/review/exclusions/${id}`, { method: 'DELETE' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '제외 규칙 해제 실패')
  return data
}

/* 2단계 검증 — 삭제대상 판정을 본문으로 재확인 (2026-08-07).
   판정을 덮어쓰지 않는다. 2차 결과를 1차와 나란히 보여주고 최종 판단은 담당자가 한다. */
export async function getVerifyPending() {
  const res = await fetch(`${BASE}/verify/pending`)
  return res.json()
}

export async function runVerify(limit = 200) {
  const res = await fetch(`${BASE}/verify/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ limit }),
  })
  return res.json()
}

export async function getVerifyStatus() {
  const res = await fetch(`${BASE}/verify/status`)
  return res.json()
}

export function articlesExportUrl({ scope = 'today', false_level = '' } = {}) {
  const qs = new URLSearchParams({ scope })
  if (false_level) qs.set('false_level', false_level)
  return `${BASE}/articles/export?${qs}`
}
