const fs = require('node:fs');
const path = require('node:path');
const files = process.argv.slice(2);
let trace = [];
let complete = false, truncated = false;
for (const file of files) {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const parts = data.parts || [data];
  for (const part of parts) {
    truncated ||= !!part.truncated;
    for (const block of part.events || []) {
      complete ||= block.method === 'Tracing.tracingComplete';
      trace.push(...(block.params?.value || []));
    }
  }
}
const quantile = (values, q) => {
  if (!values.length) return null;
  const ordered = [...values].sort((a,b) => a-b);
  return ordered[Math.min(ordered.length-1,Math.floor(q*(ordered.length-1)))];
};
const bounds = [Math.min(...trace.map(e => e.ts || Infinity)), Math.max(...trace.map(e => (e.ts || 0)+(e.dur || 0)))];
const byMarker = {};
for (const name of ['DrawFrame','BeginFrame','DroppedFrame','AnimationFrame::Presentation','Display::DrawAndSwap','SkiaRenderer::SwapBuffers']) {
  const groups = new Map();
  for (const e of trace.filter(e => e.name === name)) {
    const key = `${e.pid}/${e.tid}/${e.args?.layerTreeId || 'display'}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  byMarker[name] = [...groups.entries()].map(([key, events]) => {
    const times = [...new Set(events.map(e => e.ts))].sort((a,b) => a-b);
    const intervals = times.slice(1).map((t,i) => (t-times[i])/1000);
    return {key,count:events.length,uniqueTimes:times.length,spanSeconds:(times.at(-1)-times[0])/1e6,
      activeRate:times.length > 1 ? (times.length-1)*1e6/(times.at(-1)-times[0]) : null,
      intervalsMs:{p50:quantile(intervals,.5),p95:quantile(intervals,.95),p99:quantile(intervals,.99),max:intervals.length?Math.max(...intervals):null,
        over50:intervals.filter(t=>t>50).length,over100:intervals.filter(t=>t>100).length}};
  });
}
const result = {files,complete,truncated,eventCount:trace.length,traceSpanSeconds:(bounds[1]-bounds[0])/1e6,
  marks:trace.filter(e=>e.cat?.includes('user_timing')&&e.name.startsWith('paper-re-')).map(e=>({name:e.name,ts:e.ts,ph:e.ph})),byMarker};
console.log(JSON.stringify(result,null,2));
