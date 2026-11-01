"""Audit a complete matrix, including observed backup forwarding and reception."""
import argparse
import json
from pathlib import Path
import re


def load(path):
    return json.loads(path.read_text())


def audit(root, trials=3):
    root = Path(root)
    count = 0
    for trial in range(1,trials+1):
        for scenario in ('normal','loss','link_failure'):
            for mode in ('static','dynamic'):
                directory = root/('%s-%s-%d' % (scenario,mode,trial))
                meta = load(directory/'experiment.json')
                assert meta['valid'], str(directory)+': invalid experiment'
                assert (meta['mode'],meta['scenario'],meta['seed']) == (mode,scenario,trial)
                receiver = load(directory/'receiver.json')
                assert receiver['invalid'] == receiver['rejected'] == 0
                sessions = {s['transfer']:s for s in receiver['sessions']}
                for client in (1,2):
                    data = load(directory/('client%d.json' % client))
                    session = sessions[data['transfer']]
                    if mode == 'dynamic' or scenario == 'normal':
                        assert data['complete'] and session['complete'], str(directory)+': incomplete delivery'
                        assert data['acked'] == session['unique'] == meta['packets']
                    elif scenario == 'link_failure':
                        assert not data['complete'] and data['failed'] > 0
                    if scenario == 'loss':
                        assert data['retransmissions'] > 0
                controller = meta['controller']
                backup = mode == 'dynamic' and scenario != 'normal'
                assert controller['path'] == ('backup' if backup else 'primary')
                assert controller['pending_barriers'] == 0
                destination = 's1-eth4' if backup else 's1-eth3'
                lines = meta['flows']['1'].splitlines()
                server_rule = next(line for line in lines if 'dl_dst=00:00:00:00:00:02' in line)
                assert 'actions=output:"%s"' % destination in server_rule, server_rule
                if backup:
                    assert controller['switch_completed_wall'] >= meta['fault_wall']
                    for mac in ('01','03'):
                        rule = next(line for line in meta['flows']['4'].splitlines()
                            if 'dl_dst=00:00:00:00:00:'+mac in line)
                        assert 'actions=output:"s4-eth2"' in rule, rule
                    transit = next(line for line in meta['flows']['3'].splitlines()
                        if 'dl_dst=00:00:00:00:00:02' in line)
                    assert int(re.search(r'n_packets=(\d+)',transit).group(1)) > 0
                    reasons = {event.get('reason') for event in controller['events']}
                    if scenario == 'loss':
                        assert 'application_loss' in reasons
                    else:
                        assert reasons & {'primary_link_down','monitored_primary_link_down'}
                if scenario == 'loss':
                    drops = [int(n) for n in re.findall(r'dropped (\d+)',meta['tc_stats'])]
                    assert drops and max(drops) > 0, 'loss injection did not drop packets'
                count += 1
    print('AUDIT PASSED: %d real Mininet experiments, forwarding paths and receiver outcomes verified.' % count)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--trials',type=int,default=3)
    args = parser.parse_args()
    audit(args.root,args.trials)
