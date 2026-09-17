"""Measure first-content and decoding latency for a fixed captured crop."""
import argparse, asyncio, copy, hashlib, json, time, uuid
from pathlib import Path
import httpx

async def main(a):
    groups = sorted((json.loads(p.read_text()) for p in Path(a.crops).glob('*.json')), key=lambda g:g['created'])
    specs = [s for g in groups for s in g['specs']]
    messages, kwargs = copy.deepcopy(specs[a.index])
    salt = uuid.uuid4().hex
    for m in messages:
        for p in m['content']:
            if p.get('type') == 'image_url': p['uuid'] = salt
    body = kwargs; body.update(body.pop('extra_body', {}))
    body.update(messages=messages, model='PaddleOCR-VL-1.6-0.9B', cache_salt=salt,
                stream=True, stream_options={'include_usage':True})
    chunks=[]; content=[]; usage={}; finish=None
    async with httpx.AsyncClient(timeout=300) as client:
        start=time.time()
        async with client.stream('POST',a.url+'/v1/chat/completions',json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith('data: ') or line=='data: [DONE]': continue
                payload=json.loads(line[6:])
                if payload.get('usage'): usage=payload['usage']
                for choice in payload.get('choices',[]):
                    text=choice.get('delta',{}).get('content') or ''
                    if text: chunks.append(time.time()); content.append(text)
                    if choice.get('finish_reason'): finish=choice['finish_reason']
        end=time.time()
    result=dict(index=a.index,started=start,first_content=chunks[0],finished=end,
                ttft_seconds=chunks[0]-start,decode_seconds=end-chunks[0],wall_seconds=end-start,
                usage=usage,finish_reason=finish,chunk_times=chunks,text=''.join(content))
    Path(a.output).write_text(json.dumps(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ['text','chunk_times']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--crops',default='/tmp/paddle-bench-crops');p.add_argument('--index',type=int,default=123)
    p.add_argument('--url',required=True);p.add_argument('--output',required=True)
    asyncio.run(main(p.parse_args()))
