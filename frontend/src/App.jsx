import { useEffect, useState } from 'react'
import CollectPage from './pages/CollectPage'
import UploadPage from './pages/UploadPage'
import BatchListPage from './pages/BatchListPage'
import BatchDetailPage from './pages/BatchDetailPage'
import ReviewPage from './pages/ReviewPage'
import ReportPage from './pages/ReportPage'
import RunsPage from './pages/RunsPage'
import AdminPage from './pages/AdminPage'
import { getOperator, setOperator } from './api'

const NAV = [
  { id: 'collect', label: '수집' },
  { id: 'upload', label: '분석하기' },
  { id: 'batches', label: '결과 목록' },
  { id: 'review', label: '검수/선정' },
  { id: 'report', label: '보고서' },
  { id: 'runs', label: '실행 이력' },
  { id: 'admin', label: '관리자' },
]

export default function App() {
  const [page, setPage] = useState('collect')
  const [selectedBatchId, setSelectedBatchId] = useState(null)
  const [op, setOp] = useState(null)

  useEffect(() => { getOperator().then(setOp).catch(() => {}) }, [])

  function goToBatch(id) {
    setSelectedBatchId(id)
    setPage('batch-detail')
  }

  async function changeOperator() {
    const name = prompt('담당자 이름을 입력하세요 (실행 이력에 기록됩니다)', op?.operator_name || '')
    if (!name || !name.trim()) return
    try {
      await setOperator(name)
      setOp(await getOperator())
    } catch (e) { alert(e.message) }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-blue-700 text-white shadow">
        <div className="max-w-6xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h1 className="text-xl font-bold">SafeWatch</h1>
              <p className="text-blue-200 text-xs">병무청 불법·허위·조작정보 수집 · 분류 시스템</p>
            </div>
            <button onClick={changeOperator}
              className="text-xs text-blue-100 hover:text-white border border-blue-500 rounded px-3 py-1.5">
              담당자 <b className="text-white">{op?.display || '…'}</b>
              {op && !op.configured && <span className="ml-1 text-amber-300">· 미등록</span>}
            </button>
          </div>
          <nav className="flex gap-1 mt-3 flex-wrap">
            {NAV.map(n => (
              <button
                key={n.id}
                onClick={() => setPage(n.id)}
                className={`px-4 py-1.5 rounded text-sm font-medium transition ${
                  page === n.id || (n.id === 'batches' && page === 'batch-detail')
                    ? 'bg-white text-blue-700' : 'text-blue-100 hover:bg-blue-600'
                }`}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {page === 'collect' && <CollectPage />}
        {page === 'upload' && <UploadPage onComplete={goToBatch} />}
        {page === 'batches' && <BatchListPage onSelect={goToBatch} />}
        {page === 'batch-detail' && (
          <BatchDetailPage batchId={selectedBatchId} onBack={() => setPage('batches')} />
        )}
        {page === 'review' && <ReviewPage />}
        {page === 'report' && <ReportPage />}
        {page === 'runs' && <RunsPage />}
        {page === 'admin' && <AdminPage />}
      </main>
    </div>
  )
}
