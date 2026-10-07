import { useEffect, useState } from 'react'

// tên nút trong macro (Xbox) -> nhãn theo máy RG40XXV
const BUTTONS = [
  ['A', 'A'], ['B', 'B'], ['X', 'X'], ['Y', 'Y'],
  ['LB', 'L1'], ['LT', 'L2'], ['RB', 'R1'], ['RT', 'R2'],
  ['UP', '↑'], ['DOWN', '↓'], ['LEFT', '←'], ['RIGHT', '→'],
  ['BACK', 'SELECT'], ['START', 'START'], ['L3', 'L3'], ['R3', 'R3'],
]
const LABEL = Object.fromEntries(BUTTONS)

const newStep = () => ({ buttons: ['A'], hold: 50, gapMin: 100, gapMax: 100 })
const newMacro = () => ({ id: '', name: 'Macro mới', repeat: 0, steps: [newStep()] })

function post(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-RGPad': '1' },
    body: JSON.stringify(body || {}),
  }).then(async (r) => {
    const data = await r.json()
    if (!r.ok) throw new Error(data.error || 'Lỗi ' + r.status)
    return data
  })
}

function describe(m) {
  const steps = m.steps.map((s) => {
    const keys = s.buttons.map((b) => LABEL[b]).join('+')
    const gap = s.gapMin === s.gapMax ? `${s.gapMin}` : `${s.gapMin}–${s.gapMax}`
    return `${keys} ${s.hold}ms, nghỉ ${gap}ms`
  })
  return steps.join(' → ') + ' · ' + (m.repeat ? `${m.repeat} vòng` : 'lặp tới khi dừng')
}

function NumberField({ label, value, onChange, min, max, suffix = 'ms' }) {
  return (
    <label className="num">
      <span>{label}</span>
      <input type="number" min={min} max={max} value={value}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))} />
      <span className="muted">{suffix}</span>
    </label>
  )
}

function StepEditor({ step, index, count, onChange, onMove, onRemove }) {
  const random = step.gapMin !== step.gapMax
  const set = (patch) => onChange({ ...step, ...patch })
  const toggle = (b) => set({
    buttons: step.buttons.includes(b) ? step.buttons.filter((x) => x !== b) : [...step.buttons, b],
  })
  return (
    <div className="step">
      <div className="step-head">
        <b>Bước {index + 1}</b>
        <span className="step-tools">
          <button className="small" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Lên">↑</button>
          <button className="small" disabled={index === count - 1} onClick={() => onMove(1)} aria-label="Xuống">↓</button>
          <button className="small danger-text" disabled={count === 1} onClick={onRemove}>Xoá bước</button>
        </span>
      </div>
      <div className="chips">
        {BUTTONS.map(([b, label]) => (
          <button key={b} className={`chip-btn ${step.buttons.includes(b) ? 'on' : ''}`}
            aria-pressed={step.buttons.includes(b)} onClick={() => toggle(b)}>{label}</button>
        ))}
      </div>
      <div className="fields">
        <NumberField label="Giữ" value={step.hold} min={10} max={10000} onChange={(v) => set({ hold: v })} />
        <NumberField label={random ? 'Nghỉ từ' : 'Nghỉ'} value={step.gapMin} min={0} max={600000}
          onChange={(v) => set(random ? { gapMin: v } : { gapMin: v, gapMax: v })} />
        {random && (
          <NumberField label="đến" value={step.gapMax} min={0} max={600000} onChange={(v) => set({ gapMax: v })} />
        )}
        <label className="check">
          <input type="checkbox" checked={random}
            onChange={(e) => set({ gapMax: e.target.checked ? Math.max(step.gapMin * 2, step.gapMin + 50) : step.gapMin })} />
          Nghỉ ngẫu nhiên
        </label>
      </div>
    </div>
  )
}

