"""Run inside the OCR pod to remove WAN/port-forward/S3 from engine measurements.

Requires httpx (already present in the serving images). Does not retry failed requests.
Saves response content hashes, output sizes, page coverage, raw metrics, and timings.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

def metric_values(text):
    result = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            key, value = line.rsplit(" ", 1)
            result[key] = float(value)
        except ValueError:
            pass
    return result

async def main(a):
    root = Path(a.data)
    output = Path(a.out) / a.name
    output.mkdir(parents=True, exist_ok=False)
    tasks = json.loads((root / a.workload).read_text())
    if a.limit:
        tasks = tasks[:a.limit]
    # Read and encode input before timed execution.
    encoded_files = {
        filename: base64.b64encode((root/filename).read_bytes()).decode()
        for filename in dict.fromkeys(task["file"] for task in tasks)
    }
    prepared = [(task, encoded_files[task["file"]]) for task in tasks]
    extra = json.loads(a.request_options)
    targets = a.urls.split(',') if a.urls else [a.url]
    results, snapshots = [], []
    stop = asyncio.Event()
    async with httpx.AsyncClient(timeout=7200, limits=httpx.Limits(max_connections=max(32,a.concurrency+8))) as client:
        async def metrics(full=False):
            snapshot = {"time": time.time()}
            for target in targets:
                host=urlsplit(target).hostname
                for name, port in [("triton",8002),("vlm",8118)]:
                    try:
                        r = await client.get(f"http://{host}:{port}/metrics", timeout=5)
                        r.raise_for_status()
                        values = metric_values(r.text)
                        if not full:
                            values = {k:v for k,v in values.items()
                                      if k.startswith(('vllm:', 'nv_'))
                                      and not k.split('{')[0].endswith(('_bucket','_created'))}
                        if len(targets)>1:
                            values = {(k.replace('{', '{bench_engine="'+host+'",',1) if '{' in k
                                       else k+'{bench_engine="'+host+'"}'):v for k,v in values.items()}
                        snapshot.setdefault(name,{}).update(values)
                    except Exception as exc:
                        snapshot[name+"_error_"+host] = repr(exc)
            snapshots.append(snapshot)
            with (output/"metrics.jsonl").open("a") as f:
                f.write(json.dumps(snapshot)+"\n")
        async def monitor():
            while not stop.is_set():
                await metrics()
                try:
                    await asyncio.wait_for(stop.wait(),2)
                except asyncio.TimeoutError:
                    pass
        await metrics(full=True)
        monitor_task = asyncio.create_task(monitor())
        semaphore = asyncio.Semaphore(a.concurrency)
        started = time.time()
        async def run(index, task, encoded):
            async with semaphore:
                begin = time.time()
                target=targets[index%len(targets)]
                result = dict(index=index, **task, started=begin, target=target)
                try:
                    response = await client.post(target+"/layout-parsing", json={
                        "file":encoded,"fileType":0,"useDocOrientationClassify":False,
                        "useDocUnwarping":False,"visualize":False,"returnMarkdownImages":True,**extra})
                    received = time.time()
                    result.update(http_status=response.status_code, response_bytes=len(response.content),
                                  http_seconds=received-begin)
                    payload = response.json()
                    pages = payload.get("result",{}).get("layoutParsingResults",[])
                    result.update(error_code=payload.get("errorCode",0), returned_pages=len(pages),
                                  markdown_chars=sum(len(x.get("markdown",{}).get("text","")) for x in pages),
                                  markdown_lengths=[len(x.get("markdown",{}).get("text","")) for x in pages],
                                  markdown_hashes=[hashlib.sha256(x.get("markdown",{}).get("text","").encode()).hexdigest() for x in pages],
                                  empty_pages=sum(not x.get("markdown",{}).get("text","").strip() for x in pages))
                    result["ok"] = response.status_code==200 and result["error_code"]==0 and len(pages)==task["pages"]
                    if not result["ok"]:
                        result["error"] = str(payload)[:2000]
                    if a.save_outputs:
                        (output/f"response-{index:04d}.json").write_text(json.dumps(payload))
                except Exception as exc:
                    result.update(ok=False,error=repr(exc))
                result.update(finished=time.time(), seconds=time.time()-begin)
                results.append(result)
                with (output/"requests.jsonl").open("a") as f:
                    f.write(json.dumps(result)+"\n")
                print(json.dumps({k:result.get(k) for k in ["index","file","pages","seconds","ok","returned_pages","error"]}),flush=True)
        await asyncio.gather(*(run(i,*x) for i,x in enumerate(prepared)))
        finished = time.time()
        stop.set()
        await monitor_task
        await metrics(full=True)
    durations = sorted(x["seconds"] for x in results)
    success = [x for x in results if x["ok"]]
    summary = dict(name=a.name, options=vars(a), started=started, finished=finished,
                   wall_seconds=finished-started, requests=len(results), failures=len(results)-len(success),
                   pages=sum(x["pages"] for x in success), attempted_pages=sum(x["pages"] for x in results),
                   pages_per_second=sum(x["pages"] for x in success)/(finished-started),
                   latency_p50=statistics.median(durations),
                   latency_p95=durations[max(0,math.ceil(.95*len(durations))-1)],
                   latency_max=max(durations), markdown_chars=sum(x.get("markdown_chars",0) for x in success))
    for service in ["triton","vlm"]:
        first,last = snapshots[0].get(service,{}),snapshots[-1].get(service,{})
        summary[service+"_deltas"] = {k:v-first.get(k,0) for k,v in last.items()
              if any(s in k.split('{')[0] for s in ["_total","_sum","_count","_duration_us","_success","_failure"])
              and not k.split('{')[0].endswith("_created")}
    summary['metric_error_samples']=sum(any('_error_' in k for k in row) for row in snapshots)
    summary['model_counter_reset']=any(v<0 for service in ['triton','vlm']
        for k,v in summary[service+'_deltas'].items() if k.startswith(('vllm:','nv_inference_')))
    observed=sum(v for k,v in summary['triton_deltas'].items()
        if k.split('{')[0] in ['nv_inference_request_success','nv_inference_request_failure']
        and 'model="layout-parsing"' in k)
    summary['triton_requests_observed']=observed
    summary['request_accounting_difference']=observed-len(results)
    (output/"summary.json").write_text(json.dumps(summary,indent=2))
    print("SUMMARY",json.dumps({k:v for k,v in summary.items() if not k.endswith("_deltas")}),flush=True)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="/tmp/paddle-bench/data")
    p.add_argument("--out",default="/tmp/paddle-bench/results")
    p.add_argument("--workload",default="sample-10.json")
    p.add_argument("--name",required=True)
    p.add_argument("--concurrency",type=int,default=3)
    p.add_argument("--url",default="http://127.0.0.1:8080")
    p.add_argument("--urls",default="",help="Comma-separated direct pod URLs for a multiple-engine trial")
    p.add_argument("--request-options",default="{}")
    p.add_argument("--limit",type=int,default=0)
    p.add_argument("--save-outputs",action="store_true")
    asyncio.run(main(p.parse_args()))
