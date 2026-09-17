"""Local controller for measured trials. Uses an existing runner and protected GPU node.

Example: python benchmark-experiment.py --kubeconfig ... --node ... --output ...
  --name p10-c3 --chunk 10 --concurrency 3
Requires benchmarkProfiling=true for a fresh prefix-cache namespace per trial.
"""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import time
import uuid

p=argparse.ArgumentParser()
p.add_argument('--kubeconfig',required=True)
p.add_argument('--node',required=True)
p.add_argument('--output',required=True)
p.add_argument('--name',required=True)
p.add_argument('--release',default='paddleocr-hps')
p.add_argument('--runner',default='paddle-benchmark-runner')
p.add_argument('--peer-release',action='append',default=[])
p.add_argument('--peer-node',help='Expected node for physical multi-GPU peers; defaults to the primary node')
p.add_argument('--data',default='/tmp/paddle-bench/data')
p.add_argument('--chunk',type=int,default=10)
p.add_argument('--concurrency',type=int,default=3)
p.add_argument('--full',action='store_true')
p.add_argument('--save-outputs',action='store_true')
p.add_argument('--request-options',default='{}')
a=p.parse_args()
k=['kubectl','--kubeconfig',a.kubeconfig]
out=Path(a.output)/a.name
out.mkdir(parents=True,exist_ok=False)
selected=[]
for release in [a.release]+a.peer_release:
    pods=json.loads(subprocess.check_output(k+['get','pods','-n','paddleocr','-l','app.kubernetes.io/instance='+release,'-o','json']))['items']
    expected_node=a.node if release==a.release else (a.peer_node or a.node)
    pods=[pod for pod in pods if pod['spec'].get('nodeName')==expected_node and not pod['metadata'].get('deletionTimestamp')]
    assert len(pods)==1, 'Expected exactly one OCR pod per release on the preserved node'
    pod=pods[0]
    assert any(x['type']=='Ready' and x['status']=='True' for x in pod['status']['conditions']), 'OCR pod is not ready'
    selected.append(pod)
pod=selected[0]
salt=uuid.uuid4().hex
for target in selected:
    remote=k+['exec','-n','paddleocr',target['metadata']['name'],'-c','pipeline','--']
    subprocess.run(remote+['python','-c',f"open('/tmp/paddle-bench-cache-salt','w').write({salt!r})"],check=True)
(out/'pod.json').write_text(json.dumps(pod,indent=2))
(out/'pods.json').write_text(json.dumps(selected,indent=2))
(out/'trial.json').write_text(json.dumps(dict(options=vars(a),cache_salt=salt,start=time.time()),indent=2))
command=k+['exec','-n','paddleocr',a.runner,'--','python','/tmp/benchmark-run.py',
    '--name',a.name,'--url',f"http://{pod['status']['podIP']}:8080",'--concurrency',str(a.concurrency),
    '--workload','full.json' if a.full else f'sample-{a.chunk}.json', '--request-options',a.request_options,'--data',a.data]
if len(selected)>1:
    command+=['--urls',','.join(f"http://{target['status']['podIP']}:8080" for target in selected)]
if a.save_outputs or a.full: command+=['--save-outputs']
with (out/'progress.log').open('w') as f:
    result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
for filename in ['summary.json','requests.jsonl','metrics.jsonl']:
    data=subprocess.run(k+['exec','-n','paddleocr',a.runner,'--','gzip','-c',
                         f'/tmp/paddle-bench/results/{a.name}/{filename}'],capture_output=True)
    if data.returncode==0:
        temporary=out/(filename+'.tmp')
        temporary.write_bytes(gzip.decompress(data.stdout))
        temporary.replace(out/filename)
if result.returncode: raise SystemExit(result.returncode)
summary=json.loads((out/'summary.json').read_text())
print(json.dumps({k:v for k,v in summary.items() if not k.endswith('_deltas')},indent=2),flush=True)
