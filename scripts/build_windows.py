"""Build a self-contained Windows executable and a ready-to-use ZIP."""
import hashlib
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cleaner import __version__


def main():
    if sys.platform!='win32': raise SystemExit('Build the Windows release on Windows.')
    parser=argparse.ArgumentParser()
    parser.add_argument('--package-only',action='store_true',help='Reuse the tested EXE; refresh documentation and ZIP checksums')
    args=parser.parse_args()
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--noupx',
        '--name','YouTubeSpamCleaner','--add-data',f'{ROOT / "cleaner/static"};cleaner/static',
        '--collect-submodules','uvicorn','--collect-data','certifi',
        '--recursive-copy-metadata','google-auth-oauthlib','--recursive-copy-metadata','fastapi',
        '--copy-metadata','uvicorn','launcher.py']
    if not args.package_only:
        build_environment=os.environ.copy()
        build_environment.pop('PYTHONPATH',None)
        build_environment.pop('PYTHONHOME',None)
        subprocess.run(command,cwd=ROOT,check=True,env=build_environment)
    exe=ROOT/'dist/YouTubeSpamCleaner.exe'
    quickstart='''YOUTUBE SPAM CLEANER — WINDOWS QUICK START

1. Extract this ZIP to a folder on your computer.
2. Double-click YouTubeSpamCleaner.exe. Your default browser opens the local app.
3. Open Connection, import your Google OAuth Desktop app JSON, and connect your channel.
4. Add detection rules, run a scan, review matches, and choose a moderation action.

No Python, Node.js, compiler, or package installation is required.
To try the interface without Google credentials, double-click Demo.cmd.
Demo mode uses separate sample data and never contacts YouTube.

Google setup is still required for real use: enable YouTube Data API v3 in your
Google Cloud project, configure the consent screen, add yourself as a test user
if applicable, create a Desktop app OAuth client, and download its JSON.

The service keeps running when a browser tab closes. Use Quit application in
the sidebar to stop it. Opening the EXE again reopens an existing instance.
The app is local-only; it does not run while the computer is sleeping or shut down.

Data: %LOCALAPPDATA%\\YouTubeSpamCleaner\\data
Demo data: %LOCALAPPDATA%\\YouTubeSpamCleaner\\demo
Windows tokens are protected for the current Windows account using DPAPI.
Do not share the data folder, session.json, or OAuth credentials.

This executable is unsigned. The included checksums verify the downloaded files.
See README.md and VERIFICATION.md for setup details and test limitations.
'''
    release=ROOT/'dist'/f'YouTubeSpamCleaner-{__version__}-windows-x64.zip'
    notices=[]
    for dist in sorted(importlib.metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
        if dist.metadata['Name'].lower() in {'pytest','httpx'}: continue
        for file in dist.files or []:
            if '.dist-info/' in str(file).replace('\\','/') and Path(str(file)).name.lower() in {'license','license.txt','license.md','copying','notice'}:
                try:
                    text=dist.locate_file(file).read_text(encoding='utf-8',errors='replace')
                    notices.append(f"\n{'='*72}\n{dist.metadata['Name']} {dist.version}\n{'='*72}\n{text}")
                except OSError: pass
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():
        notices.append('\nPython runtime license\n'+python_license.read_text(encoding='utf-8',errors='replace'))
    files={'YouTubeSpamCleaner.exe':exe.read_bytes(),
        'Demo.cmd':b'@echo off\r\nstart "" "%~dp0YouTubeSpamCleaner.exe" --demo\r\n',
        'START-HERE.txt':quickstart.encode('utf-8'),
        'README.md':(ROOT/'README.md').read_bytes(),
        'RELEASE_NOTES.md':(ROOT/'RELEASE_NOTES.md').read_bytes(),
        'VERIFICATION.md':(ROOT/'VERIFICATION.md').read_bytes(),
        'THIRD-PARTY-NOTICES.txt':'\n'.join(notices).encode('utf-8')}
    screenshot=ROOT/'docs/demo-overview.png'
    if screenshot.exists(): files['docs/demo-overview.png']=screenshot.read_bytes()
    checksums=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in files.items())
    files['SHA256SUMS.txt']=checksums.encode()
    with zipfile.ZipFile(release,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in files.items(): archive.writestr(name,data)
    digest=hashlib.sha256(release.read_bytes()).hexdigest()
    checksum=release.with_suffix(release.suffix+'.sha256')
    checksum.write_text(f'{digest}  {release.name}\n',encoding='utf-8')
    print(json.dumps({'version':__version__,'archive':str(release),'bytes':release.stat().st_size,'sha256':digest},indent=2))


if __name__=='__main__': main()
