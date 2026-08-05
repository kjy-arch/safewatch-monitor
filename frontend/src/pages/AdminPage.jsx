import { useState, useEffect } from 'react'
import {
  getDepartments, createDepartment, updateDepartment, deleteDepartment,
  getDocs, uploadDoc, deleteDoc,
  getSettings, updateSettings,
} from '../api'

export default function AdminPage() {
  const [tab, setTab] = useState('departments')
  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-800 mb-6">관리자</h2>
      <div className="flex gap-2 mb-6">
        {[['departments', '부서 관리'], ['docs', '공식 문서 관리'], ['settings', '분석 설정']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition ${
              tab === id ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 border hover:bg-gray-50'
            }`}
          >{label}</button>
        ))}
      </div>
      {tab === 'departments' && <DepartmentsTab />}
      {tab === 'docs' && <DocsTab />}
      {tab === 'settings' && <SettingsTab />}
    </div>
  )
}

function SettingsTab() {
  const [threshold, setThreshold] = useState(70)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    getSettings().then(s => { setThreshold(s.risk_threshold); setLoading(false) })
  }, [])

  async function handleSave() {
    try {
      const s = await updateSettings({ risk_threshold: Number(threshold) })
      setThreshold(s.risk_threshold)
      setMsg('저장 완료')
    } catch (e) { setMsg('오류: ' + e.message) }
    setTimeout(() => setMsg(''), 3000)
  }

  if (loading) return <p className="text-gray-400 text-sm">불러오는 중...</p>

  return (
    <div className="bg-white rounded-xl shadow p-6 max-w-xl">
      <h3 className="font-semibold text-gray-700 mb-1">위험 임계값</h3>
      <p className="text-xs text-gray-400 mb-4">
        거짓점수가 이 값 이상인 게시글을 <span className="font-medium text-red-500">위험</span>으로 표시합니다.
        값을 바꾸면 재분석 없이 즉시 반영됩니다.
      </p>
      <div className="flex items-center gap-4">
        <input type="range" min="0" max="100" value={threshold}
          onChange={e => setThreshold(e.target.value)}
          className="flex-1 accent-red-500" />
        <input type="number" min="0" max="100" value={threshold}
          onChange={e => setThreshold(e.target.value)}
          className="w-20 border rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:border-blue-400" />
        <span className="text-sm text-gray-500">점 이상</span>
      </div>
      <div className="flex items-center gap-3 mt-5">
        <button onClick={handleSave}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition">
          저장
        </button>
        {msg && <span className="text-xs text-green-600">{msg}</span>}
      </div>
    </div>
  )
}

function DepartmentsTab() {
  const [depts, setDepts] = useState([])
  const [form, setForm] = useState({ name: '', keywords: '' })
  const [editId, setEditId] = useState(null)
  const [msg, setMsg] = useState('')

  useEffect(() => { load() }, [])
  async function load() { setDepts(await getDepartments()) }

  async function handleSave() {
    const keywords = form.keywords.split(',').map(k => k.trim()).filter(Boolean)
    try {
      if (editId) {
        await updateDepartment(editId, { name: form.name, keywords })
        setMsg('수정 완료')
      } else {
        await createDepartment({ name: form.name, keywords })
        setMsg('추가 완료')
      }
      setForm({ name: '', keywords: '' }); setEditId(null); load()
    } catch (e) { setMsg('오류: ' + e.message) }
    setTimeout(() => setMsg(''), 3000)
  }

  function startEdit(d) {
    setEditId(d.id)
    setForm({ name: d.name, keywords: d.keywords.join(', ') })
  }

  async function handleDelete(id) {
    if (!confirm('삭제하시겠습니까?')) return
    await deleteDepartment(id); load()
  }

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* 폼 */}
      <div className="bg-white rounded-xl shadow p-6">
        <h3 className="font-semibold text-gray-700 mb-4">{editId ? '부서 수정' : '부서 추가'}</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">부서명</label>
            <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
              placeholder="예: 병역판정검사과" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">키워드 (쉼표로 구분)</label>
            <input value={form.keywords} onChange={e => setForm(p => ({ ...p, keywords: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
              placeholder="예: 신체검사, 병역판정, 현역" />
          </div>
          {msg && <p className="text-xs text-green-600">{msg}</p>}
          <div className="flex gap-2">
            <button onClick={handleSave}
              className="flex-1 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition">
              {editId ? '수정 저장' : '추가'}
            </button>
            {editId && (
              <button onClick={() => { setEditId(null); setForm({ name: '', keywords: '' }) }}
                className="px-4 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50">
                취소
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 목록 */}
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left text-gray-500">부서명</th>
              <th className="px-4 py-3 text-left text-gray-500">키워드</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {depts.map(d => (
              <tr key={d.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-700">{d.name}</td>
                <td className="px-4 py-3 text-gray-400 text-xs">{d.keywords.join(', ')}</td>
                <td className="px-4 py-3 flex gap-1 justify-end">
                  <button onClick={() => startEdit(d)} className="px-2 py-1 text-xs bg-blue-50 text-blue-600 rounded hover:bg-blue-100">수정</button>
                  <button onClick={() => handleDelete(d.id)} className="px-2 py-1 text-xs bg-red-50 text-red-500 rounded hover:bg-red-100">삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DocsTab() {
  const [docs, setDocs] = useState([])
  const [title, setTitle] = useState('')
  const [file, setFile] = useState(null)
  const [url, setUrl] = useState('')
  const [mode, setMode] = useState('url') // 'url' | 'pdf'
  const [msg, setMsg] = useState('')

  useEffect(() => { load() }, [])
  async function load() { setDocs(await getDocs()) }

  async function handleUpload() {
    if (!title) return setMsg('제목을 입력하세요.')
    if (mode === 'pdf' && !file) return setMsg('PDF 파일을 선택하세요.')
    if (mode === 'url' && !url) return setMsg('URL을 입력하세요.')
    try {
      const result = await uploadDoc(title, mode === 'pdf' ? file : null, mode === 'url' ? url : null)
      setMsg(`등록 완료 (${result.content_length}자 추출)`)
      setTitle(''); setFile(null); setUrl(''); load()
    } catch (e) { setMsg('오류: ' + e.message) }
    setTimeout(() => setMsg(''), 4000)
  }

  async function handleDelete(id) {
    if (!confirm('삭제하시겠습니까?')) return
    await deleteDoc(id); load()
  }

  return (
    <div className="space-y-6">
      {/* 업로드 폼 */}
      <div className="bg-white rounded-xl shadow p-6">
        <h3 className="font-semibold text-gray-700 mb-4">공식 문서 등록</h3>
        <div className="space-y-3">
          <input value={title} onChange={e => setTitle(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
            placeholder="문서 제목 (예: 병무청 신체검사 기준 공식 설명)" />
          <div className="flex gap-2">
            {[['url', '🔗 URL'], ['pdf', '📄 PDF']].map(([m, l]) => (
              <button key={m} onClick={() => setMode(m)}
                className={`px-4 py-1.5 rounded text-sm font-medium border transition ${
                  mode === m ? 'border-blue-400 bg-blue-50 text-blue-600' : 'text-gray-500 hover:bg-gray-50'
                }`}>{l}</button>
            ))}
          </div>
          {mode === 'url'
            ? <input value={url} onChange={e => setUrl(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
                placeholder="https://..." />
            : <input type="file" accept=".pdf" onChange={e => setFile(e.target.files[0])}
                className="w-full text-sm text-gray-500" />
          }
          {msg && <p className="text-xs text-green-600">{msg}</p>}
          <button onClick={handleUpload}
            className="w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition">
            등록
          </button>
        </div>
      </div>

      {/* 목록 */}
      <div className="bg-white rounded-xl shadow overflow-hidden">
        {!docs.length
          ? <p className="text-center text-gray-400 py-8 text-sm">등록된 공식 문서가 없습니다.</p>
          : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-gray-500">제목</th>
                  <th className="px-4 py-3 text-center text-gray-500">유형</th>
                  <th className="px-4 py-3 text-left text-gray-500">출처</th>
                  <th className="px-4 py-3 text-left text-gray-500">등록일</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {docs.map(d => (
                  <tr key={d.id} className="border-b last:border-0 hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-700">{d.title}</td>
                    <td className="px-4 py-3 text-center">
                      <span className="px-2 py-0.5 bg-gray-100 text-gray-500 rounded text-xs">{d.doc_type}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs truncate max-w-[180px]">{d.source}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {new Date(d.created_at).toLocaleDateString('ko-KR')}
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleDelete(d.id)}
                        className="px-2 py-1 text-xs bg-red-50 text-red-500 rounded hover:bg-red-100">삭제</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </div>
    </div>
  )
}
