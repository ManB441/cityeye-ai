import { useId } from "react";
export type EyePhase = "idle" | "verifying" | "success" | "failure";
const networkPaths = [
  "M45 230 132 142 216 142 279 83 390 83 457 104 540 104 632 175 715 230",
  "M45 230 132 318 216 318 279 377 390 377 457 356 540 356 632 285 715 230",
  "M74 230 171 174 226 174 291 115 455 115 521 153 585 153 685 230",
  "M74 230 171 286 226 286 291 345 455 345 521 307 585 307 685 230",
  "M45 230H173L220 197H254M715 230H587L540 197H506",
  "M45 230H173L220 263H254M715 230H587L540 263H506",
  "M132 142V101H216L249 68H316M132 318V359H216L249 392H316",
  "M632 175V126H577L532 81H461M632 285V334H577L532 379H461",
  "M171 174V230L216 275V318M585 153V230L540 275V307",
  "M216 142V101M279 83V115M540 104V153M216 318V359M279 345V377M540 307V356",
];
const nodes = [[45,230],[132,142],[216,142],[279,83],[390,83],[457,104],[540,104],[632,175],[715,230],[132,318],[216,318],[279,377],[390,377],[540,356],[632,285],[171,174],[226,174],[291,115],[455,115],[585,153],[171,286],[226,286],[291,345],[455,345],[585,307],[132,101],[216,101],[249,68],[632,126],[577,126],[132,359],[249,392],[577,334],[532,379]];
export function CityEyeVisual({ phase = "idle" }: { phase?: EyePhase }) {
  const id = useId().replace(/:/g, "");
  return <div className="cityeye-visual" data-phase={phase} aria-hidden="true">
    <svg viewBox="0 0 760 460" className="cityeye-svg">
      <defs>
        <radialGradient id={`${id}-iris`}><stop stopColor="#0c464b" stopOpacity=".5" /><stop offset=".66" stopColor="#082c34" stopOpacity=".4" /><stop offset="1" stopColor="#05151d" stopOpacity="0" /></radialGradient>
        <linearGradient id={`${id}-edge`}><stop stopColor="#25777c" stopOpacity=".15"/><stop offset=".45" stopColor="#63d9cf" stopOpacity=".85"/><stop offset="1" stopColor="#2c9299" stopOpacity=".3"/></linearGradient>
      </defs>
      <ellipse cx="380" cy="230" rx="222" ry="195" fill={`url(#${id}-iris)`} />
      <g className="eye-roadwork" fill="none" stroke={`url(#${id}-edge)`}>
        {networkPaths.map((d,i) => <path key={d} d={d} pathLength="1" style={{ animationDelay: `${.48+i*.035}s` }} />)}
        <path className="eye-envelope" d="M45 230Q380 -63 715 230Q380 523 45 230Z" />
      </g>
      <g className="eye-junctions">{nodes.map(([x,y],i) => <g key={i}><circle cx={x} cy={y} r={i%4===0 ? 3 : 2} /><circle className={i%7===0 ? "eye-node-pulse" : "eye-node-ring"} cx={x} cy={y} r="6" style={{animationDelay:`${i*-.31}s`}} /></g>)}</g>
      <g className="eye-trajectories" fill="none"><path d="M45 230 132 142 216 142 279 83 380 83" pathLength="100"/><path d="M715 230 632 285 540 356 457 356 380 377" pathLength="100" /></g>
      <g transform="translate(380 230)">
        <g className="eye-iris-track">
          <g className="eye-iris-reveal">
            <circle r="120" className="iris-boundary" />
            <g className="iris-ticks">{Array.from({length:72},(_,i)=><line key={i} x1="0" y1={i%6===0?-120:-117} x2="0" y2="-111" transform={`rotate(${i*5})`} />)}</g>
            <g className="iris-orbit"><circle r="103" className="iris-orbit-line"/><path d="M-103 0A103 103 0 0 1 0-103M103 0A103 103 0 0 1 0 103" className="iris-arc"/><circle cx="0" cy="-103" r="3" className="iris-satellite"/></g>
            <g className="iris-counter"><circle r="87"/><path d="M-87 0A87 87 0 0 1 0-87"/><circle cx="87" cy="0" r="2"/></g>
            <g className="iris-response"><path d="M-68-38A78 78 0 0 1 68-38M68 38A78 78 0 0 1-68 38"/><path className="iris-focus-brackets" d="M-57-40v-17h17M40-57h17v17M57 40v17H40M-40 57h-17V40"/></g>
            <circle className="iris-inner" r="61"/>
            <g className="iris-core"><circle r="44" className="iris-dark"/><circle r="30" className="iris-core-ring"/><path d="M-17 0h9M8 0h9M0-17v9M0 8v9" className="iris-crosshair"/><circle r="3.5" className="intelligence-point"/><circle r="10" className="intelligence-halo"/></g>
          </g>
        </g>
        <circle r="110" className="eye-success-wave"/>
        <path d="M-190 0H190" className="eye-success-scan"/>
      </g>
      <g className="eye-annotation"><path d="M380 32v26M380 402v26M12 230h19M729 230h19"/><text x="380" y="22" textAnchor="middle">CAMERA VISION / HUMAN JUDGMENT</text><text x="380" y="447" textAnchor="middle">CONNECTED BY INTELLIGENCE</text></g>
    </svg>
  </div>;
}
