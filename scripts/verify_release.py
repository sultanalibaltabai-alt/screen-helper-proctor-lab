"""Validate distribution integrity and prevent local secrets from being published."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

from package_project import ROOT, source_files


def verify():
    secret_values = set()
    # Read only the originating project's local key, without printing or copying it.
    original = ROOT.parent.parent / 'screen-helper' / 'config.local.json'
    if original.is_file():
        config = json.loads(original.read_text(encoding='utf-8-sig'))
        for key, value in config.items():
            if 'key' in key.lower() and isinstance(value, str) and len(value) > 25:
                secret_values.add(value.encode())
    signatures = re.compile(rb'(?:sk-(?:proj-)?[A-Za-z0-9_-]{35,}|AIza[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,})')
    checked = 0

    def inspect(name, data):
        nonlocal checked
        checked += 1
        if any(value in data for value in secret_values):
            raise RuntimeError('Local key found in ' + name)
        matches = signatures.findall(data)
        for value in matches:
            # Only explicit offline fixtures may contain key-shaped example strings.
            if b'FAKE' in value or b'fake' in value or len(set(value.split(b'-')[-1])) < 3:
                continue
            raise RuntimeError('Potential credential found in ' + name + '; value withheld')

    for file in source_files():
        inspect(file.relative_to(ROOT).as_posix(), file.read_bytes())
    checksums = ROOT / 'release' / 'SHA256SUMS.txt'
    for line in checksums.read_text(encoding='ascii').splitlines():
        expected, name = line.split('  ', 1)
        file = ROOT / 'release' / name
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Checksum mismatch: ' + name)
        with zipfile.ZipFile(file) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Damaged ZIP: ' + name)
            for member in archive.infolist():
                if member.is_dir():
                    continue
                parts = Path(member.filename).parts
                forbidden = member.filename.endswith('.local.json') or '.env' in parts or '.git' in parts
                if forbidden or any(part in ('api-check.json','last-result.json','self-check.json','native-self-check.json') for part in parts):
                    raise RuntimeError('Private configuration/report found in ' + name)
                inspect(name + ':' + member.filename, archive.read(member))
    print('Verified: source and 4 ZIPs, ' + str(checked) + ' entries; checksums valid; no detected credentials/private reports.')


if __name__ == '__main__':
    verify()
