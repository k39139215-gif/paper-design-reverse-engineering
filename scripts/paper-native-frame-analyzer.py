"""Analyze explicit PresentMon v2 CSVs without pooling separate swapchains."""
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def stats(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return {
        'count': len(values),
        'mean': statistics.fmean(values) if values else None,
        'p50': percentile(values, .5),
        'p95': percentile(values, .95),
        'p99': percentile(values, .99),
        'min': min(values) if values else None,
        'max': max(values) if values else None,
    }


run = Path(sys.argv[1]).resolve()
metadata = json.loads((run / 'capture-metadata.json').read_text(encoding='utf-8-sig'))
output = {
    'runDirectory': str(run),
    'collectorVersion': metadata['collectorVersion'],
    'administrator': metadata['administrator'],
    'schemaSource': 'https://github.com/GameTechDev/PresentMon/blob/v2.6.0/README-ConsoleApplication.md',
    'meaning': 'ETW graphics presentations attributed to Paper.exe; not a physical camera measurement or proof each frame changed artwork',
    'phases': [],
}
for phase in metadata['phaseResults']:
    path = Path(phase['csvPath'])
    out = {
        'name': phase['name'],
        'requestedSeconds': phase['seconds'],
        'collectorElapsedMs': phase['elapsedMs'],
        'exitCode': phase.get('exitCode'),
        'reportedStatus': phase['status'],
        'stderr': phase.get('stderr'),
    }
    if not path.is_file():
        out.update(status='unmeasured-no-csv', reason='No recorded frames; do not infer zero FPS or successful smooth interaction')
        output['phases'].append(out)
        continue
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    out['rowCount'] = len(rows)
    out['columns'] = list(rows[0]) if rows else []
    groups = defaultdict(list)
    for row in rows:
        key = (row.get('Application'), row.get('ProcessID'), row.get('SwapChainAddress'),
               row.get('VidPnSourceId'), row.get('LayerIndex'))
        groups[key].append(row)
    out['groups'] = []
    for key, group in groups.items():
        group.sort(key=lambda r: number(r.get('CPUStartQPCTime')) or 0)
        displayed = [r for r in group if number(r.get('DisplayedTime')) is not None]
        times = [number(r['CPUStartQPCTime']) + number(r['DisplayLatency']) for r in displayed
                 if number(r.get('CPUStartQPCTime')) is not None and number(r.get('DisplayLatency')) is not None]
        # Display latency is from CPU start, so this reconstructs ETW first-display time.
        times.sort()
        intervals = [b - a for a, b in zip(times, times[1:])]
        duplicates = sum(v == 0 for v in intervals)
        positive = [v for v in intervals if v > 0]
        span_ms = times[-1] - times[0] if len(times) > 1 else 0
        bins = Counter(int((time - times[0]) // 1000) for time in times) if times else Counter()
        present_start = [number(r.get('CPUStartQPCTime')) for r in group]
        present_start = [t for t in present_start if t is not None]
        display_duration = [number(r.get('DisplayedTime')) for r in displayed]
        display_sum = sum(v for v in display_duration if v is not None)
        out['groups'].append({
            'application': key[0], 'processId': key[1], 'swapchain': key[2],
            'displaySourceId': key[3], 'layerIndex': key[4],
            'presentRuntimes': dict(Counter(r.get('PresentRuntime') for r in group)),
            'presentModes': dict(Counter(r.get('PresentMode') for r in group)),
            'presentedRows': len(group), 'displayedRows': len(displayed),
            'notDisplayedRows': len(group) - len(displayed),
            'notDisplayedFraction': (len(group) - len(displayed)) / len(group),
            'presentSpanMs': max(present_start) - min(present_start) if len(present_start) > 1 else None,
            'displaySpanMs': span_ms,
            'intervalRateWithinObservedSpan': (len(times) - 1) * 1000 / span_ms if span_ms else None,
            'displayedRowsPerRequestedSecond': len(displayed) / phase['seconds'],
            'displayedDurationSumMs': display_sum,
            'rateFromDisplayedDuration': len(displayed) * 1000 / display_sum if display_sum else None,
            'sameTimestampIntervals': duplicates,
            'displayIntervalsMs': stats(positive),
            'intervalsOver33_333ms': sum(v > 1000 / 30 for v in positive),
            'intervalsOver50ms': sum(v > 50 for v in positive),
            'intervalsOver100ms': sum(v > 100 for v in positive),
            'displayedTimeMs': stats(display_duration),
            'displayLatencyMs': stats([number(r.get('DisplayLatency')) for r in displayed]),
            'cpuFrameTimeMs': stats([number(r.get('FrameTime')) for r in group]),
            'gpuBusyMs': stats([number(r.get('GPUBusy')) for r in group]),
            'oneSecondCountsFromFirstObservedDisplay': dict(sorted(bins.items())),
        })
    out['status'] = 'native-presentations-analyzed' if rows else 'unmeasured-empty-csv'
    output['phases'].append(out)
destination = run / 'analysis.json'
destination.write_text(json.dumps(output, indent=2), encoding='utf-8')
print(json.dumps(output, indent=2))
