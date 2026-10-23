"""Assemble a new full installer from a verified unchanged runtime and new core."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request

CONFIG = json.loads(Path('packaging/photo-release-input.json').read_text())
BASE = f"repos/{os.environ['GITHUB_REPOSITORY']}"
ROOT = Path(os.environ['RUNNER_TEMP']) / 'FreeSearchPhotoRelease'
ROOT.mkdir()
REPORTS = ROOT / 'reports'
REPORTS.mkdir()
STAGE = ROOT / 'program'
OUTPUT = ROOT / 'installer'
OUTPUT.mkdir()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'{BASE}/{path}']))


def download(asset, destination):
    with destination.open('wb') as stream:
        subprocess.run(['gh', 'api', f"{BASE}/releases/assets/{asset['id']}",
                        '-H', 'Accept: application/octet-stream'], stdout=stream, check=True)
    assert destination.stat().st_size == asset['bytes'] and sha(destination) == asset['sha256']


release = api(f"releases/{CONFIG['release_id']}")
assert release['draft'] and release['tag_name'] == CONFIG['tag']
base_installer = [a for a in CONFIG['base_assets'] if a['name'].endswith(('.exe', '.bin'))]
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(lambda a: download(a, ROOT / a['name']), base_installer))
setup = ROOT / 'FreeSearch-Setup-0.1.0-preview.1.exe'
subprocess.run([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
                '/NOICONS', '/TASKS=', f'/DIR={STAGE}', f"/LOG={REPORTS / 'base-install.log'}"],
               check=True, timeout=900)
assert json.loads((STAGE / 'installed.json').read_text())['version'] == '0.1.0-preview.1'
for asset in base_installer:
    (ROOT / asset['name']).unlink()
assert {p.relative_to(STAGE).as_posix() for p in (STAGE / '_internal').rglob('*') if p.is_file()} == set(CONFIG['runtime_hashes'])
for relative, expected in CONFIG['runtime_hashes'].items():
    assert sha(STAGE / relative) == expected, relative

core = ROOT / 'FreeSearch-core.exe'
with core.open('wb') as stream:
    for part in CONFIG['parts']:
        temporary = ROOT / 'core.part'
        download(part, temporary)
        with temporary.open('rb') as source:
            shutil.copyfileobj(source, stream, length=1024**2)
        temporary.unlink()
assert core.stat().st_size == CONFIG['core_bytes'] and sha(core) == CONFIG['core_sha256']
for edition in ('offline', 'api'):
    shutil.copyfile(core, STAGE / f'FreeSearch-{edition}.exe')
for name in ('README.md', 'docs/QUICKSTART.zh-CN.md', 'docs/VALIDATION.md', 'docs/GITHUB_UPLOAD.zh-CN.md'):
    shutil.copyfile(name, STAGE / name)
shutil.copyfile('packaging/installed.json', STAGE / 'installed.json')
# The base installer's own uninstaller must never enter the new payload.
for path in STAGE.glob('unins*'):
    assert path.is_file()
    path.replace(ROOT / path.name)

compiler_setup = ROOT / 'innosetup.exe'
with urllib.request.urlopen(CONFIG['inno_url'], timeout=120) as response, compiler_setup.open('wb') as stream:
    shutil.copyfileobj(response, stream)
assert sha(compiler_setup) == CONFIG['inno_sha256']
compiler = ROOT / 'InnoSetup'
subprocess.run([str(compiler_setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
                '/NOICONS', '/TASKS=', f'/DIR={compiler}'], check=True, timeout=180)
with (REPORTS / 'compiler.log').open('wb') as log:
    subprocess.run([str(compiler / 'ISCC.exe'), f'/DStagingDir={STAGE}', f'/DSetupOutput={OUTPUT}',
                    str(Path('packaging/FreeSearch.iss').resolve())], stdout=log, stderr=subprocess.STDOUT,
                   check=True, timeout=900)
files = sorted(OUTPUT.glob('FreeSearch-Setup-0.1.0-preview.2*'))
assert len(files) == 3 and any(p.suffix == '.exe' for p in files)
assert all(p.stat().st_size < 2 * 1024**3 for p in files)
dependency = next(a for a in CONFIG['base_assets'] if a['name'] == 'FreeSearch-dependency-sources.zip')
dependency_path = OUTPUT / dependency['name']
download(dependency, dependency_path)
source = next(a for a in api(f"releases/{CONFIG['release_id']}/assets?per_page=100")
              if a['name'] == 'FreeSearch-source.zip')
assert source['size'] == CONFIG['source']['bytes'] and source['digest'] == 'sha256:' + CONFIG['source']['sha256']
expected = [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files + [dependency_path]]
expected.append(CONFIG['source'])
checksums = OUTPUT / 'SHA256SUMS.txt'
checksums.write_text(''.join(f"{a['sha256']}  {a['name']}\n" for a in expected), encoding='ascii', newline='\n')
expected.append({'name': checksums.name, 'bytes': checksums.stat().st_size, 'sha256': sha(checksums)})
for path in files + [dependency_path, checksums]:
    subprocess.run(['gh', 'release', 'upload', CONFIG['tag'], str(path), '--repo', os.environ['GITHUB_REPOSITORY']], check=True)
uploaded = {a['name']: a for a in api(f"releases/{CONFIG['release_id']}/assets?per_page=100")}
for target in expected:
    remote = uploaded[target['name']]
    assert remote['size'] == target['bytes'] and remote['digest'] == 'sha256:' + target['sha256']
manifest = {'release_id': CONFIG['release_id'], 'tag': CONFIG['tag'], 'commit': CONFIG['commit'],
            'core_sha256': CONFIG['core_sha256'], 'runtime_files_unchanged': len(CONFIG['runtime_hashes']),
            'passed': True, 'expected': expected}
(REPORTS / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in manifest.items() if k != 'expected'}))
