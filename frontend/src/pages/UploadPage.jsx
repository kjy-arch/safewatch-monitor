import { useState, useRef } from 'react'
import { uploadExcel, startAnalyze } from '../api'

export default function UploadPage({ onComplete }) {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('idle') // idle | uploading | analyzing | done | error
  const [message, setMessage] = useState('')
  const inputRef = useRef()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!file) return

    try {
      setStatus('uploading')
      setMessage('엑셀 파일 업로드 중...')
      const { batch_id, total_rows } = await uploadExcel(file)

      setStatus('analyzing')
      setMessage(`${total_rows}행 업로드 완료. AI 분석 시작 중...`)
      await startAnalyze(batch_id)

      setStatus('done')
      setMessage(`분석 요청 완료! 결과 확인 중...`)
      setTimeout(() => onComplete(batch_id), 1500)
    } catch (err) {
      setStatus('error')
      setMessage(err.message)
    }
  }

  const levelColors = {
    uploading: 'bg-blue-50 border-blue-200 text-blue-700',
    analyzing: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    done: 'bg-green-50 border-green-200 text-green-700',
    error: 'bg-red-50 border-red-200 text-red-700',
  }

  return (
    <div className="max-w-xl mx-auto">
      <div className="bg-white rounded-xl shadow p-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-2">엑셀 업로드</h2>
        <p className="text-gray-500 text-sm mb-6">
          분석할 텍스트가 담긴 엑셀 파일을 업로드하세요.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div
            onClick={() => inputRef.current.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition ${
              file ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400'
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={e => setFile(e.target.files[0])}
            />
            {file ? (
              <div>
                <p className="text-blue-700 font-medium">📄 {file.name}</p>
                <p className="text-gray-400 text-xs mt-1">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            ) : (
              <div>
                <p className="text-gray-400 text-4xl mb-2">📂</p>
                <p className="text-gray-500">클릭하여 엑셀 파일 선택</p>
                <p className="text-gray-400 text-xs mt-1">.xlsx, .xls 파일</p>
              </div>
            )}
          </div>

          {status !== 'idle' && (
            <div className={`border rounded-lg px-4 py-3 text-sm ${levelColors[status] || ''}`}>
              {status === 'uploading' && <span className="animate-pulse">⏳ </span>}
              {status === 'analyzing' && <span className="animate-pulse">🤖 </span>}
              {status === 'done' && '✅ '}
              {status === 'error' && '❌ '}
              {message}
            </div>
          )}

          <button
            type="submit"
            disabled={!file || status === 'uploading' || status === 'analyzing'}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {status === 'uploading' || status === 'analyzing' ? '처리 중...' : 'AI 분석 시작'}
          </button>
        </form>

        <div className="mt-6 bg-gray-50 rounded-lg p-4 text-xs text-gray-500 space-y-2">
          <p className="font-medium text-gray-600">엑셀 형식 안내</p>
          <p>• <span className="font-medium text-gray-600">컬럼명 자유</span> — 기존 엑셀 그대로 사용 가능. 내용·텍스트·본문·기사내용 등 자동 인식</p>
          <p>• <span className="font-medium text-gray-600">컬럼명 없어도 OK</span> — 첫 번째 열을 원문으로 자동 처리</p>
          <p>• <span className="font-medium text-gray-600">출처 구분값</span> — 언론 · SNS · 커뮤니티 · 유튜브 (없거나 다른 값이면 "언론"으로 처리)</p>
        </div>
      </div>
    </div>
  )
}
