import { useEffect, useState, useRef } from 'react'
import {
  getCrawlSources, runCrawl, getCrawlStatus, getBacklog, runAnalyzeBacklog,
} from '../api'

/* 수집 화면 — 기존 대시보드(dashboard.html)의 기능을 옮겨온 것.
   소스 선택 · 수동 수집 · 진행률 · 출처별 실적 · 미분류 백로그 분류. */

const TIER_LABEL = { safe: '안전', gray: '회색' }

export default function CollectPage() {
  const [sources, setSources] = useState([])
  const [picked, setPicked] = useState(() => new Set())
  const [status, setStatus] = useState(null)
  const [backlog, setBacklog] = useState(null)
  const [limit, setLimit] = useState(100)
  const [msg, setMsg] = useState('')
  const timer = useRef(null)

  useEffect(() => {
    getCrawlSources().then(list => {
      setSources(list)
      // 안전 소스는 기본 선택, 회색지대는 명시적으로 골라야 실행된다
      setPicked(new Set(list.filter(s => s.tier === 'safe' && s.is_active).map(s => s.id)))
    }).catch(() => setMsg('수집 소스를 불러오지 못했습니다.'))
    poll()
    return () => clearTimeout(timer.current)
  }, [])

  function poll() {
    getCrawlStatus().then(s => {
      setStatus(s)
      if (s.status === 'running') timer.current = setTimeout(poll, 1500)
      else getBacklog().then(b => setBacklog(b.unclassified)).catch(() => {})
    }).catch(() => {})
  }

  function toggle(id) {
    setPicked(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function start() {
    const ids = [...picked]
    if (!ids.length) return setMsg('수집할 소스를 하나 이상 선택하세요.')
    const gray = sources.filter(s => ids.includes(s.id) && s.tier === 'gray')
    if (gray.length && !confirm(
      `회색지대 소스가 포함됩니다: ${gray.map(g => g.name).join(', ')}\n\n` +
      '이 소스들은 공식 API가 아닌 방식으로 수집하며, 기관 법무·정보보안 검토가 ' +
      '완료되지 않았습니다. 실행 사실은 이력에 기록됩니다. 계속할까요?'
    )) return
    setMsg('')
    try {
      await runCrawl(ids)
      setTimeout(poll, 600)
    } catch (e) { setMsg(e.message) }
  }

  async function analyzeBacklog() {
    try {
      await runAnalyzeBacklog(limit)
      setTimeout(poll, 600)
    } catch (e) { setMsg(e.message) }
  }

  const running = status?.status === 'running'
  const pct = status?.phase_total
    ? Math.round((status.phase_done / status.phase_total) * 100) : 0

  return (
    <div className="space-y-6">
      {msg && <div className="bg-amber-50 border border-amber-300 text-amber-800 px-4 py-2 rounded text-sm">{msg}</div>}

      {/* 소스 선택 */}
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="font-bold mb-1">수집 소스 선택</h2>
        <p className="text-xs text-gray-500 mb-3">
          안전(공식 API)은 기본 선택됩니다. 회색지대(스크래핑·비공식)는 직접 선택해야 실행되며,
          실행 사실이 이력에 기록됩니다.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {sources.map(s => (
            <label key={s.id}
              className={`flex items-center gap-2 border rounded px-3 py-2 text-sm cursor-pointer ${
                !s.is_active ? 'opacity-40' : picked.has(s.id) ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
              }`}>
              <input type="checkbox" disabled={!s.is_active}
                checked={picked.has(s.id)} onChange={() => toggle(s.id)} />
              <span className="flex-1">{s.name}</span>
              <span className={`text-[11px] px-1.5 rounded ${
                s.tier === 'gray' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-500'}`}>
                {TIER_LABEL[s.tier] || s.tier}
              </span>
            </label>
          ))}
          {!sources.length && <p className="text-sm text-gray-400">불러오는 중…</p>}
        </div>
        <button onClick={start} disabled={running}
          className="mt-4 bg-blue-600 text-white px-5 py-2 rounded font-medium disabled:bg-gray-300">
          {running ? '실행 중…' : '수동 수집 시작'}
        </button>
      </section>

      {/* 진행률 */}
      <section className="bg-white rounded-lg shadow p-5">
        <div className="flex justify-between text-sm mb-1">
          <span className="font-medium">{status?.phase || '대기 중'}</span>
          <span className="text-gray-500">{pct}%</span>
        </div>
        <div className="h-2 bg-gray-100 rounded overflow-hidden">
          <div className="h-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="grid grid-cols-4 gap-3 mt-4 text-center">
          <Tile label="수집" value={status?.collected ?? 0} />
          <Tile label="분류" value={status?.analyzed ?? 0} />
          <Tile label="위험 높음" value={status?.high ?? 0} tone="text-red-600" />
          <Tile label="위험 중간" value={status?.mid ?? 0} tone="text-amber-600" />
        </div>
        {status?.message && <p className="text-xs text-gray-500 mt-3">{status.message}</p>}
        {status?.export_path && (
          <p className="text-xs text-green-700 mt-1">결과 엑셀 저장: {status.export_path}</p>
        )}
      </section>

      {/* 출처별 (이번 실행) */}
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="font-bold mb-3">출처별 수집 <span className="text-gray-400 font-normal text-sm">· 이번 실행</span></h2>
        {Object.keys(status?.by_source || {}).length ? (
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(status.by_source).map(([name, n]) => (
                <tr key={name} className="border-b last:border-0">
                  <td className="py-1.5">{name}</td>
                  <td className="py-1.5 text-right font-medium">{n}건</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-gray-400">아직 수집 실적이 없습니다.</p>}
      </section>

      {/* 미분류 백로그 */}
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="font-bold mb-1">
          미분류 분류 {backlog != null && <span className="text-amber-600 text-sm">{backlog}건 대기</span>}
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          수집됐지만 아직 분류되지 않은 글을 처리합니다. 처리 건수만큼 Gemini 비용이 발생합니다.
        </p>
        <div className="flex gap-2">
          <select value={limit} onChange={e => setLimit(Number(e.target.value))}
            className="border rounded px-3 py-2 text-sm">
            {[50, 100, 300, 500, 1000].map(n => <option key={n} value={n}>{n}건</option>)}
          </select>
          <button onClick={analyzeBacklog} disabled={running || !backlog}
            className="bg-gray-700 text-white px-4 py-2 rounded text-sm disabled:bg-gray-300">
            분류 실행
          </button>
        </div>
      </section>
    </div>
  )
}

function Tile({ label, value, tone = 'text-gray-800' }) {
  return (
    <div className="border rounded py-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
    </div>
  )
}
