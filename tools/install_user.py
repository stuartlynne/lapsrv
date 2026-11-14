#!/usr/bin/env python3
"""Install the user launcher and desktop icon using this checkout's venv."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--desktop', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = root / '.venv/bin/python'
    if not python.exists():
        parser.error('Create .venv and install requirements.txt first')
    launcher = Path.home() / '.local/bin/lapsrv'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    log = Path.home() / '.local/state/lapsrv/application.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(
        '#!/bin/sh\n# Managed by lapsrv tools/install_user.py\n'
        f'cd {shlex.quote(str(root))} || exit 1\n'
        f'exec {shlex.quote(str(python))} {shlex.quote(str(root / "lapsrv.py"))}'
        f' "$@" >>{shlex.quote(str(log))} 2>&1\n'
    )
    launcher.chmod(0o755)
    text = f'''[Desktop Entry]
Type=Application
Name=Lapsrv
Comment=Approaching riders from the early RFID reader
Exec="{launcher}"
Icon=network-wireless
Terminal=false
Categories=Utility;
StartupNotify=true
'''
    application = Path.home() / '.local/share/applications/lapsrv.desktop'
    application.parent.mkdir(parents=True, exist_ok=True)
    application.write_text(text)
    application.chmod(0o755)
    if args.desktop:
        try:
            desktop = Path(subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip())
        except (OSError, subprocess.CalledProcessError):
            desktop = Path.home() / 'Desktop'
        desktop.mkdir(parents=True, exist_ok=True)
        icon = desktop / 'Lapsrv.desktop'
        icon.write_text(text)
        icon.chmod(0o755)
        environment = os.environ.copy()
        environment.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path=/run/user/{os.getuid()}/bus')
        try:
            result = subprocess.run(['gio', 'set', str(icon), 'metadata::trusted', 'true'], env=environment, capture_output=True)
            if result.returncode:
                print('Desktop may require right-click > Allow Launching.')
        except FileNotFoundError:
            pass
    print(f'Launcher: {launcher}\nLog: {log}')


if __name__ == '__main__':
    main()
