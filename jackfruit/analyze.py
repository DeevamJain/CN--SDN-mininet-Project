"""Summarize only completed, valid Mininet experiments; never synthesize results."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def analyze(root):
    root = Path(root)
    rows = []
    for path in sorted(root.glob('*/experiment.json')):
        meta = json.loads(path.read_text())
        if not meta.get('valid'):
            continue
        sessions = {s['transfer']: s for s in
                    json.loads((path.parent/'receiver.json').read_text())['sessions']}
        complete_wall = meta['controller'].get('switch_completed_wall')
        for client in sorted(path.parent.glob('client[12].json')):
            data = json.loads(client.read_text())
            reception = sessions[data['transfer']]
            row = {key: data[key] for key in ['acked','failed','initial_sent','unsent','retransmissions',
                'first_attempt_timeout_ratio','final_unacked_ratio','goodput_bps',
                'duration_s','rtt_p50_ms','rtt_p95_ms',
                'first_retransmitted_ack_after_detection_s']}
            row.update(run=path.parent.name, client=client.stem, mode=meta['mode'],
                       scenario=meta['scenario'], seed=meta['seed'])
            row.update(receiver_unique=reception['unique'], receiver_missing=reception['missing'],
                receiver_duplicates=reception['duplicates'],
                received_datagrams=reception['received_datagrams'],
                observed_forward_datagram_deficit=max(0,data['sent_datagrams']-reception['received_datagrams']))
            row['fault_to_barriers_s'] = (complete_wall-meta['fault_wall']) if complete_wall else None
            # Cohorts are defined by first-send time. Timeout is an ACK-based loss
            # indicator, not a one-way wire-loss measurement.
            for phase in ('before_fault','during_recovery','after_recovery'):
                packets = []
                for packet in data['packet_records']:
                    sent_wall = data['start_wall']+packet['first_sent_s']
                    selected = ('before_fault' if sent_wall < meta['fault_wall'] else
                                'after_recovery' if complete_wall and sent_wall >= complete_wall else
                                'during_recovery')
                    if phase == selected:
                        packets.append(packet)
                row[phase+'_packets'] = len(packets)
                row[phase+'_timeout_ratio'] = (sum(p['first_timeout'] for p in packets)/len(packets)
                                               if packets else None)
            rows.append(row)
    if not rows:
        raise ValueError('no valid Mininet experiments; no report generated')
    with open(root/'summary.csv','w',newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Measured Mininet results', '',
        'Timeout ratios are missing-ACK indicators, not direct wire-loss rates.', '',
        '| Scenario | Mode | Runs | Mean goodput (bit/s) | Mean final unacked ratio |',
        '|---|---|---:|---:|---:|']
    for scenario, mode in sorted({(r['scenario'],r['mode']) for r in rows}):
        values = [r for r in rows if r['scenario']==scenario and r['mode']==mode]
        lines.append('| %s | %s | %d | %.1f | %.4f |' % (scenario, mode,
            len({r['run'] for r in values}), statistics.mean(r['goodput_bps'] for r in values),
            statistics.mean(r['final_unacked_ratio'] for r in values)))
    lines.extend(['', '| Scenario | Mode | Mean retransmissions/client | Mean initial timeout ratio | Mean fault-to-barriers (s) |',
                  '|---|---|---:|---:|---:|'])
    for scenario, mode in sorted({(r['scenario'],r['mode']) for r in rows}):
        values = [r for r in rows if r['scenario']==scenario and r['mode']==mode]
        recoveries = [r['fault_to_barriers_s'] for r in values if r['fault_to_barriers_s'] is not None]
        lines.append('| %s | %s | %.2f | %.4f | %s |' % (scenario, mode,
            statistics.mean(r['retransmissions'] for r in values),
            statistics.mean(r['first_attempt_timeout_ratio'] for r in values),
            '%.4f' % statistics.mean(recoveries) if recoveries else '—'))
    lines.extend(['', 'ACK-timeout cohorts (packet counts and weighted ratios):', '',
        '| Scenario | Mode | Before fault: n / ratio | During recovery: n / ratio | After barriers: n / ratio |',
        '|---|---|---:|---:|---:|'])
    for scenario, mode in sorted({(r['scenario'],r['mode']) for r in rows}):
        values = [r for r in rows if r['scenario']==scenario and r['mode']==mode]
        cohorts = []
        for phase in ('before_fault','during_recovery','after_recovery'):
            count = sum(r[phase+'_packets'] for r in values)
            timeouts = sum((r[phase+'_timeout_ratio'] or 0)*r[phase+'_packets'] for r in values)
            cohorts.append('%d / %.4f' % (count,timeouts/count) if count else '0 / —')
        lines.append('| %s | %s | %s |' % (scenario,mode,' | '.join(cohorts)))
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root')
    analyze(p.parse_args().root)


if __name__ == '__main__':
    main()
