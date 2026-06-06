#!/usr/bin/env python3
from pathlib import Path
import json
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from counterbouncer.model import sha256, save, now
root=Path(__file__).resolve().parents[1]
data={'timestamp':now(), 'repositories':{}, 'binaries':{}, 'images':{}}
for name in ['parsec','cloudsuite','memcached-loadtester','STREAM','azure']:
    repo=root/'vendor'/name
    data['repositories'][name]={'commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
                                'remote':subprocess.check_output(['git','-C',str(repo),'remote','get-url','origin'],text=True).strip()}
# No path-space assumptions: list known benchmark names explicitly.
for name,kind in [('blackscholes','apps'),('canneal','kernels'),('dedup','kernels'),('streamcluster','kernels')]:
    path=root/'vendor/parsec/pkgs'/kind/name/'inst/amd64-linux.gcc/bin'/name
    data['binaries'][str(path.relative_to(root))]=sha256(path)
for name in ['server','client']:
    data['images'][name]=json.loads(subprocess.check_output(['docker','image','inspect',f'cloudsuite/data-caching:{name}'],text=True))[0]
data['compiler']=subprocess.check_output(['cc','--version'],text=True)
data['compiler_flags']={'CFLAGS':'-O3 -g', 'CXXFLAGS':'-O3 -g plus upstream compatibility flags'}
data['docker_existing']=subprocess.check_output(['docker','ps','--format','{{.Names}} {{.Status}}'],text=True)
save(root/'artifacts/setup/provenance.json',data)