function MacroEditor({ macro, onSave, onCancel, error }) {
  const [m, setM] = useState(macro)
  const setStep = (i, s) => setM({ ...m, steps: m.steps.map((x, j) => (j === i ? s : x)) })
  const move = (i, d) => {
    const steps = [...m.steps]
    ;[steps[i], steps[i + d]] = [steps[i + d], steps[i]]
    setM({ ...m, steps })
  }
  return (
    <div className="editor">
      <div className="fields">
        <label className="text-field">
          <span>Tên</span>
          <input value={m.name} maxLength={40} onChange={(e) => setM({ ...m, name: e.target.value })} />
        </label>
        <NumberField label="Lặp" value={m.repeat} min={0} max={100000} suffix="vòng (0 = tới khi dừng)"
          onChange={(v) => setM({ ...m, repeat: v })} />
      </div>
      {m.steps.map((s, i) => (
        <StepEditor key={i} step={s} index={i} count={m.steps.length}
          onChange={(x) => setStep(i, x)} onMove={(d) => move(i, d)}
          onRemove={() => setM({ ...m, steps: m.steps.filter((_, j) => j !== i) })} />
      ))}
      <button onClick={() => setM({ ...m, steps: [...m.steps, newStep()] })}>+ Thêm bước</button>
      {error && <div className="banner">{error}</div>}
      <div className="actions">
        <button className="primary" onClick={() => onSave(m)}>Lưu macro</button>
        <button onClick={onCancel}>Huỷ</button>
      </div>
      <p className="muted small-note">
        Bấm nhiều nút trong cùng một bước = bấm cùng lúc. Nhiều bước = bấm lần lượt (combo).
        Game thường cần giữ nút ít nhất 40–50 ms mới nhận.
      </p>
    </div>
  )
}

export default function MacroPanel({ status }) {
  const [macros, setMacros] = useState([])
  const [editing, setEditing] = useState(null) // index đang sửa, -1 = macro mới
  const [error, setError] = useState('')

  const load = () => fetch('/api/macros').then((r) => r.json()).then((d) => setMacros(d.macros))
  useEffect(() => { load() }, [status.version])

  const saveAll = (list) => post('/api/macros', { macros: list }).then((d) => {
    setMacros(d.macros)
    setEditing(null)
    setError('')
  }).catch((e) => setError(e.message))

  const onSave = (m) => {
    const list = editing === -1 ? [...macros, m] : macros.map((x, i) => (i === editing ? m : x))
    saveAll(list)
  }
  const remove = (i) => {
    if (confirm(`Xoá macro "${macros[i].name}"?`)) saveAll(macros.filter((_, j) => j !== i))
  }

  return (
    <section className="card macro">
      <div className="macro-head">
        <h2>Macro</h2>
        <span className="muted">
          Trên máy: <b>MENU + A</b> chạy/dừng macro đang chọn · <b>MENU + B</b> đổi macro
        </span>
      </div>

      {macros.map((m, i) => {
        const running = status.running === m.id
        return editing === i ? (
          <MacroEditor key={m.id} macro={m} error={error} onSave={onSave}
            onCancel={() => { setEditing(null); setError('') }} />
        ) : (
          <div key={m.id} className={`macro-row ${running ? 'running' : ''}`}>
            <label className="pick" title="Macro dùng cho MENU + A">
              <input type="radio" name="active-macro" checked={status.active === m.id}
                onChange={() => post('/api/macro/active', { id: m.id })} />
            </label>
            <div className="macro-info">
              <div className="macro-name">
                {m.name}
                {running && <span className="badge">Đang chạy · vòng {status.loops + 1}</span>}
              </div>
              <div className="muted macro-desc">{describe(m)}</div>
            </div>
            <div className="macro-tools">
              {running
                ? <button className="primary" onClick={() => post('/api/macro/stop')}>Dừng</button>
                : <button className="primary" onClick={() => post('/api/macro/start', { id: m.id })}>Chạy</button>}
              <button onClick={() => { setEditing(i); setError('') }}>Sửa</button>
              <button className="danger-text" onClick={() => remove(i)}>Xoá</button>
            </div>
          </div>
        )
      })}

      {editing === -1
        ? <MacroEditor macro={newMacro()} error={error} onSave={onSave}
            onCancel={() => { setEditing(null); setError('') }} />
        : <button onClick={() => { setEditing(-1); setError('') }}>+ Thêm macro</button>}
      {editing === null && error && <div className="banner">{error}</div>}
    </section>
  )
}
