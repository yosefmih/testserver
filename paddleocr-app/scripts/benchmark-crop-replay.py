"""Replay exact captured crop requests to isolate VLM capacity and group barriers.

Run in the benchmark runner. Profiled runs are diagnostic only, not throughput evidence.
"""
import argparse,asyncio,base64,copy,hashlib,io,json,math,statistics,time,uuid
from pathlib import Path
import httpx

async def main(a):
    groups=[]
    for f in sorted(Path(a.crops).glob('*.json')):
        d=json.loads(f.read_text());d['producer']=f.name.split('-')[0];d['source']=f.name;groups.append(d)
    groups.sort(key=lambda d:d['created'])
    salt=uuid.uuid4().hex;tasks=[];by_producer={}
    for g in groups:
        items=[]
        for messages,kwargs in g['specs']:
            messages=copy.deepcopy(messages)
            if a.fresh_images:
                for message in messages:
                    for part in message.get('content',[]):
                        if part.get('type')=='image_url':part['uuid']=salt+':'+str(len(tasks))
            body=copy.deepcopy(kwargs);body.update(body.pop('extra_body',{}));body['cache_salt']=salt
            body.update(model=a.model,messages=messages)
            item={'index':len(tasks),'group':g['source'],'body':body}
            if a.order=='pixels-desc':
                from PIL import Image
                part=next(p for m in messages for p in m['content'] if p['type']=='image_url')
                image=Image.open(io.BytesIO(base64.b64decode(part['image_url']['url'].split(',',1)[1])))
                item['pixels']=image.width*image.height
            tasks.append(item);items.append(item)
        by_producer.setdefault(g['producer'],[]).append(items)
    if a.repeat > 1:
        assert a.mode == 'pooled', 'Repeated workload is only supported for pooled replay'
        original=tasks;tasks=[]
        for repetition in range(a.repeat):
            for source in original:
                item=copy.deepcopy(source);item['index']=len(tasks)
                if a.fresh_images:
                    for message in item['body']['messages']:
                        for part in message.get('content',[]):
                            if part.get('type')=='image_url':part['uuid']=salt+':'+str(item['index'])
                tasks.append(item)
    out=Path(a.out)/a.name;out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps({'options':vars(a),'crops':len(tasks),'groups':len(groups),'producers':list(by_producer),'cache_salt':salt},indent=2))
    rows=[];snapshots=[];stop=asyncio.Event();sem=asyncio.Semaphore(a.concurrency)
    urls=a.urls.split(',') if a.urls else [a.url]
    async with httpx.AsyncClient(timeout=7200,limits=httpx.Limits(max_connections=a.concurrency+8)) as client:
        async def sample():
            async def one(endpoint):
                try:
                    response=await client.get(endpoint+'/metrics',timeout=10)
                    response.raise_for_status();d={'time':time.time(),'endpoint':endpoint,'text':response.text}
                except Exception as e:d={'time':time.time(),'endpoint':endpoint,'error':repr(e)}
                snapshots.append(d)
                with (out/'metrics.jsonl').open('a') as f:f.write(json.dumps(d)+'\n')
            await asyncio.gather(*(one(endpoint) for endpoint in urls))
        async def monitor():
            while not stop.is_set():
                await sample()
                try:await asyncio.wait_for(stop.wait(),.5)
                except asyncio.TimeoutError:pass
        async def profile():
            if a.profile_delay:await asyncio.sleep(a.profile_delay)
            response=await client.post(a.url+'/start_profile',timeout=120);response.raise_for_status()
            (out/'profile-start.json').write_text(json.dumps({'time':time.time(),'status':response.status_code}))
        async def run(item):
            async with sem:
                start=time.time();d={'index':item['index'],'group':item['group'],'started':start}
                try:
                    endpoint=urls[item['index']%len(urls)];d['endpoint']=endpoint
                    response=await client.post(endpoint+'/v1/chat/completions',json=item['body']);response.raise_for_status()
                    payload=response.json();choice=payload['choices'][0];content=choice['message'].get('content') or ''
                    d.update(ok=True,usage=payload.get('usage',{}),finish_reason=choice['finish_reason'],text=content,text_sha256=hashlib.sha256(content.encode()).hexdigest())
                except Exception as e:d.update(ok=False,error=repr(e))
                d.update(finished=time.time(),seconds=time.time()-start);rows.append(d)
                with (out/'requests.jsonl').open('a') as f:f.write(json.dumps(d)+'\n')
        async def producer(group_list):
            local_sem=asyncio.Semaphore(a.producer_concurrency)
            async def limited(item):
                async with local_sem:await run(item)
            for items in group_list:await asyncio.gather(*(limited(x) for x in items))
        await sample();m=asyncio.create_task(monitor())
        prof=asyncio.create_task(profile()) if a.profile else None
        if prof and not a.profile_delay:await prof
        started=time.time()
        if a.mode=='pooled':
            ordered=sorted(tasks,key=lambda x:-x['pixels']) if a.order=='pixels-desc' else tasks
            await asyncio.gather(*(run(x) for x in ordered))
        else:await asyncio.gather(*(producer(gs) for gs in by_producer.values()))
        finished=time.time();stop.set();await m;await sample()
        if prof:
            await prof
            response=await client.post(a.url+'/stop_profile',timeout=300)
            (out/'profile-stop.json').write_text(json.dumps({'time':time.time(),'status':response.status_code,'body':response.text[:1000]}))
    good=[d for d in rows if d['ok']];lat=sorted(d['seconds'] for d in rows)
    tokens=sum(d['usage'].get('completion_tokens',0) for d in good)
    summary={'name':a.name,'options':vars(a),'started':started,'finished':finished,'wall_seconds':finished-started,'crops':len(rows),'failures':len(rows)-len(good),'crops_per_second':len(good)/(finished-started),'generated_tokens':tokens,'output_tokens_per_second':tokens/(finished-started),'latency_p50':statistics.median(lat),'latency_p95':lat[math.ceil(.95*len(lat))-1],'length_finishes':sum(d.get('finish_reason')=='length' for d in rows)}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--crops',required=True);p.add_argument('--url',required=True);p.add_argument('--name',required=True)
    p.add_argument('--repeat',type=int,default=1,help='Repeat the captured crop sequence with unique image UUIDs for sustained-load tests')
    p.add_argument('--urls',help='Comma-separated engine URLs; stable round-robin by crop index')
    p.add_argument('--out',default='/tmp/paddle-bench/crop-results');p.add_argument('--model',default='PaddleOCR-VL-1.6-0.9B');p.add_argument('--concurrency',type=int,default=64)
    p.add_argument('--mode',choices=['pooled','grouped'],default='pooled');p.add_argument('--profile',action='store_true');p.add_argument('--profile-delay',type=float,default=0)
    p.add_argument('--producer-concurrency',type=int,default=64,help='Per-pipeline client concurrency in grouped mode')
    p.add_argument('--fresh-images',action='store_true',help='Assign unique image UUIDs to bypass cross-request GPU encoder cache reuse')
    p.add_argument('--order',choices=['original','pixels-desc'],default='original')
    asyncio.run(main(p.parse_args()))
