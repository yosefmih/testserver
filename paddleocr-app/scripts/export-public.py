#!/usr/bin/env python3
"""Copy an explicit source allowlist to a new standalone directory; never copy history or data."""
import argparse
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parents[1]
dest = args.destination.resolve()
if dest.exists():
    parser.error('destination must not already exist')
ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store', 'node_modules', 'dist', 'static', '.venv', 'data')
for rel in ['backend', 'frontend', '.github']:
    shutil.copytree(source / rel, dest / rel, ignore=ignore)
(dest / 'examples').mkdir(exist_ok=True)
shutil.copy2(source / 'examples/l40s-values.yaml', dest / 'examples/l40s-values.yaml')
shutil.copy2(source / 'examples/porter.yaml', dest / 'porter.yaml')
chart = Path('charts/paddleocr-vl-hps')
for rel in ['templates', 'files']:
    shutil.copytree(source / chart / rel, dest / chart / rel, ignore=ignore)
for rel in ['Chart.yaml', 'values.yaml', 'values-stock-vllm.yaml', 'values-g6xlarge.yaml', 'values-g6e-8xlarge.yaml']:
    shutil.copy2(source / chart / rel, dest / chart / rel)
for rel in ['Dockerfile', '.dockerignore', '.values.example.yaml', 'LICENSE', 'NOTICE']:
    shutil.copy2(source / rel, dest / rel)
(dest / 'scripts').mkdir(exist_ok=True)
for rel in ['common.sh', 'build-app-image.sh', 'build-paddleocr-images.sh', 'build-vllm-image.sh', 'deploy-paddleocr.sh']:
    shutil.copy2(source / 'scripts' / rel, dest / 'scripts' / rel)
shutil.copy2(source / 'PUBLIC_README.md', dest / 'README.md')
(dest / '.gitignore').write_text('''node_modules/
frontend/dist/
backend/app/static/
__pycache__/
*.pyc
.venv/
.env
.env.*
.values*.yaml
!.values.example.yaml
.DS_Store
benchmarks/
data/
*.log
''')
print(f'Exported source to {dest}')
