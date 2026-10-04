"""Recalculate saved aggregate comparisons offline; never train a model."""
from __future__ import annotations
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(root, name):
    return json.loads((root / 'data/aggregates' / (name + '.json')).read_text())

def csv_text(rows):
    out = io.StringIO(newline='')
    w = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator='\n')
    w.writeheader(); w.writerows(rows)
    return out.getvalue()

def calculate(root=ROOT):
    one = load(root, 'kisa_one_example_20261004')
    allm = load(root, 'kisa_all_models_summary_20261004')
    few = load(root, 'kisa_few_example_20261004')
    one_rows, all_rows, few_rows = [], [], []
    for fold in one['folds']:
        for step, x in fold['steps'].items():
            h, n, r = x['held_out_misses'], x['normal_regression'], x['retention']
            assert h['recovered_count'] == len(h['recovered_cases'])
            assert r['denominator'] == r['retained_count'] + r['newly_missed_count']
            assert n['total_alerts'] == n['baseline_alerts'] + n['new_alerts'] - n['resolved_alerts']
            assert x['summary_22_cases']['detected_count'] == int(x['support']['learned']) + h['recovered_count'] + r['retained_count']
            one_rows.append(dict(support=fold['support_case_id'], updates=int(step), learned=x['support']['learned'], recovered=h['recovered_count'], miss_denominator=h['denominator'], retained=r['retained_count'], new_misses=r['newly_missed_count'], normal_alerts=n['total_alerts'], normal_denominator=n['denominator'], new_normal_alerts=n['new_alerts'], clean_recovery=x['verdicts']['clean_recovery']))
    for model in allm['models']:
        for fold in model['folds']:
            for step, x in fold['steps'].items():
                clean = x['recovered'] > 0 and x['new_misses'] == 0 and x['new_normal_alerts'] == 0
                assert clean == x['clean_recovery']
                assert 0 <= x['recovered'] <= x['miss_denominator']
                assert x['normal_alerts'] == model['baseline_normal_alerts'] + x['new_normal_alerts'] - x['resolved_normal_alerts']
                all_rows.append(dict(model=model['id'], family=model['family'], support=fold['support'], updates=int(step), support_was_missed=not fold['support_baseline_detected'], support_detected=x['support_detected'], recovered=x['recovered'], miss_denominator=x['miss_denominator'], new_misses=x['new_misses'], normal_alerts=x['normal_alerts'], new_normal_alerts=x['new_normal_alerts'], clean_recovery=clean))
    for step in ('1', '5', '10'):
        rows = [r for r in all_rows if r['updates'] == int(step)]
        t = allm['stage_totals'][step]
        assert len(rows) == t['observations']
        assert sum(r['clean_recovery'] for r in rows) == t['clean_recovery_observations']
        assert sum(r['clean_recovery'] and r['support_was_missed'] for r in rows) == t['support_was_missed_clean_recovery_observations']
    for model in few['models']:
        for group in model['groups']:
            for step, x in group['steps'].items():
                m = x['metrics']
                clean = m['recovered'] > 0 and m['new_misses'] == 0 and m['new_normal_alerts'] == 0
                assert clean == m['clean_recovery']
                assert m['heldout_count'] == 22 - group['size'] - len(group['collisions'])
                assert m['normal_alerts'] == m['baseline_normal_alerts'] + m['new_normal_alerts'] - m['resolved_normal_alerts']
                assert 0 <= m['recovered'] <= m['miss_denominator']
                few_rows.append(dict(model=model['id'], family=model['family'], support_group=group['group_id'], learned_examples=group['size'], updates=int(step), support_detected=m['support_detected'], recovered=m['recovered'], miss_denominator=m['miss_denominator'], common_recovered=m['common_recovered'], common_denominator=m['common_denominator'], new_misses=m['new_misses'], normal_alerts=m['normal_alerts'], new_normal_alerts=m['new_normal_alerts'], clean_recovery=clean))
    for size in ('2', '3'):
        for step in ('1', '5', '10'):
            rows = [r for r in few_rows if r['learned_examples'] == int(size) and r['updates'] == int(step)]
            assert len(rows) == few['totals'][size][step]['observations']
            assert sum(r['clean_recovery'] for r in rows) == few['totals'][size][step]['clean_recovery']
    final = [r for r in one_rows if r['updates'] == one['overall_summary']['primary_step']]
    summary = {
        'role': 'saved_aggregate_recalculation_not_new_inference',
        'baseline': one['baseline_summary'],
        'one_example': {'folds': len(final), 'untrained_recovered_range': [min(r['recovered'] for r in final), max(r['recovered'] for r in final)], 'normal_alert_range': [min(r['normal_alerts'] for r in final), max(r['normal_alerts'] for r in final)], 'clean_recovery': sum(r['clean_recovery'] for r in final)},
        'all_model_conditions': allm['all_conditions'],
        'all_models_primary': allm['stage_totals'][str(allm['primary_step'])],
        'few_example_primary': {s: few['totals'][s][str(few['primary_step'])] for s in ('2', '3')},
        'limitations': ['Known cases reused; not independent future campaigns', 'Normal candidates are development inputs, not operational FPR', 'Counts across folds are repeated observations, not unique SMS'],
    }
    return {'one_example.csv': csv_text(one_rows), 'all_models_one_example.csv': csv_text(all_rows), 'few_example.csv': csv_text(few_rows), 'summary.json': json.dumps(summary, ensure_ascii=False, indent=2)+'\n'}

def check(root=ROOT):
    files = calculate(root)
    for name, text in files.items():
        assert (root / 'data/derived' / name).read_text() == text, 'Derived result drift: '+name
    print(json.dumps(json.loads(files['summary.json']), ensure_ascii=False, indent=2))
    print('PASS: saved aggregate arithmetic and all comparison CSVs agree. No inference or training performed.')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--write', action='store_true', help='Write recalculated copies to local outputs/recalculated, never overwrite evidence');a=p.parse_args()
    check()
    if a.write:
        out=ROOT/'outputs/recalculated';out.mkdir(parents=True,exist_ok=True)
        for name,text in calculate().items():(out/name).write_text(text)
