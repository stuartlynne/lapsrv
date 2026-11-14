#!/usr/bin/env python3

import argparse
import datetime
import math
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
import wave
from io import BytesIO


getTimeNow = datetime.datetime.now
STOP_REQUESTED = False


def log(message):
    print('%s %s' % (getTimeNow().strftime('%H:%M:%S'), message), file=sys.stderr)


def handle_signal(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    log(f'POWERALERT:signal_received signum={signum}')


def parse_bool(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def find_power_path(explicit_path=None):
    if explicit_path:
        return explicit_path if os.path.exists(explicit_path) else None

    preferred = [
        '/sys/class/power_supply/AC/online',
        '/sys/class/power_supply/ADP1/online',
    ]
    for path in preferred:
        if os.path.exists(path):
            return path

    power_root = '/sys/class/power_supply'
    if not os.path.isdir(power_root):
        return None

    for entry in sorted(os.listdir(power_root)):
        entry_path = os.path.join(power_root, entry)
        type_path = os.path.join(entry_path, 'type')
        online_path = os.path.join(entry_path, 'online')
        try:
            if os.path.exists(type_path) and os.path.exists(online_path):
                with open(type_path, 'r', encoding='ascii') as f:
                    if f.read().strip().lower() == 'mains':
                        return online_path
        except OSError:
            continue
    return None


def get_ac_status(power_path):
    if not power_path or not os.path.exists(power_path):
        return None
    try:
        with open(power_path, 'r', encoding='ascii') as f:
            return f.read().strip() == '1'
    except OSError as e:
        log(f'POWERALERT:read_error path={power_path} error={e}')
        return None


def build_tone_pcm(frequency=440.0, duration=0.5, sample_rate=44100, amplitude=32767 // 3):
    total_samples = int(sample_rate * duration)
    pcm = bytearray()
    for i in range(total_samples):
        sample = int(amplitude * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
        pcm.extend(struct.pack('<h', sample))
    return bytes(pcm), sample_rate


def build_wave_bytes(pcm_bytes, sample_rate):
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_bytes)
    return buffer.getvalue()


def pick_player():
    candidates = [
        ('paplay', ['paplay']),
        ('aplay', ['aplay', '-q']),
        ('ffplay', ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', '-i', '-']),
        ('play', ['play', '-q', '-t', 'wav', '-']),
    ]
    for name, cmd in candidates:
        if shutil.which(name):
            return cmd
    return None


def play_once(player_cmd, wav_bytes):
    if player_cmd is None:
        raise RuntimeError('no audio player found; tried paplay, aplay, ffplay, play')
    subprocess.run(player_cmd, input=wav_bytes, check=True)


def beep_twice(player_cmd, wav_bytes, pause=0.15):
    play_once(player_cmd, wav_bytes)
    time.sleep(pause)
    play_once(player_cmd, wav_bytes)


def parse_args():
    parser = argparse.ArgumentParser(description='Standalone AC power alert helper.')
    parser.add_argument('--config', default=None, help='Path to .power_alert.env config file')
    parser.add_argument('--path', default=None, help='Explicit /sys/.../online path to monitor')
    parser.add_argument('--poll', type=float, default=2.0, help='Polling interval in seconds')
    parser.add_argument('--repeat', type=float, default=15.0, help='Repeat alarm interval while AC is absent')
    parser.add_argument('--startup-test', action='store_true', help='Play a double-beep at startup')
    return parser.parse_args()


def resolve_config_path(explicit_path=None):
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    candidates.append(os.path.join(os.path.expanduser('~'), '.power_alert.env'))
    candidates.append('.power_alert.env')
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return explicit_path or os.path.join(os.path.expanduser('~'), '.power_alert.env')


def load_config_file(config_path):
    config = {}
    if not config_path or not os.path.exists(config_path):
        return config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip().lower().replace('-', '_')
                value = value.strip()
                config[key] = value
    except OSError as e:
        log(f'POWERALERT:config_read_error path={config_path} error={e}')
    return config


def ensure_default_config(config_path):
    if not config_path or os.path.exists(config_path):
        return
    parent = os.path.dirname(config_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    default_config = """# power_alert configuration
# Edit this file while power_alert.py is running; it will reload on change.
#
# Audio playback:
#   power_alert.py does not synthesize audio itself. It looks for one of:
#     paplay, aplay, ffplay, play
#   On Debian/Ubuntu these are commonly provided by:
#     sudo apt install pulseaudio-utils
#     sudo apt install alsa-utils
#     sudo apt install ffmpeg
#     sudo apt install sox
#
# startup_test:
#   true  -> play a double-beep when the script starts or when toggled back on
#   false -> do not play a startup beep
startup_test=false
#
# repeat:
#   seconds between repeated alarms while AC power is absent
repeat=15
#
# poll:
#   seconds between power checks
poll=2
#
# path:
#   optional explicit /sys/class/power_supply/.../online path
#   leave commented out for auto-detection
# path=/sys/class/power_supply/AC/online
"""
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(default_config)
    log(f'POWERALERT:config_created path={config_path}')


def merge_settings(args, config):
    settings = {
        'path': args.path,
        'poll': args.poll,
        'repeat': args.repeat,
        'startup_test': args.startup_test,
    }

    if 'path' in config:
        settings['path'] = config['path'] or None
    if 'poll' in config:
        try:
            settings['poll'] = float(config['poll'])
        except ValueError:
            log(f"POWERALERT:config_value_error key=poll value={config['poll']}")
    if 'repeat' in config:
        try:
            settings['repeat'] = float(config['repeat'])
        except ValueError:
            log(f"POWERALERT:config_value_error key=repeat value={config['repeat']}")
    if 'startup_test' in config:
        settings['startup_test'] = parse_bool(config['startup_test'])

    return settings


def main():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    args = parse_args()
    config_path = resolve_config_path(args.config)
    ensure_default_config(config_path)
    config_mtime = None
    config = load_config_file(config_path)
    settings = merge_settings(args, config)
    power_path = find_power_path(settings['path'])
    player_cmd = pick_player()
    pcm_bytes, sample_rate = build_tone_pcm()
    alert_wav_bytes = build_wave_bytes(pcm_bytes, sample_rate)
    restored_pcm_bytes, restored_sample_rate = build_tone_pcm(frequency=660.0, duration=0.35)
    restored_wav_bytes = build_wave_bytes(restored_pcm_bytes, restored_sample_rate)
    ac_online = None
    last_alarm = 0.0
    startup_test_done = False

    if os.path.exists(config_path):
        try:
            config_mtime = os.path.getmtime(config_path)
        except OSError:
            config_mtime = None

    try:
        log(
            'POWERALERT:start path=%s player=%s config=%s poll=%s repeat=%s startup_test=%s'
            % (
                power_path,
                ' '.join(player_cmd) if player_cmd else 'none',
                config_path,
                settings['poll'],
                settings['repeat'],
                settings['startup_test'],
            )
        )

        if settings['startup_test']:
            try:
                beep_twice(player_cmd, alert_wav_bytes)
                log('POWERALERT:startup_beep ok')
            except Exception as e:
                log(f'POWERALERT:startup_beep_error error={e}')
            startup_test_done = True

        while not STOP_REQUESTED:
            if config_path and os.path.exists(config_path):
                try:
                    current_mtime = os.path.getmtime(config_path)
                except OSError:
                    current_mtime = config_mtime
                if config_mtime is None or current_mtime != config_mtime:
                    config_mtime = current_mtime
                    config = load_config_file(config_path)
                    settings = merge_settings(args, config)
                    power_path = find_power_path(settings['path'])
                    log(
                        'POWERALERT:config_reloaded path=%s poll=%s repeat=%s startup_test=%s power_path=%s'
                        % (config_path, settings['poll'], settings['repeat'], settings['startup_test'], power_path)
                    )
                    if settings['startup_test'] and not startup_test_done:
                        try:
                            beep_twice(player_cmd, wav_path)
                            log('POWERALERT:startup_beep ok')
                        except Exception as e:
                            log(f'POWERALERT:startup_beep_error error={e}')
                        startup_test_done = True
                    elif not settings['startup_test']:
                        startup_test_done = False

            current = get_ac_status(power_path)
            if current != ac_online:
                log(f'POWERALERT:transition old={ac_online} new={current}')
                if ac_online is False and current is True:
                    try:
                        play_once(player_cmd, restored_wav_bytes)
                        log('POWERALERT:restored_beep ok')
                    except Exception as e:
                        log(f'POWERALERT:restored_beep_error error={e}')
                ac_online = current

            if ac_online is False and time.time() - last_alarm >= settings['repeat']:
                try:
                    beep_twice(player_cmd, alert_wav_bytes)
                    last_alarm = time.time()
                    log('POWERALERT:alarm_beep ok')
                except Exception as e:
                    log(f'POWERALERT:alarm_beep_error error={e}')

            time.sleep(settings['poll'])
    finally:
        log('POWERALERT:stopping')


if __name__ == '__main__':
    main()
