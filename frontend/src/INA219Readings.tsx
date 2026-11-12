import type { ElectricalBranch } from './types'

export default function INA219Readings({ branches, fresh = true }: { branches?: Record<string, ElectricalBranch>; fresh?: boolean }) {
  return <section className="panel"><h2>INA219 branch measurements</h2><p>Separate STM32 sensors. Circuit supply readings are not circuit test-point probe voltages.</p>
    {(['MOTOR', 'CIRCUIT'] as const).map((name, index) => {
      const branch = branches?.[name]
      const current = fresh && branch && !branch.stale
      return <div key={name}><h3>{name} · 0x{(0x40 + index).toString(16)}</h3>
        <p>{!current ? branch ? 'STALE / DISCONNECTED' : 'NOT REPORTED' : `${branch.status} · ${branch.valid ? 'valid acquisition' : 'invalid / pending acquisition'}`} · Calibration: {branch?.calibrated ? 'verified' : 'unverified'}</p>
        <section className="metric-grid">{(['voltage', 'current', 'power'] as const).map(channel => {
          const item = branch?.measurements[channel]
          return <div className="metric" key={channel}><span>{name.toLowerCase()} {channel}</span><strong>{current && branch.valid && item?.valid && item.value != null ? item.value.toFixed(3) : '—'}<small> {({ voltage: 'V', current: 'A', power: 'W' })[channel]}</small></strong></div>
        })}<div className="metric"><span>STM32 acquisition time</span><strong>{branch?.timestamp_ms ?? '—'}<small> ms</small></strong></div></section>
      </div>
    })}
  </section>
}
