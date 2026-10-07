// So do tay cam Xbox ao: hien dung nhung gi game dang nhan duoc.
const BIT = {
  UP: 0x0001, DOWN: 0x0002, LEFT: 0x0004, RIGHT: 0x0008,
  START: 0x0010, BACK: 0x0020, L3: 0x0040, R3: 0x0080,
  LB: 0x0100, RB: 0x0200, GUIDE: 0x0400,
  A: 0x1000, B: 0x2000, X: 0x4000, Y: 0x8000,
}

function Key({ x, y, w, h, label, on, r = 6 }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={r} className={on ? 'on' : 'idle'} />
      <text x={x + w / 2} y={y + h / 2} className={on ? 'label on' : 'label'}>{label}</text>
    </g>
  )
}

function Trigger({ x, y, w, h, label, value }) {
  const fill = (value / 255) * w
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={6} className="idle" />
      {fill > 0 && <rect x={x} y={y} width={Math.max(fill, 12)} height={h} rx={6} className="on" />}
      <text x={x + w / 2} y={y + h / 2} className={value > 127 ? 'label on' : 'label'}>{label}</text>
    </g>
  )
}

function Stick({ cx, cy, x, y, pressed, caption }) {
  // Xbox: len = duong -> tren man hinh phai dao truc Y
  const dx = (x / 32767) * 30
  const dy = (-y / 32767) * 30
  const moving = Math.hypot(x, y) > 3000
  return (
    <g>
      <circle cx={cx} cy={cy} r={44} className={pressed ? 'ring on-stroke' : 'ring'} />
      <circle cx={cx + dx} cy={cy + dy} r={13} className={moving ? 'dot on' : 'dot'} />
      <text x={cx} y={cy + 64} className="caption">{caption}</text>
    </g>
  )
}

function Face({ cx, cy, label, on }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={18} className={on ? 'on' : 'idle'} />
      <text x={cx} y={cy} className={on ? 'label big on' : 'label big'}>{label}</text>
    </g>
  )
}

export default function PadView({ pad }) {
  const b = pad.buttons
  const on = (name) => (b & BIT[name]) !== 0
  const s = 26
  const dx = 238, dy = 200
  return (
    <svg viewBox="0 0 640 270" className="pad" role="img" aria-label="Trạng thái tay cầm Xbox ảo">
      {/* dung thu tu nut vai tren RG40XXV: L1 mep ngoai, L2 phia trong */}
      <Key x={24} y={14} w={80} h={24} label="L1" on={on('LB')} />
      <Trigger x={112} y={14} w={96} h={24} label="L2" value={pad.lt} />
      <Trigger x={432} y={14} w={96} h={24} label="R2" value={pad.rt} />
      <Key x={536} y={14} w={80} h={24} label="R1" on={on('RB')} />

      <Stick cx={120} cy={110} x={pad.lx} y={pad.ly} pressed={on('L3')} caption="Cần trái · di chuyển" />

      <rect x={dx - s / 2} y={dy - s / 2} width={s} height={s} className="idle" />
      <rect x={dx - s / 2} y={dy - s / 2 - s} width={s} height={s} rx={4} className={on('UP') ? 'on' : 'idle'} />
      <rect x={dx - s / 2} y={dy + s / 2} width={s} height={s} rx={4} className={on('DOWN') ? 'on' : 'idle'} />
      <rect x={dx - s / 2 - s} y={dy - s / 2} width={s} height={s} rx={4} className={on('LEFT') ? 'on' : 'idle'} />
      <rect x={dx + s / 2} y={dy - s / 2} width={s} height={s} rx={4} className={on('RIGHT') ? 'on' : 'idle'} />

      <Key x={244} y={84} w={58} h={22} label="SELECT" on={on('BACK')} r={11} />
      <Key x={340} y={84} w={50} h={22} label="START" on={on('START')} r={11} />

      <Stick cx={420} cy={190} x={pad.rx} y={pad.ry} pressed={on('R3')} caption="Cần phải · camera" />

      {/* bo cuc nhu tren may: X tren, A phai, B duoi, Y trai (gan theo chu in) */}
      <Face cx={520} cy={76} label="X" on={on('X')} />
      <Face cx={556} cy={110} label="A" on={on('A')} />
      <Face cx={520} cy={144} label="B" on={on('B')} />
      <Face cx={484} cy={110} label="Y" on={on('Y')} />
    </svg>
  )
}
