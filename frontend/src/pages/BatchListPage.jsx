import { useState, useEffect } from 'react'
import { getBatches, quarterlyReportUrl } from '../api'

export default function BatchListPage({ onSelect }) {
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getBatches().then(data => { setBatches(data); setLoading(false) })
  }, [])

  if (loading) return <p className="text-center text-gray-400 py-16">불러오는 중...</p>

  if (!batches.length)
    return (
      <div className="text-center py-16 text-gray-400">
        <p className="text-4xl mb-3">📋</p>
        <p>분석 이력이 없습니다.</p>
      </div>
    )

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">분석 결과 목록</h2>
        <a href={quarterlyReportUrl()} download
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition">
          📊 분기 보고서 (최근 3개월)
        </a>
      </div>
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 border-b">
            <tr>
              <th className="px-4 py-3 text-left">파일명</th>
              <th className="px-4 py-3 text-center">총 행</th>
              <th className="px-4 py-3 text-center">분석 완료</th>
              <th className="px-4 py-3 text-left">날짜</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {batches.map(b => (
              <tr key={b.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-700">{b.file_name}</td>
                <td className="px-4 py-3 text-center">{b.total_rows}</td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    b.analyzed_rows === b.total_rows
                      ? 'bg-green-100 text-green-700'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {b.analyzed_rows}/{b.total_rows}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400">
                  {new Date(b.created_at).toLocaleString('ko-KR')}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => onSelect(b.id)}
                    className="px-3 py-1 bg-blue-50 text-blue-600 rounded text-xs font-medium hover:bg-blue-100 transition"
                  >
                    결과 보기
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
