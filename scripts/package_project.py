"""Assemble public release files. Never copy installed local settings or reports."""
from pathlib import Path
import hashlib,json,shutil,zipfile

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'release'

def source_files():
    files=[]
    for path in ROOT.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(ROOT);parts=relative.parts
        if any(x in {'.git','.openai','release','build','build-v2','dist-v2','__pycache__','node_modules','.venv'} for x in parts):continue
        if path.name=='.env' or path.name.startswith('.env.'):continue
        if parts[:3] in [('proctor-lab','native','dist'),('proctor-lab','native','build')]:continue
        if path.suffix in ('.zip','.spec','.log') or path.name.endswith(('.local.json','.local.tmp','-check.json')):continue
        if path.name in ('process-status.json','last-result.json','last-recognition.json','benchmark.json'):continue
        if path.name.startswith('native-proof'):continue
        files.append(path)
    return sorted(files)

def package():
    OUT.mkdir(exist_ok=True)
    helper=ROOT/'screen-helper-portable-v8.3.zip'
    native=ROOT/'proctor-lab-windows-v3.zip'
    for source,name in [(helper,'ScreenHelper-Windows-x64.zip'),(native,'ProctorLab-Windows-x64.zip')]:
        if not source.is_file():raise RuntimeError('Build missing: '+source.name)
        shutil.copy2(source,OUT/name)
    combined=OUT/'StudyTools-Windows-x64.zip'
    with zipfile.ZipFile(combined,'w',zipfile.ZIP_DEFLATED) as archive:
        for source in (helper,native):
            with zipfile.ZipFile(source) as incoming:
                for name in incoming.namelist():
                    if name.endswith('/') or name.endswith('.local.json'):continue
                    archive.writestr(name,incoming.read(name))
        for path in [ROOT/'Start.cmd',ROOT/'README_RU.md',ROOT/'README.md',*sorted((ROOT/'docs').glob('*.md'))]:
            archive.write(path,path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(OUT/'Project-Source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():archive.write(path,'screen-helper-proctor-lab/'+path.relative_to(ROOT).as_posix())
    hashes=[]
    for path in sorted(OUT.glob('*.zip')):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert not any(x.endswith('.local.json') for x in archive.namelist())
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n',encoding='ascii')
    print(json.dumps({'release_files':[{'name':p.name,'bytes':p.stat().st_size} for p in sorted(OUT.iterdir())]},indent=2))

if __name__=='__main__':package()
