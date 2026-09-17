"""Build a compact table from recorded trials (stdlib only)."""
import argparse
import csv
import json
from pathlib import Path
import statistics

p=argparse.ArgumentParser()
p.add_argument('directory')
a=p.parse_args()
root=Path(a.directory)
rows=[]
for path in sorted(root.glob('*/summary.json')):
    s=json.loads(path.read_text())
    def delta(name,service='vlm',required=''):
        return sum(v for k,v in s.get(service+'_deltas',{}).items()
                   if k.split('{')[0]==name and required in k)
    duration=s['wall_seconds']
    r={k:s[k] for k in ['name','pages','wall_seconds','pages_per_second','latency_p50','latency_p95','failures']}
    r.update(concurrency=s['options']['concurrency'],workload=s['options']['workload'],
             generation_tokens_per_second=delta('vllm:generation_tokens_total')/duration,
             prompt_tokens_per_second=delta('vllm:prompt_tokens_total')/duration,
             crop_requests=delta('vllm:request_success_total'),
             output_token_limit_hits=delta('vllm:request_success_total',required='finished_reason="length"'),
             preemptions=delta('vllm:num_preemptions_total'),
             prefix_hit_fraction=delta('vllm:prefix_cache_hits_total')/max(1,delta('vllm:prefix_cache_queries_total')),
             triton_queue_seconds_per_request=delta('nv_inference_queue_duration_us','triton','layout-parsing')/max(1,s['requests'])/1e6,
             triton_compute_seconds_per_request=delta('nv_inference_compute_infer_duration_us','triton','layout-parsing')/max(1,s['requests'])/1e6)
    metrics=path.parent/'metrics.jsonl'
    for name in ['num_requests_running','num_requests_waiting','kv_cache_usage_perc']:
        r[name+'_mean']=float('nan')
        r[name+'_max']=float('nan')
    if metrics.exists():
        values=[json.loads(line).get('vlm',{}) for line in metrics.read_text().splitlines()]
        for name in ['num_requests_running','num_requests_waiting','kv_cache_usage_perc']:
            aggregate=(lambda vs:max(vs,default=0)) if name=='kv_cache_usage_perc' else sum
            series=[aggregate([v for k,v in sample.items() if k.split('{')[0]=='vllm:'+name]) for sample in values]
            r[name+'_mean']=statistics.mean(series) if series else 0
            r[name+'_max']=max(series,default=0)
    rows.append(r)
if rows:
    with (root/'comparison.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    print(f"{'trial':30} {'pages/s':>8} {'p95 s':>8} {'GPU queue':>10} {'KV max':>8} {'cache hit':>10} {'trunc':>6}")
    for r in rows:
        print(f"{r['name']:30} {r['pages_per_second']:8.3f} {r['latency_p95']:8.1f} {r['num_requests_waiting_max']:10.0f} {r['kv_cache_usage_perc_max']:8.3f} {r['prefix_hit_fraction']:10.3f} {r['output_token_limit_hits']:6.0f}")
