# BinRAT
# Python RAT & C2 — Malware Research Project

> **Security research only.** This repository contains a proof-of-concept remote access trojan (RAT) and command-and-control (C2) controller. It includes invasive surveillance, persistence, file-transfer, and remote-code-execution capabilities. Study it only in an isolated, explicitly authorized laboratory environment. Do not deploy it on other people's systems.

## Overview

This project explores the architecture and behavior of a Python-based RAT and its accompanying C2 backend. The two programs communicate using a custom TCP protocol. The controller tracks connected clients and provides a terminal-based interface for issuing commands; the client processes commands and returns responses or media data.

The repository is intended for **malware analysis, detection engineering, and defensive security education**, not for unauthorized monitoring or access.

## Repository structure

```text
.
├── trojan_v8.py    # RAT client: command handling, collection, streaming, persistence
├── backend_v8.py   # C2 controller: client registry, command menu, data reception
└── README.md
```

## Architecture

```text
┌──────────────────────────┐       Custom TCP protocol       ┌──────────────────────────┐
│ backend_v8.py            │ <─────────────────────────────> │ trojan_v8.py             │
│ C2 controller            │                                 │ RAT client               │
│ • Connected-client list  │                                 │ • Command dispatcher     │
│ • Interactive CLI        │                                 │ • Collection modules     │
│ • Response/file receiver │                                 │ • Streaming modules      │
│ • Live preview           │                                 │ • Persistence behavior   │
└──────────────────────────┘                                 └──────────────────────────┘
```

The client initiates a connection to the controller, identifies itself using its hostname, and handles incoming requests. The controller supports multiple registered clients and selection of one or more clients from its CLI.

## Implemented capabilities

| Area | Functionality represented in the code |
| --- | --- |
| C2 communication | TCP client/server communication, client registration, reconnection attempts, command dispatch |
| Remote system control | Shutdown and restart commands |
| Camera | Still-image capture, video recording, live video streaming |
| Microphone | Audio recording and audio streaming |
| Screen | Screenshots, screen recording, live screen streaming |
| Combined capture | Camera/audio and screen/audio recording or streaming |
| Keystroke collection | Timed, manually toggled, and continuous logging modes |
| Persistence | Windows user-level Run-key persistence and status checking |
| File transfer | Transfer of collected files to the controller; FTP upload functionality |
| Code execution | Execution of Python code received from the controller |
| Operator interface | Text-based command menu, multiple-client selection, OpenCV live preview |

**Important:** These are features identified through source-code review, not claims that they have been tested successfully on every operating system or hardware configuration.

## Technical characteristics

- **Language:** Python
- **Networking:** Python sockets with a custom application protocol
- **Concurrency:** Threads and synchronization primitives
- **Image/video processing:** OpenCV, Pillow, MSS, NumPy
- **Audio processing:** SoundDevice and Python's `wave` module
- **Keyboard input monitoring:** Pynput
- **Media encoding:** Optional FFmpeg integration for video conversion and audio/video merging
- **Operating-system integration:** Windows registry access for persistence; platform-specific background-process behavior

The client code includes automatic dependency-installation behavior. The controller imports OpenCV and NumPy for live-stream reception and preview.

## Security considerations

This project has several behaviors that defenders should recognize:

1. **Persistence:** Attempts to establish automatic execution at user login on Windows.
2. **Background execution:** Contains logic intended to run without a visible terminal.
3. **Sensitive data collection:** Can collect keystrokes, desktop imagery, camera footage, and microphone audio.
4. **Remote execution:** Accepts Python code for execution on the client system.
5. **Data movement:** Can transmit collected artifacts over network connections.
6. **C2 traffic:** Uses a custom, largely unprotected TCP protocol; the implementation does not establish authenticated, encrypted C2 sessions.

These behaviors can create serious privacy and security risks. Do not use the project with real personal data, credentials, or devices without explicit permission.

## Safe research environment

For defensive analysis, use a dedicated disposable virtual machine, synthetic data, and a network isolated from production and personal devices. Review the source statically before any execution. Avoid exposing the C2 service to public networks, and do not use real accounts, passwords, cameras, or microphones for experiments.

This README intentionally does not include deployment, persistence-enablement, surveillance, or remote-execution instructions.

## Suggested defensive research topics

- Identify persistence-related registry changes and process behavior.
- Study how the client and controller structure their messages and transfer data.
- Examine host and network telemetry associated with repeated connection attempts.
- Evaluate the risks of unauthenticated command channels and arbitrary code execution.
- Develop detection hypotheses using synthetic or pre-recorded laboratory observations.
- Assess how file artifacts and media capture could be identified during incident response.

## Limitations

- The source does not include automated tests or documented test results.
- Functionality depends on the operating system, hardware permissions, installed libraries, and available media devices.
- Some recording paths depend on FFmpeg and may use fallback output formats.
- The network protocol lacks robust authentication and transport encryption.
- The implementation is a research prototype, not a secure remote administration product.

## Ethical and legal notice

**Use only on systems you own or are explicitly authorized to test.** Unauthorized access, keystroke collection, recording, persistence, and data extraction may violate privacy, computer misuse, and other applicable laws. The project should be handled as potentially harmful code.

## License

No license has been specified. Add a `LICENSE` file if you intend to grant others permission to use, modify, or redistribute this repository. Public visibility on GitHub does not automatically grant those permissions. <br><br><br>

Demo Video : <br>
<video controls src="https://github.com/pehyanbin/BinRAT/blob/main/1122.mp4" title="<src/workspaces/BinRAT/1122.mp4 "></video>