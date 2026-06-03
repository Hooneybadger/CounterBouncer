from pathlib import Path
import re
import subprocess
import tarfile
from .base import Workload
from ..model import sha256

LAYOUT = {'blackscholes': 'apps', 'canneal': 'kernels', 'dedup': 'kernels', 'streamcluster': 'kernels'}
ARGS = {
 'blackscholes': ['4', 'in_10M.txt', 'prices.txt'],
 'canneal': ['4', '15000', '2000', '2500000.nets', '6000'],
 'dedup': ['-c', '-p', '-v', '-t', '4', '-i', 'FC-6-x86_64-disc1.iso', '-o', 'output.dat.ddp'],
 'streamcluster': ['10', '20', '128', '1000000', '200000', '5000', 'none', 'output.txt', '4']}


def parse_output(name, text, workdir=None):
    if 'PARSEC Benchmark Suite' not in text:
        return None
    if name == 'blackscholes' and 'Num of Options: 10000000' not in text:
        return None
    if name == 'canneal' and 'Final routing is:' not in text:
        return None
    if name == 'dedup' and 'Effective compression factor:' not in text:
        return None
    if name == 'streamcluster':
        expected = int(ARGS[name][3])
        reads = [int(n) for n in re.findall(r'read (\d+) points', text)]
        if sum(reads) != expected or 'error reading data' in text or 'oops! no more space' in text:
            return None
        if workdir is not None:
            output = Path(workdir) / ARGS[name][7]
            if not output.is_file() or output.stat().st_size <= 0:
                return None
    # The runner supplies wall time around the native application (including its I/O).
    return {'validated_program_output': True}


def make(name):
    root = Path(__file__).resolve().parents[2]
    repo = root / 'vendor/parsec'
    package = repo / 'pkgs' / LAYOUT[name] / name
    binary = package / 'inst/amd64-linux.gcc/bin' / name
    if not binary.exists():
        raise FileNotFoundError(binary)
    workdir = package / 'run/counterbouncer-native'
    workdir.mkdir(parents=True, exist_ok=True)
    archive = package / 'inputs/input_native.tar'
    marker = workdir / '.extracted'
    if not marker.exists():
        if name == 'streamcluster':
            # Official native.runconf uses 'none': the application generates its input.
            marker.write_text('official-native-internal-generator:' + sha256(package / 'parsec/native.runconf'))
        else:
            with tarfile.open(archive) as tar:
                tar.extractall(workdir, filter='data')
            marker.write_text(sha256(archive))
    if name == 'streamcluster':
        leftover = workdir / ARGS[name][7]
        if leftover.exists():
            leftover.unlink()
    version = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    return Workload('parsec', name, 'native', [str(binary), *ARGS[name]], str(workdir), version,
                    lambda text, n=name, directory=str(workdir): parse_output(n, text, directory), metadata={
                        'binary_sha256': sha256(binary), 'input_archive_sha256': marker.read_text(),
                        'threads': 4, 'roi': 'whole application incl input/output; not PARSEC hook ROI',
                        'runconf': str(package / 'parsec/native.runconf')})
