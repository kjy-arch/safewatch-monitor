import { useState, useEffect, useCallback } from 'react'
import { getBatch, getBatchStats, getDepartments, downloadUrl } from '../api'

const LEVEL_STYLE = {
  높음: 'bg-red-100 text-red-700',
  중간: 'bg-yellow-100 text-yellow-700',
  낮음: 'bg-green-100 text-green-700',
}

const ACTION_STYLE = {
  '삭제대상': 'bg-red-100 text-red-700',
  '종합판단': 'bg-yellow-100 text-yellow-700',
  '비대상':   'bg-green-100 text-green-700',
}

const CATEGORY_STYLE = {
  '편법·속임수·공정성 훼손': 'bg-red-50 text-red-600',
  '허위·조작':   'bg-orange-50 text-orange-600',
  '단순문의·불평': 'bg-gray-100 text-gray-500',
  '정책비판':    'bg-purple-50 text-purple-600',
  '정상정보':    'bg-green-50 text-green-600',
  '해당없음':    'bg-gray-100 text-gray-400',
}

const INTENT_STYLE = {
  '악의적 유포': 'bg-red-50 text-red-600',
  '단순 오해':   'bg-orange-50 text-orange-600',
  '풍자/비판':   'bg-purple-50 text-purple-600',
  '사실 보도':   'bg-green-50 text-green-600',
  '불명확':      'bg-gray-100 text-gray-500',
}

function DistCard({ title, counts, order, styleMap }) {
  const map = counts || {}
  const entries = order
    ? order.filter(k => map[k]).map(k => [k, map[k]])
    : Object.entries(map).sort((a, b) => b[1] - a[1])
  return (
    <div className="bg-white rounded-xl shadow p-4">
      <p className="text-xs font-medium text-gray-400 mb-3">{title}</p>
      <div className="flex flex-wrap gap-2">
        {entries.length === 0
          ? <span className="text-gray-300 text-xs">데이터 없음</span>
          : entries.map(([k, c]) => (
            <span key={k} className={`px-2 py-1 rounded-full text-xs font-medium ${(styleMap && styleMap[k]) || 'bg-gray-100 text-gray-500'}`}>
              {k} {c}건
            </span>
          ))}
      </div>
    </div>
  )
}

