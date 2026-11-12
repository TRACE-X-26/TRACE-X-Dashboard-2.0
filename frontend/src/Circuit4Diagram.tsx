export default function Circuit4Diagram() {
  return <div className="circuit4-diagram"><svg viewBox="0 0 820 340" role="img" aria-label="Circuit 4 topology: 5 V through R1, TP4, S1, TP1 and R2 to ground. S2 and R3 shunt TP1. RV1 drives TP2. LM324 output TP3 drives Q1 and the LED.">
    <g fill="none" stroke="#8595a3" strokeWidth="2">
      <path d="M60 38 H790 M100 38 V60 M100 95 V115 M100 115 V135 M100 160 V188 M100 188 V215 M100 250 V280 H55 M100 188 H195 V215 M195 240 V255 M195 285 V305 H155 M100 188 H480 V135 H510 M350 38 V180 M350 220 V280 H310 M365 200 H510 M620 165 H655 M690 165 H700 V225 H715 M735 245 V280 H700 M790 38 V60 M790 95 V120 M790 142 V205 H735"/>
      <rect x="88" y="60" width="24" height="35"/><rect x="88" y="215" width="24" height="35"/>
      <rect x="184" y="255" width="22" height="30"/><rect x="338" y="180" width="24" height="40"/>
      <path d="M100 135 L115 155 M100 160 V165 M195 215 L212 235 M195 240 V245 M510 105 L510 225 L620 165 Z"/>
      <rect x="655" y="154" width="35" height="22"/>
      <rect x="778" y="60" width="24" height="35"/><path d="M782 120 H798 V142 H782 Z"/>
      <circle cx="735" cy="225" r="20"/>
    </g>
    <g fill="#e9eef6" fontFamily="Arial, sans-serif" fontSize="17">
      <text x="40" y="25">TP0 · +5 V</text><text x="130" y="82">R1 10 kΩ</text><text x="28" y="120">TP4</text>
      <text x="130" y="150">S1</text><text x="32" y="192">TP1</text><text x="18" y="240">R2</text><text x="18" y="260">10 kΩ</text>
      <text x="220" y="235">S2</text><text x="220" y="275">R3 1 kΩ</text><text x="50" y="305">GND</text>
      <text x="365" y="175">RV1 10 kΩ</text><text x="365" y="222">TP2 ≈2.0 V</text>
      <text x="523" y="140">+</text><text x="523" y="205">−</text><text x="540" y="168">LM324</text>
      <text x="625" y="140">TP3</text><text x="625" y="195">R4 4.7 kΩ</text>
      <text x="710" y="82">R5 1 kΩ</text><text x="740" y="137">LED</text>
      <text x="700" y="225">Q1</text><text x="650" y="265">2N3904</text><text x="405" y="315">+5 V → R5 1 kΩ → LED → Q1 collector</text>
    </g>
    <g fill="#41c5e7"><circle cx="100" cy="38" r="4"/><circle cx="100" cy="115" r="4"/><circle cx="100" cy="188" r="4"/><circle cx="400" cy="200" r="4"/><circle cx="640" cy="165" r="4"/></g>
  </svg><p>Topology reference, not a wiring-verification result. LM324 pin 4 = +5 V, pin 11 = GND; TP1 → pin 3, TP2 → pin 2, TP3 = pin 1. Q1 emitter = GND.</p></div>
}
