"""Publish this isolated repository using the owner's cached GitHub credentials.

Credentials stay in memory and curl's stdin; never in URLs, files or arguments.
Run --prepare first, then --publish after inspecting release assets.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, GCM_INTERACTIVE='never', GIT_TERMINAL_PROMPT='0')
ASSETS = ('StudyTools-Windows-x64.zip', 'ScreenHelper-Windows-x64.zip',
          'ProctorLab-Windows-x64.zip', 'Project-Source.zip', 'SHA256SUMS.txt')
TAG = 'v1.1.0'


def run(args, **kwargs):
    result = subprocess.run(args, cwd=ROOT, env=ENV, text=True,
                            capture_output=True, timeout=300, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: ' + str(args[0]) + '\n' + result.stderr[:1000])
    return result.stdout.strip()


def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


class GitHub:
    def __init__(self):
        result = run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n')
        fields = dict(line.split('=', 1) for line in result.splitlines() if '=' in line)
        self.token = fields.get('password')
        if not self.token:
            raise RuntimeError('GitHub credential unavailable; sign in to GitHub first.')

    def request(self, path, method='GET', data=None, file=None, missing_ok=False):
        url = path if path.startswith('https://') else 'https://api.github.com' + path
        if urllib.parse.urlsplit(url).hostname not in ('api.github.com', 'uploads.github.com'):
            raise RuntimeError('Unexpected API destination')
        config = [f'url = {quote(url)}', f'request = {quote(method)}',
                  f'header = {quote("Authorization: Bearer " + self.token)}',
                  'header = "Accept: application/vnd.github+json"',
                  'user-agent = "StudyTools-Release"', 'connect-timeout = 15',
                  'max-time = 240', 'silent', 'show-error']
        if file:
            content = 'text/plain' if file.suffix == '.txt' else 'application/zip'
            config += [f'header = {quote("Content-Type: " + content)}',
                       f'data-binary = {quote("@" + file.name)}']
        elif data is not None:
            config += ['header = "Content-Type: application/json"',
                       f'data-binary = {quote(json.dumps(data))}']
        proc = subprocess.run(['curl.exe', '--config', '-', '--write-out', '\n%{http_code}'],
                              input='\n'.join(config) + '\n', text=True,
                              capture_output=True, timeout=260, cwd=file.parent if file else ROOT)
        if proc.returncode:
            raise RuntimeError('GitHub network request failed, curl exit ' + str(proc.returncode))
        body, _, code = proc.stdout.rpartition('\n')
        if code == '404' and missing_ok:
            return None
        if not code.startswith('2'):
            raise RuntimeError('GitHub API HTTP ' + code)
        return json.loads(body) if body.strip() else {}


def repository(api):
    owner = api.request('/user')['login']
    base_name = 'screen-helper-proctor-lab'
    remote = run(['git', 'remote', 'get-url', 'origin']) if (ROOT / '.git').exists() else ''
    for name in (base_name, base_name + '-20261108'):
        path = f'/repos/{owner}/{name}'
        repo = api.request(path, missing_ok=True)
        expected = f'https://github.com/{owner}/{name}.git'
        if repo and remote != expected:
            continue
        if not repo:
            repo = api.request('/user/repos', 'POST', {
                'name': name, 'private': True, 'auto_init': False,
                'description': 'Windows x64 Screen Helper and independent Proctor Lab training tools',
            })
        if not repo.get('private'):
            raise RuntimeError('Expected a private repository')
        if not (ROOT / '.git').exists():
            run(['git', 'init', '-b', 'main'])
            run(['git', 'config', 'user.name', owner])
            run(['git', 'config', 'user.email', owner + '@users.noreply.github.com'])
            run(['git', 'remote', 'add', 'origin', expected])
        return repo, path
    raise RuntimeError('Repository names are already in use; no existing repository was changed.')


def find_release(api, path):
    release = api.request(path + '/releases/tags/' + TAG, missing_ok=True)
    if release:
        return release
    # Draft tags may not exist yet; the owner can still retrieve their release.
    matches = [item for item in api.request(path + '/releases?per_page=100')
               if item['tag_name'] == TAG]
    if len(matches) > 1:
        raise RuntimeError('Multiple draft releases match; no assets were changed.')
    return matches[0] if matches else None


def publish(api, repo, path):
    files = [ROOT / 'release' / name for name in ASSETS]
    if not all(file.is_file() for file in files):
        raise RuntimeError('Build release assets first')
    run([sys.executable, 'scripts/verify_release.py'])
    run(['git', 'add', '--', '.'])
    changed = run(['git', 'status', '--porcelain'])
    if changed:
        run(['git', 'commit', '-m', 'Protect API credentials and simplify the result display'])
    sha = run(['git', 'rev-parse', 'HEAD'])
    run(['git', 'push', '-u', 'origin', 'main'])
    release = find_release(api, path)
    if not release:
        release = api.request(path + '/releases', 'POST', {
            'tag_name': TAG, 'target_commitish': sha, 'name': 'Study Tools 1.1.0 — Screen Helper 8.3',
            'draft': True, 'prerelease': False,
            'body': 'Screen Helper 8.3: Gemini and OpenAI setup, encrypted Windows-user API keys, '
                    'seconds-only waiting indicator and 15-second answer display. '
                    'Legacy persistent/debug overlay settings are removed. '
                    'API redirects are refused; recognized questions and answer history are no longer saved in normal use.\n\n'
                    'Download **StudyTools-Windows-x64.zip**, extract ALL files, then run **Start.cmd**. '
                    'Python is included. Windows x64 only.\n\n'
                    'Russian OpenAI setup and a ChatGPT handoff prompt are in **docs/**. '
                    'An API key and funded API balance must be supplied by the owner locally. '
                    'No keys or personal settings are included.\n\n'
                    'Offline tests and portable self-checks passed. A funded OpenAI call and '
                    'a second physical computer have not been tested. Proctor Lab is an independent '
                    'training stand; OES compatibility or undetectability is not guaranteed.\n\n'
                    'Source archive and SHA-256 checksums are included.',
        })
    existing = {asset['name']: asset for asset in release.get('assets', [])}
    for file in files:
        digest = 'sha256:' + hashlib.sha256(file.read_bytes()).hexdigest()
        if file.name in existing:
            asset = existing[file.name]
            if asset['size'] != file.stat().st_size or asset.get('digest') not in (None, digest):
                raise RuntimeError('Existing release asset differs: ' + file.name)
        else:
            url = release['upload_url'].split('{')[0] + '?name=' + urllib.parse.quote(file.name)
            asset = api.request(url, 'POST', file=file)
            if asset['size'] != file.stat().st_size or asset.get('digest') not in (None, digest):
                raise RuntimeError('Upload verification failed: ' + file.name)
        print('Verified asset: ' + file.name + ' (' + str(asset['size']) + ' bytes)', flush=True)
    final = api.request(path + '/releases/' + str(release['id']))
    if set(ASSETS) - {asset['name'] for asset in final['assets']}:
        raise RuntimeError('Release has missing assets')
    if final['draft']:
        final = api.request(path + '/releases/' + str(final['id']), 'PATCH',
                            {'draft': False, 'target_commitish': sha})
    print(json.dumps({'repository': repo['html_url'], 'private': repo['private'],
                      'release': final['html_url'], 'commit': sha}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if not (args.prepare or args.publish):
        parser.error('Choose --prepare or --publish')
    api = GitHub()
    repo, path = repository(api)
    if args.publish:
        publish(api, repo, path)
    else:
        print(json.dumps({'repository': repo['html_url'], 'private': repo['private']}, indent=2))
