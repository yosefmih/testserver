"""Per-container Linux process/cgroup sampling; GPU sampling where nvidia-smi exists."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument("--out",required=True)
p.add_argument("--interval",type=float,default=2)
a=p.parse_args()
ticks=os.sysconf("SC_CLK_TCK")
previous={}
gpu=shutil.which("nvidia-smi")
with open(a.out,"a",buffering=1) as output:
    while True:
        now=time.time()
        record={"time":now,"processes":[]}
        for directory in Path('/proc').glob('[0-9]*'):
            try:
                text=(directory/'stat').read_text()
                fields=text[text.rfind(')')+2:].split()
                cpu=(int(fields[11])+int(fields[12]))/ticks
                pid=int(directory.name)
                cmd=(directory/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')[:300]
                item={"pid":pid,"command":cmd,"rss_bytes":int(fields[21])*os.sysconf('SC_PAGE_SIZE')}
                if pid in previous:
                    old_time,old_cpu=previous[pid]
                    item['cpu_cores']=(cpu-old_cpu)/(now-old_time)
                previous[pid]=(now,cpu)
                record['processes'].append(item)
            except (OSError,ValueError,IndexError):
                pass
        for name in ['cpu.stat','memory.current','memory.events','cpu.max']:
            try: record[name]=Path('/sys/fs/cgroup',name).read_text().strip()
            except OSError: pass
        if gpu:
            try:
                record['gpu']=subprocess.check_output([gpu,'--query-gpu=utilization.gpu,utilization.memory,memory.used,power.draw,clocks.sm,clocks.mem,temperature.gpu','--format=csv,noheader,nounits'],text=True,timeout=3).strip()
                record['gpu_clock_events']=subprocess.check_output([gpu,'--query-gpu=clocks_event_reasons.active,clocks_event_reasons.sw_power_cap,clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.hw_power_brake_slowdown','--format=csv,noheader,nounits'],text=True,timeout=3).strip()
            except Exception as exc: record['gpu_error']=repr(exc)
        output.write(json.dumps(record)+'\n')
        time.sleep(a.interval)
