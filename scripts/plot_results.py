"""Optional standalone scientific figure from actual summary.csv (requires matplotlib)."""
import argparse
import csv
from pathlib import Path
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    args = parser.parse_args()
    with args.summary.open() as file:
        rows = list(csv.DictReader(file))
    scenarios = ['normal', 'loss', 'link_failure']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for ax, metric, scale, label in zip(axes,
        ['goodput_bps','final_unacked_ratio','retransmissions'],
        [1/1000,100,1], ['Goodput per client (kbit/s)','Final unacked (%)','Retransmissions per client']):
        for mode, offset, color in [('static',-.18,'#536878'),('dynamic',.18,'#15846b')]:
            means, deviations = [], []
            for scenario in scenarios:
                runs = {}
                for row in rows:
                    if row['mode']==mode and row['scenario']==scenario:
                        runs.setdefault(row['run'], []).append(float(row[metric])*scale)
                values = [statistics.mean(v) for v in runs.values()]
                if not values:
                    raise ValueError('missing measured scenario/mode: '+scenario+'/'+mode)
                means.append(statistics.mean(values))
                deviations.append(statistics.stdev(values) if len(values)>1 else 0)
            ax.bar([i+offset for i in range(3)], means, yerr=deviations,
                   width=.34, label=mode, color=color, capsize=3)
        ax.set_xticks(range(3), ['Normal','Loss','Link failure'])
        ax.set_ylabel(label)
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    axes[0].legend()
    fig.suptitle('Jackfruit: measured static versus dynamic SDN (error bars: trial standard deviation)')
    for extension in ('png','pdf'):
        fig.savefig(args.summary.with_name('comparison.'+extension), dpi=180)


if __name__ == '__main__':
    main()
