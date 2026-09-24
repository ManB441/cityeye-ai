const roads = [
  "M-40 170H180L280 270H470L620 420H910L1100 230H1240",
  "M80 -40V110L330 360V560L110 780V950",
  "M420 -40V150L550 280V510L740 700V950",
  "M820 -40V160L700 280V470L930 700H1250",
  "M-40 610H170L300 480H580L810 250H1200",
  "M-40 830H340L540 630H900L1130 400H1240",
  "M1080 -40V90L940 230V470L1080 610V950",
];
const intersections = [[180,170],[280,270],[330,360],[330,560],[110,780],[420,150],[550,280],[550,510],[740,700],[820,160],[700,280],[930,700],[170,610],[300,480],[810,250],[540,630],[900,630],[1080,610]];
export function CityNetworkBackground() {
  return <svg className="city-network" viewBox="0 0 1200 900" preserveAspectRatio="none" aria-hidden="true">
    <g className="city-roads">{roads.map(d => <path key={d} d={d} />)}</g>
    <g className="city-blocks"><path d="M40 280h110l90 90v70H40zM405 355h90v125h-90zM610 70h120v100l-70 70h-50zM700 750h180v110H700zM960 280h90v120l-90 90z" /></g>
    {intersections.map(([x,y], index) => <g key={index} data-city-region="" data-x={x} data-y={y} className="city-region">
      <path d={`M${x-35} ${y}H${x+35}M${x} ${y-28}V${y+28}`} />
      <circle cx={x} cy={y} r="2.4" />
      {index % 5 === 0 && <circle className="city-beacon" cx={x} cy={y} r="6" style={{ animationDelay: `${index * -.7}s` }} />}
    </g>)}
    <g className="city-signals"><path d={roads[0]} pathLength="100" /><path d={roads[4]} pathLength="100" /></g>
  </svg>;
}
