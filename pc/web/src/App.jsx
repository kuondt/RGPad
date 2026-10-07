import { useEffect, useState } from 'react'
import PadView from './PadView.jsx'
import MacroPanel from './MacroPanel.jsx'

const NEUTRAL_PAD = { buttons: 0, lx: 0, ly: 0, rx: 0, ry: 0, lt: 0, rt: 0 }

function post(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-RGPad': '1' },
    body: JSON.stringify(body || {}),
  }).then((r) => r.json())
}

function useBackend() {
  const [state, setState] = useState(null)
  const [online, setOnline] = useState(true)
  useEffect(() => {
    const es = new EventSource('/api/events')
    es.onmessage = (e) => {
      setState(JSON.parse(e.data))
      setOnline(true)
    }
    es.onerror = () => setOnline(false)
    return () => es.close()
  }, [])
  return [state, setState, online]
}

function StatusCard({ s, onRetry }) {
  const pcIp = s.ips[0] || '?'
  const view = {
    waiting: ['warn', 'Đang chờ RG40XXV…',
      `Mở Applications → RGPad trên máy cầm tay · IP của PC: ${pcIp} · cổng UDP ${s.port}`],
    ok: ['good', `Đã kết nối RG40XXV  ${s.client}`, `${s.rate} gói/giây`],
    lost: ['bad', `Mất tín hiệu từ RG40XXV  ${s.client}`,
      'Kiểm tra WiFi, hoặc mở lại app RGPad trên máy cầm tay'],
    error: ['bad', 'Chưa chạy được', s.error || ''],
  }[s.status]
  const [tone, title, sub] = view
  return (
    <section className="card status">
      <span className={`dot ${tone}`} />
      <div className="status-text">
        <div className="title">{title}</div>
        <div className="sub">{sub}</div>
      </div>
      {s.status === 'error' && <button onClick={onRetry}>Thử lại</button>}
    </section>
  )
}

function Tile({ label, value, tone }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className={`tile-value ${tone || ''}`}>{value}</div>
    </div>
  )
}

export default function App() {
  const [s, setS, online] = useBackend()
  const [stopped, setStopped] = useState(false)

  if (stopped) {
    return (
      <main className="app center">
        <h1>RGPad đã tắt</h1>
        <p className="muted">Tay cầm ảo đã nhả hết nút. Mở lại bằng shortcut <b>RGPad PC</b>.</p>
      </main>
    )
  }
  if (!s) {
    return (
      <main className="app center">
        <p className="muted">{online ? 'Đang kết nối tới RGPad…' : 'Không kết nối được RGPad. Hãy mở shortcut RGPad PC.'}</p>
      </main>
    )
  }

  const quit = () => {
    if (confirm('Tắt RGPad? Máy cầm tay sẽ không điều khiển được PC nữa.')) {
      post('/api/quit').finally(() => setStopped(true))
    }
  }
  const padTone = s.padOk ? 'good' : 'bad'
  const padText = s.dry ? 'Chế độ thử' : s.padOk ? (s.paused ? 'Đã tạm dừng' : 'Sẵn sàng') : 'Lỗi'

  return (
    <main className="app">
      <header>
        <div>
          <h1>RGPad</h1>
          <p className="muted">Bảng điều khiển trên PC · nhận nút từ RG40XXV</p>
        </div>
        <span className={`chip ${s.sunshine ? 'good' : 'bad'}`}>
          <span className={`dot small ${s.sunshine ? 'good' : 'bad'}`} />
          Sunshine {s.sunshine ? 'đang chạy' : s.sunshine === false ? 'đang tắt' : '?'}
        </span>
      </header>

      {!online && <div className="banner">Mất kết nối tới chương trình RGPad trên PC…</div>}
      {s.duplicate && (
        <div className="banner warn">
          Máy cầm tay đang chạy 2 bản RGPad cùng lúc (vd RGPad và RGPad-Nen). Đang dùng bản có bấm nút,
          bỏ qua bản kia. Hãy thoát bớt một bản cho chắc.
        </div>
      )}

      <StatusCard s={s} onRetry={() => post('/api/retry').then(setS)} />

      <section className={`card pad-card ${s.paused ? 'paused' : ''}`}>
        <PadView pad={s.status === 'ok' ? s.pad : NEUTRAL_PAD} />
        {s.paused && <div className="paused-note">Đã tạm dừng · game không nhận nút</div>}
        {!s.paused && s.keyboard && (
          <div className="mouse-note">
            Chế độ bàn phím · đang gõ từ máy cầm tay vào cửa sổ đang mở · đã gõ {s.keysTyped} phím
          </div>
        )}
        {!s.paused && s.mouse && (
          <div className="mouse-note">
            Chế độ chuột · A chuột trái · B chuột phải · X chuột giữa · L1/R1 cuộn · giữ L2 di chậm ·
            START Enter · SELECT Esc · giữ MENU: D-pad là D-pad tay cầm
          </div>
        )}
      </section>

      <section className="tiles">
        <Tile label="Tay cầm Xbox ảo" value={padText} tone={s.paused || s.dry ? 'warn' : padTone} />
        <Tile label="Chế độ" value={s.keyboard ? 'Bàn phím' : s.mouse ? 'Chuột' : 'Tay cầm'}
          tone={s.keyboard || s.mouse ? 'warn' : ''} />
        <Tile label="Gói/giây" value={s.rate} />
        <Tile label="IP của PC" value={s.ips.join(', ') || '?'} />
      </section>

      <section className="actions">
        <button className="primary" disabled={s.status === 'error'}
          onClick={() => post('/api/pause', { paused: !s.paused }).then(setS)}>
          {s.paused ? 'Tiếp tục' : 'Tạm dừng'}
        </button>
        <a className="button" href={s.sunshineUrl} target="_blank" rel="noreferrer">Mở trang Sunshine</a>
        {s.client
          ? <a className="button" href={`http://${s.client}:9090`} target="_blank" rel="noreferrer"
              title="Trang quản lý file muOS (Web Services) trên máy cầm tay">Mở quản lý file máy</a>
          : <button disabled title="Chưa kết nối máy cầm tay nên chưa biết IP">Mở quản lý file máy</button>}
        <button className="danger" onClick={quit}>Tắt RGPad</button>
      </section>

      {s.macro && <MacroPanel status={s.macro} />}

      <section className="card log">
        <h2>Nhật ký</h2>
        <ul>
          {[...s.log].reverse().map((l, i) => (
            <li key={i}><span className="muted">{l.t}</span> {l.msg}</li>
          ))}
        </ul>
      </section>

      <footer className="muted">
        Trên máy cầm tay: <b>MENU + START</b> để thoát · <b>MENU + Y</b> chuột ↔ tay cầm · <b>MENU + X</b> bàn phím · <b>MENU + A / B</b> chạy / đổi macro · giữ <b>MENU</b> + cần để xoay camera ·
        <b> MENU + SELECT</b> bật/tắt D-pad camera
      </footer>
    </main>
  )
}
