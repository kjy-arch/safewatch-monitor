import { useEffect, useState } from 'react'
import { getRuns } from '../api'

/* 실행 이력 — 담당자가 번갈아 쓰는 운영에서 "지난주에 누가 돌렸나"를 확인한다.
   ⚠️ 신원 값은 인증이 아니라 기록이다(로그인 없음). 부인방지는 성립하지 않는다. */

const TYPE = { crawl: '수집', analyze: '미분류 분류', batch: '엑셀 분석' }
const STATUS = {
  running: ['실행 중', 'bg-blue-100 text-blue-700'],
  done:    ['완료',    'bg-green-100 text-green-700'],
  failed:  ['실패',    'bg-red-100 text-red-700'],
}

function fmt(ts) {
  if (!ts) return '-'
  return ts.slice(0, 16).replace('T', ' ')
}

function elapsed(a, b) {
  if (!a || !b) return ''
  const sec = Math.round((new Date(b) - new Date(a)) / 1000)
  if (sec < 60) return `${sec}초`
  return `${Math.floor(sec / 60)}분 ${sec % 60}초`
}

export default function RunsPage() {
  const [runs, setRuns] = useState(null)

  useEffect(() => { getRuns(100).then(setRuns).catch(() => setRuns([])) }, [])

  return (
    <div className="space-y-4">
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="font-bold mb-1">실행 이력</h2>
        <p className="text-xs text-gray-500">
          다른 PC에서 돌린 작업도 함께 보입니다. 담당자 이름은 각 PC에서 입력한 값이며,
          로그인이 없으므로 <b>인증이 아니라 기록</b>입니다.
        </p>
      </section>

      <section className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              {['시작', '유형', '담당자', 'PC', '상태', '수집', '분류', '소요', '비고'].map(h => (
                <th key={h} className="text-left px-3 py-2 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs?.map(r => {
              const [label, cls] = STATUS[r.status] || [r.status, 'bg-gray-100 text-gray-600']
              return (
                <tr key={r.id} className="border-t">
                  <td className="px-3 py-2 whitespace-nowrap">{fmt(r.started_at)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{TYPE[r.run_type] || r.run_type}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {r.operator_name || <span className="text-gray-400">미등록</span>}
                    {r.os_account && <span className="text-gray-400 text-xs"> ({r.os_account})</span>}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-gray-500">{r.host_name || '-'}</td>
                  <td className="px-3 py-2"><span className={`px-2 py-0.5 rounded text-xs ${cls}`}>{label}</span></td>
                  <td className="px-3 py-2 text-right">{r.collected || 0}</td>
                  <td className="px-3 py-2 text-right">{r.analyzed || 0}</td>
                  <td className="px-3 py-2 whitespace-nowrap text-gray-500">
                    {elapsed(r.started_at, r.finished_at)}
                  </td>
                  <td className="px-3 py-2 text-gray-500 max-w-xs truncate" title={r.message || ''}>
                    {r.message || ''}
                  </td>
                </tr>
              )
            })}
            {runs && !runs.length && (
              <tr><td colSpan={9} className="px-3 py-6 text-center text-gray-400">
                아직 실행 이력이 없습니다.
              </td></tr>
            )}
            {!runs && (
              <tr><td colSpan={9} className="px-3 py-6 text-center text-gray-400">불러오는 중…</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  )
}