export default function BatchDetailPage({ batchId, onBack }) {
  const [data, setData] = useState(null)
  const [stats, setStats] = useState(null)
  const [deptMap, setDeptMap] = useState({})
  const [loading, setLoading] = useState(true)

  const load = useCallback(async function loadBatch() {
    setLoading(true)
    const result = await getBatch(batchId)
    setData(result)
    try {
      const depts = await getDepartments()
      setDeptMap(Object.fromEntries(depts.map(d => [d.id, d.name])))
    } catch { /* 부서 조회 실패 시 이름 대신 '—' 표시 */ }
    const done = result.batch.analyzed_rows >= result.batch.total_rows
    if (done) {
      try { setStats(await getBatchStats(batchId)) } catch { setStats(null) }
    }
    setLoading(false)
    if (result.batch.analyzed_rows < result.batch.total_rows) {
      setTimeout(loadBatch, 5000)
    }
  }, [batchId])

  useEffect(() => { load() }, [load])

  if (loading) return <p className="text-center text-gray-400 py-16">불러오는 중...</p>
  if (!data) return null

  const { batch, articles } = data
  const done = batch.analyzed_rows === batch.total_rows
  const failedCount = articles.filter(a => a.status === 'failed').length
  const deptName = id => (id && deptMap[id]) || null
  const riskThreshold = stats ? stats.risk_threshold : null
  const isRisk = a => riskThreshold != null && typeof a.false_score === 'number' && a.false_score >= riskThreshold

  return (
    <div>
      {/* 상단 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <button onClick={onBack} className="text-blue-500 hover:underline text-sm mb-1">← 목록으로</button>
          <h2 className="text-2xl font-bold text-gray-800">{batch.file_name}</h2>
          <p className="text-gray-400 text-sm mt-0.5">
            {new Date(batch.created_at).toLocaleString('ko-KR')} · 총 {batch.total_rows}행
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {!done && (
            <span className="text-yellow-600 text-sm animate-pulse">
              ⏳ 분석 중... ({batch.analyzed_rows}/{batch.total_rows})
            </span>
          )}
          {done && failedCount > 0 && (
            <span className="text-orange-500 text-sm">⚠️ {failedCount}건 분석 실패</span>
          )}
          {done && (
            <a href={downloadUrl(batchId)} download
              className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition">
              📥 엑셀 다운로드
            </a>
          )}
          <button onClick={load}
            className="px-3 py-2 bg-gray-100 text-gray-600 rounded-lg text-sm hover:bg-gray-200 transition">
            🔄 새로고침
          </button>
        </div>
      </div>

      {/* 위험 요약 배너 (관리자 임계값 기준) */}
      {done && stats && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4 flex items-center gap-3">
          <span className="text-2xl">⚠️</span>
          <div>
            <p className="text-sm text-red-700 font-semibold">위험 {stats.risk_count}건 / 총 {stats.total}건</p>
            <p className="text-xs text-red-400">거짓점수 {stats.risk_threshold}점 이상 (관리자 설정값)</p>
          </div>
        </div>
      )}

      {/* 통계 요약 (서버 /stats 엔드포인트) */}
      {done && stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
          <DistCard title="조치유형 분포" counts={stats.action_type} order={['삭제대상', '종합판단', '비대상']} styleMap={ACTION_STYLE} />
          <DistCard title="거짓 척도 분포" counts={stats.false_level} order={['높음', '중간', '낮음']} styleMap={LEVEL_STYLE} />
          <DistCard title="분류 구분 분포" counts={stats.category} styleMap={CATEGORY_STYLE} />
          <DistCard title="의도 유형 분포" counts={stats.intent_type} styleMap={INTENT_STYLE} />
          <DistCard title="연관 부서(1순위)" counts={stats.department && stats.department.primary} />
          <DistCard title="출처 분포" counts={stats.source_type} />
        </div>
      )}

      {/* 결과 테이블 */}
      <div className="bg-white rounded-xl shadow overflow-x-auto">
        <table className="w-full text-sm min-w-[1200px]">
          <thead className="bg-gray-50 text-gray-500 border-b">
            <tr>
              <th className="px-3 py-3 text-center">#</th>
              <th className="px-4 py-3 text-left">원문</th>
              <th className="px-4 py-3 text-center">출처</th>
              <th className="px-4 py-3 text-center">거짓점수</th>
              <th className="px-4 py-3 text-center">척도</th>
              <th className="px-4 py-3 text-center">조치유형</th>
              <th className="px-4 py-3 text-center">분류 구분</th>
              <th className="px-4 py-3 text-center">연관 부서</th>
              <th className="px-4 py-3 text-center">의도 유형</th>
              <th className="px-4 py-3 text-left">판단 이유</th>
            </tr>
          </thead>
          <tbody>
            {articles.map((a, i) => (
              <tr key={a.id} className={`border-b last:border-0 hover:bg-gray-50 ${isRisk(a) ? 'bg-red-50/40' : ''}`}>
                <td className="px-3 py-3 text-center text-xs text-gray-400">{a.row_index ?? i + 1}</td>
                <td className="px-4 py-3 text-gray-700 max-w-[240px]">
                  <p className="line-clamp-2 text-xs">{a.original_text}</p>
                  {a.source_url && (
                    <a href={a.source_url} target="_blank" rel="noreferrer"
                      className="text-blue-400 text-xs hover:underline">링크 →</a>
                  )}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{a.source_type}</span>
                </td>
                <td className={`px-4 py-3 text-center font-bold whitespace-nowrap ${isRisk(a) ? 'text-red-600' : 'text-gray-700'}`}>
                  {a.false_score ?? '—'}
                  {isRisk(a) && <span className="ml-1 text-xs">⚠</span>}
                </td>
                <td className="px-4 py-3 text-center">
                  {a.false_level
                    ? <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${LEVEL_STYLE[a.false_level]}`}>{a.false_level}</span>
                    : '—'}
                </td>
                <td className="px-4 py-3 text-center">
                  {a.action_type
                    ? <span className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${ACTION_STYLE[a.action_type] || 'bg-gray-100 text-gray-500'}`}>{a.action_type}</span>
                    : '—'}
                </td>
                <td className="px-4 py-3 text-center">
                  {a.category
                    ? <span className={`px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${CATEGORY_STYLE[a.category] || 'bg-gray-100 text-gray-500'}`}>{a.category}</span>
                    : '—'}
                </td>
                <td className="px-4 py-3 text-center text-xs text-gray-600 whitespace-nowrap">
                  {deptName(a.department_id) || '—'}
                  {deptName(a.department_id_2) && (
                    <span className="text-gray-400"><br />{deptName(a.department_id_2)}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-center">
                  {a.intent_type
                    ? <span className={`px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${INTENT_STYLE[a.intent_type] || 'bg-gray-100 text-gray-500'}`}>{a.intent_type}</span>
                    : '—'}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">{a.false_reason ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
