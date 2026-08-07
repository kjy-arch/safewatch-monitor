import { useEffect, useState } from 'react'
import { getQuarterlySummary, quarterlyDownloadUrl } from '../api'

/* 분기 보고서 — 수집분 + 업로드분 통합 집계 (Phase 4).
   엑셀을 내려받기 전에 집계를 화면에서 먼저 확인할 수 있게 한다. */

function isoDate(d) { return d.toISOString().slice(0, 10) }
const DEFAULT_TO = isoDate(new Date())
const DEFAULT_FROM = isoDate(new Date(Date.now() - 90 * 86400000))

export default function ReportPage() {
  const [from, setFrom] = useState(DEFAULT_FROM)
  const [to, setTo] = useState(DEFAULT_TO)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true); setErr('')
    try { setData(await getQuarterlySummary(from, to)) }
    catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => {
    let active = true
    getQuarterlySummary(DEFAULT_FROM, DEFAULT_TO)
      .then(result => { if (active) setData(result) })
      .catch(e => { if (active) setErr(e.message) })
    return () => { active = false }
  }, []) // 첫 진입 시 최근 3개월

  return (
    <div className="space-y-6">
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="font-bold mb-3">분기 보고서</h2>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="시작일"><input type="date" value={from} onChange={e => setFrom(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm" /></Field>
          <Field label="종료일"><input type="date" value={to} onChange={e => setTo(e.target.value)}
            className="border rounded px-2 py-1.5 text-sm" /></Field>
          <button onClick={load} disabled={loading}
            className="bg-blue-600 text-white px-4 py-2 rounded text-sm disabled:bg-gray-300">
            {loading ? '집계 중…' : '집계 보기'}
          </button>
          <a href={quarterlyDownloadUrl(from, to)}
            className="bg-green-600 text-white px-4 py-2 rounded text-sm">
            엑셀 다운로드
          </a>
        </div>
        {err && <p className="text-sm text-red-600 mt-3">{err}</p>}
      </section>

      {data && (
        <>
          <section className="bg-white rounded-lg shadow p-5">
            <div className="flex items-baseline justify-between">
              <h3 className="font-bold">{data.period}</h3>
              <span className="text-2xl font-bold">{data.total}건</span>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              수집분 {data.sources.수집분}건 + 업로드분 {data.sources.업로드분}건
              {data.sources.중복제거 > 0 && (
                <> − 중복 {data.sources.중복제거}건
                  <span className="text-gray-400"> (같은 글이 양쪽에 있어 제외)</span></>
              )}
            </p>
            {!data.total && (
              <p className="text-sm text-gray-400 mt-3">
                해당 기간에 분석된 자료가 없습니다.
              </p>
            )}
          </section>

          {data.total > 0 && (
            <div className="grid sm:grid-cols-2 gap-4">
              <Dist title="조치유형" data={data.by_action_type} highlight="삭제대상" />
              <Dist title="분류구분" data={data.by_category} />
              <Dist title="거짓척도" data={data.by_false_level} highlight="높음" />
              <Dist title="의도유형" data={data.by_intent_type} />
              <Dist title="출처" data={data.by_source_type} />
              <Dist title="수집 경로" data={data.by_origin} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="text-xs text-gray-500">
      <div className="mb-1">{label}</div>
      {children}
    </label>
  )
}

function Dist({ title, data, highlight }) {
  const entries = Object.entries(data || {})
  const max = Math.max(1, ...entries.map(([, v]) => v))
  return (
    <section className="bg-white rounded-lg shadow p-5">
      <h3 className="font-bold text-sm mb-3">{title}</h3>
      {entries.length ? entries.map(([k, v]) => (
        <div key={k} className="mb-2">
          <div className="flex justify-between text-sm">
            <span className={k === highlight ? 'font-bold text-red-600' : ''}>{k}</span>
            <span className="text-gray-600">{v}건</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded mt-1">
            <div className={`h-full rounded ${k === highlight ? 'bg-red-500' : 'bg-blue-400'}`}
              style={{ width: `${(v / max) * 100}%` }} />
          </div>
        </div>
      )) : <p className="text-sm text-gray-400">없음</p>}
    </section>
  )
}
