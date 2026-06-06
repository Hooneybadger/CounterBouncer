#!/usr/bin/env python3
"""Fetch immutable upstream revisions and official image digests before setup."""
from pathlib import Path
import subprocess
import yaml

root=Path(__file__).resolve().parents[1]
config=yaml.safe_load((root/'configs/sources.yaml').read_text())
for name, source in config.items():
    if 'image' in source:
        subprocess.run(['docker','pull',source['image']],check=True)
        tag='server' if name.endswith('_server') else 'client'
        subprocess.run(['docker','tag',source['image'],f'cloudsuite/data-caching:{tag}'],check=True)
        continue
    path=root/'vendor'/name
    if path.exists():
        current=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        if current != source['commit']:
            raise SystemExit(f'{name}: existing checkout differs from pinned revision; preserve and resolve explicitly')
        continue
    path.mkdir(parents=True)
    subprocess.run(['git','init',str(path)],check=True)
    subprocess.run(['git','-C',str(path),'remote','add','origin',source['url']],check=True)
    subprocess.run(['git','-C',str(path),'fetch','--depth','1','origin',source['commit']],check=True)
    subprocess.run(['git','-C',str(path),'checkout','--detach','FETCH_HEAD'],check=True)
