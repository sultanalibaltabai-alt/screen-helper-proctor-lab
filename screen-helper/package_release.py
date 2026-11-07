"""Package explicitly allowed files; local configuration and reports never ship."""
from pathlib import Path
import re
import sys
import zipfile

BASE = Path(__file__).resolve().parent

def package(version):
    if not re.fullmatch(r'\d+(?:\.\d+)*', version):
        raise ValueError('Invalid version')
    bundle = BASE / 'dist-v2' / 'ScreenHelper'
    if not (bundle / 'ScreenHelper.exe').is_file() or not (bundle / '_internal' / 'python313.dll').is_file():
        raise RuntimeError('Build the portable runtime first')
    public = sorted(BASE.glob('*.cmd')) + [BASE/'README.md', BASE/'.gitignore']
    samples = sorted((BASE/'samples').rglob('*.png'))
    portable = BASE.parent / f'screen-helper-portable-v{version}.zip'
    with zipfile.ZipFile(portable, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(bundle/'ScreenHelper.exe', 'ScreenHelper/ScreenHelper.exe')
        for path in sorted((bundle/'_internal').rglob('*')):
            if path.is_file():
                archive.write(path, 'ScreenHelper/' + path.relative_to(bundle).as_posix())
        for path in public + samples:
            archive.write(path, 'ScreenHelper/' + path.relative_to(BASE).as_posix())
    source = BASE.parent / 'screen-helper.zip'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BASE.glob('*.py')) + public + samples + [BASE/'requirements.txt']:
            archive.write(path, 'screen-helper/' + path.relative_to(BASE).as_posix())
    for path in (portable, source):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert not any(name.endswith('.local.json') for name in archive.namelist())
        print(f'{path.name}: {path.stat().st_size} bytes; ZIP integrity OK; no local configuration')

if __name__ == '__main__':
    package(sys.argv[1])
