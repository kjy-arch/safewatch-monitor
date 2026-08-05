import { useEffect, useState } from 'react'
import { getReviewQueue, getEditableFields, reclassify, getItemHistory } from '../api'

/* 검수/선정 (요구 Q3·Q1) — AI 판정을 담당자가 검토·재분류하고, 삭제 요청 대상을 선정한다.
   재분류하면 무엇을·왜·누가 바꿨는지 이력에 남는다. */

const ACTION_TONE = {
  삭제대상: 'bg-red-100 text-red-700',
  종합판단: 'bg-amber-100 text-amber-700',
  비대상:   'bg-gray-100 text-gray-600',
}
const STATUS_TONE = {
  미확인:   'bg-gray-100 text-gray-600',
  검토중:   'bg-blue-100 text-blue-700',
  대응완료: 'bg-green-100 text-green-700',
  무관:     'bg-gray-100 text-gray-400',
}

export default function ReviewPage() {
  const [rows, setRows] = useState(null)
  const [fields, setFields] = useState({})
  const [filter, setFilter] = useState({ action_type: '삭제대상', response_status: '' })
  const [editing, setEditing] = useState(null)
  const [msg, setMsg] = useState('')

  useEffect(() => { getEditableFields().then(setFields).catch(() => {}) }, [])
  useEffect(() => { load() }, [filter])

  function load() {
    setRows(null)
    getReviewQueue(filter).then(setRows).catch(() => setRows([]))
  }

  return (
    <div className="space-y-4">
      <section className="bg-white rounded-lg shadow p-5">
        <h2 className="font-bold mb-1">검수 / 삭제 요청 선정</h2>
        <p className="text-xs text-gray-500 mb-3">
          AI 판정을 검토해 필요하면 재분류합니다. <b>바꾼 내용·사유·담당자·시각이 이력에 남습니다.</b>
          대응상태로 삭제 요청 대상을 선정·관리합니다.
        </p>
        <div className="flex flex-wrap gap-2 text-sm">
          <Select label="조치유형" value={filter.action_type}
            options={['', '삭제대상', '종합판단', '비대상']}
            onChange={v => setFilter(f => ({ ...f, action_type: v }))} />
          <Select label="대응상태" value={filter.response_status}
            options={['', '미확인', '검토중', '대응완료', '무관']}
            onChange={v => setFilter(f => ({ ...f, response_status: v }))} />
        </div>
        {msg && <p className="text-sm mt-3 text-blue-700">{msg}</p>}
      </section>

      {rows === null && <p className="text-sm text-gray-400 px-1">불러오는 중…</p>}
      {rows && !rows.length && (
        <p className="text-sm text-gray-400 px-1">조건에 맞는 항목이 없습니다.</p>
      )}

      {rows?.map(r => (
        <article key={`${r.table}:${r.id}`} className="bg-white rounded-lg shadow p-4">
          <div className="flex flex-wrap items-center gap-1.5 text-xs mb-2">
            <Chip tone="bg-blue-50 text-blue-700">{r.origin}</Chip>
            <Chip tone="bg-gray-100 text-gray-600">{r.source_type || '-'}</Chip>
            <Chip tone={ACTION_TONE[r.action_type] || 'bg-gray-100 text-gray-500'}>
              {r.action_type || '미판정'}
            </Chip>
            <Chip tone="bg-gray-100 text-gray-600">{r.category || '-'}</Chip>
            <Chip tone="bg-gray-100 text-gray-600">{r.label_l2 || '-'}</Chip>
            <Chip tone="bg-gray-100 text-gray-600">점수 {r.false_score ?? '-'} · {r.false_level || '-'}</Chip>
            <Chip tone={STATUS_TONE[r.response_status] || 'bg-gray-100'}>{r.response_status || '미확인'}</Chip>
            {r.url && <a href={r.url} target="_blank" rel="noreferrer"
              className="text-blue-600 underline">링크</a>}
          </div>
          <p className="text-sm text-gray-800 whitespace-pre-wrap line-clamp-3">{r.text?.slice(0, 400)}</p>
          <div className="mt-2 flex gap-2">
            <button onClick={() => setEditing(editing?.id === r.id ? null : r)}
              className="text-xs border rounded px-3 py-1.5 hover:bg-gray-50">
              {editing?.id === r.id ? '닫기' : '재분류 / 상태변경'}
            </button>
          </div>
          {editing?.id === r.id && (
            <EditForm row={r} fields={fields}
              onDone={m => { setEditing(null); setMsg(m); load() }} />
          )}
        </article>
      ))}
    </div>
  )
}

function EditForm({ row, fields, onDone }) {
  const [changes, setChanges] = useState({})
  const [reason, setReason] = useState('')
  const [hist, setHist] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    getItemHistory(row.table, row.id).then(setHist).catch(() => setHist([]))
  }, [row.id])

  const EDITABLE = ['action_type', 'category', 'label_l2', 'subject',
                    'intent_type', 'content_type', 'false_level', 'response_status']

  async function submit() {
    setErr('')
    if (!Object.keys(changes).length) return setErr('변경할 항목을 선택하세요.')
    if (!reason.trim()) return setErr('재분류 사유를 입력하세요. (이력에 남습니다)')
    setBusy(true)
    try {
      const r = await reclassify(row.table, row.id, changes, reason)
      onDone(r.message)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="mt-3 border-t pt-3">
      <div className="grid sm:grid-cols-2 gap-2">
        {EDITABLE.filter(f => fields[f]).map(f => (
          <label key={f} className="text-xs text-gray-500">
            <div className="mb-1">{f}</div>
            <select
              value={changes[f] ?? (row[f] || '')}
              onChange={e => setChanges(c => ({ ...c, [f]: e.target.value }))}
              className="w-full border rounded px-2 py-1.5 text-sm text-gray-800">
              <option value="">(선택 안 함)</option>
              {fields[f].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        ))}
      </div>
      <label className="block mt-3 text-xs text-gray-500">
        <div className="mb-1">재분류 사유 <span className="text-red-500">*</span></div>
        <input value={reason} onChange={e => setReason(e.target.value)}
          placeholder="예: 실제 병력 기반 문의라 삭제대상 아님"
          className="w-full border rounded px-2 py-1.5 text-sm" />
      </label>
      {err && <p className="text-xs text-red-600 mt-2">{err}</p>}
      <button onClick={submit} disabled={busy}
        className="mt-3 bg-blue-600 text-white px-4 py-1.5 rounded text-sm disabled:bg-gray-300">
        {busy ? '저장 중…' : '재분류 저장'}
      </button>

      {hist?.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-bold text-gray-600 mb-1">재분류 이력</h4>
          <ul className="text-xs text-gray-600 space-y-1">
            {hist.map(h => (
              <li key={h.id} className="border-l-2 border-gray-200 pl-2">
                <b>{h.field}</b>: {h.old_value || '(없음)'} → <b>{h.new_value}</b>
                {h.reason && <> · {h.reason}</>}
                <span className="text-gray-400">
                  {' '}· {h.operator_name || h.os_account || '미상'} · {(h.created_at || '').slice(0, 16).replace('T', ' ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Chip({ children, tone }) {
  return <span className={`px-1.5 py-0.5 rounded ${tone}`}>{children}</span>
}

function Select({ label, value, options, onChange }) {
  return (
    <label className="text-xs text-gray-500">
      <div className="mb-1">{label}</div>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="border rounded px-2 py-1.5 text-sm text-gray-800">
        {options.map(o => <option key={o} value={o}>{o || '전체'}</option>)}
      </select>
    </label>
  )
}
