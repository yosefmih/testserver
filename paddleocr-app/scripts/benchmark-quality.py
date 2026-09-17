"""Output consistency and embedded-PDF-text checks, NOT a ground-truth OCR accuracy score.

Runs locally using the benchmark runner's HTTP file server through a port-forward.
Reference PDFs can omit scanned text and contain headers intentionally ignored by OCR.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import unicodedata
import urllib.request

import pypdfium2 as pdfium

p=argparse.ArgumentParser()
p.add_argument('--results',required=True)
p.add_argument('--sample-pdf',required=True)
p.add_argument('--url',default='http://127.0.0.1:18089')
p.add_argument('--baseline',default='profile-c3-p10')
p.add_argument('--cache',default='/tmp/paddle-quality-cache')
p.add_argument('--data',default='/tmp/paddle-bench/data')
p.add_argument('--prefix',default='quality')
p.add_argument('--trial-prefix',default='',help='Only compare trials whose names start with this prefix')
a=p.parse_args()
root=Path(a.results);cache=Path(a.cache);cache.mkdir(parents=True,exist_ok=True)
def words(text):
    # Strip HTML markup but retain all table-cell text and numbers.
    text=re.sub(r'<[^>]*>',' ',text)
    return Counter(re.findall(r'\w+',unicodedata.normalize('NFKC',text).lower()))
def trigrams(text):
    text=re.sub(r'\s+','',unicodedata.normalize('NFKC',re.sub(r'<[^>]*>',' ',text)).lower())
    return Counter(text[i:i+3] for i in range(max(0,len(text)-2)))
def outputs(name):
    metadata=[json.loads(x) for x in (root/name/'requests.jsonl').read_text().splitlines()]
    pages={}
    for r in metadata:
        path=cache/name/f"response-{r['index']:04d}.json"
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            urllib.request.urlretrieve(a.url+'/results/'+name+'/'+path.name,str(path))
        payload=json.loads(path.read_text())
        start=int(Path(r['file']).stem)
        for i,page in enumerate(payload.get('result',{}).get('layoutParsingResults',[])):
            pages[start+i]=page['markdown']['text']
    return pages
doc=pdfium.PdfDocument(a.sample_pdf)
reference=[]
for page in doc:
    tp=page.get_textpage();reference.append(tp.get_text_range());tp.close();page.close()
doc.close()
baseline=outputs(a.baseline)
details=[];summary=[]
for directory in sorted(root.iterdir()):
    if not (directory/'summary.json').exists():continue
    name=directory.name
    if not name.startswith(a.trial_prefix):continue
    s=json.loads((directory/'summary.json').read_text())
    if (not s['options']['workload'].startswith('sample-') or name.startswith('secondary-')
        or s['options']['data']!=a.data):continue
    try: result=outputs(name)
    except Exception as exc:
        print('SKIP',name,str(exc));continue
    ref_total=ref_matched=base_total=out_total=base_matched=exact=0
    char_base=char_out=char_overlap=0
    for index,text in sorted(result.items()):
        ref=words(reference[index]);out=words(text);base=words(baseline[index])
        overlap=sum((ref&out).values());agreement=sum((base&out).values())
        bt,ot=trigrams(baseline[index]),trigrams(text)
        char_base+=sum(bt.values());char_out+=sum(ot.values());char_overlap+=sum((bt&ot).values())
        if sum(ref.values())>=10:
            ref_total+=sum(ref.values());ref_matched+=overlap
        base_total+=sum(base.values());out_total+=sum(out.values());base_matched+=agreement
        exact+=text==baseline[index]
        details.append(dict(trial=name,page=index+1,chars=len(text),baseline_chars=len(baseline[index]),
                            reference_words=sum(ref.values()),reference_recall=overlap/max(1,sum(ref.values())),
                            baseline_word_f1=2*agreement/max(1,sum(base.values())+sum(out.values()))))
    summary.append(dict(trial=name,pages=len(result),exact_baseline_pages=exact,
                        embedded_text_word_recall=ref_matched/max(1,ref_total),
                        baseline_word_f1=2*base_matched/max(1,base_total+out_total),
                        baseline_character_trigram_f1=2*char_overlap/max(1,char_base+char_out),
                        output_words=out_total))
for filename,rows in [(a.prefix+'-pages.csv',details),(a.prefix+'-summary.csv',summary)]:
    if rows:
        with (root/filename).open('w') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
print(json.dumps(summary,indent=2))
