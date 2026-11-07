"""Package the built Windows runtime and the exact local web assets, never session data."""
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parent.parent
BUNDLE=ROOT/'native/dist/ProctorLabAgent'
WEB=ROOT/'dist'

def package():
    if not (BUNDLE/'ProctorLabAgent.exe').is_file():raise RuntimeError('Build with PyInstaller first')
    extension=WEB/'proctor-lab-extension.zip'
    with zipfile.ZipFile(extension,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT/'extension').iterdir()):
            if path.is_file():archive.write(path,path.name)
    for path in sorted(WEB.rglob('*')):
        if not path.is_file() or path.name=='proctor-lab-windows-v3.zip':continue
        target=BUNDLE/'web'/path.relative_to(WEB);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
    start='@echo off\r\ncd /d "%~dp0"\r\nif not exist "_internal\\python313.dll" goto incomplete\r\nif not exist "web\\index.html" goto incomplete\r\nstart "" "%~dp0ProctorLabAgent.exe"\r\nexit /b\r\n:incomplete\r\necho Extract ALL files from the ZIP first.\r\npause\r\n'
    (BUNDLE/'Start.cmd').write_text(start,encoding='ascii')
    (BUNDLE/'README_RU.txt').write_text('Proctor Lab 3 — Windows x64\n\nРаспакуйте архив полностью и запустите Start.cmd или ProctorLabAgent.exe.\nPython и ключи AI для прокторинга не нужны.\nВ окне программы разрешите контроль, скопируйте код и откройте локальный стенд.\nВставьте код в поле сайта и подключите Windows. Расширение устанавливается отдельно вручную.\nКамера, микрофон, экран и локальная запись включаются на странице явно.\nЗакрытие программы прекращает контроль. Нет автозапуска, драйвера или завершения чужих процессов.\nПодробнее: web/capabilities.html и README.md в исходниках.\n',encoding='utf-8-sig')
    destination=WEB/'proctor-lab-windows-v3.zip'
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUNDLE.rglob('*')):
            if path.is_file() and (path.name in ('ProctorLabAgent.exe','Start.cmd','README_RU.txt') or path.relative_to(BUNDLE).parts[0] in ('_internal','web')):
                if path.name.endswith('.local.json') or path.name.endswith('-check.json'):continue
                archive.write(path,'ProctorLabAgent/'+path.relative_to(BUNDLE).as_posix())
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert 'ProctorLabAgent/web/vendor/mediapipe/blaze_face_short_range.tflite' in archive.namelist()
        assert not any('config.local.json' in x or 'native-self-check.json' in x for x in archive.namelist())
    shutil.copy2(destination,ROOT.parent/'proctor-lab-windows-v3.zip')
    print(f'Portable archive: {destination.stat().st_size} bytes; ZIP verified; includes offline model and web UI; no pairing token/configuration')

if __name__=='__main__':package()
