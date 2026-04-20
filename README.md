##  Team Information
| Name | SRN |
|------|-----|
| Akula Pragnya | PES1UG24AM028 |
| Amogh Shetty | PES1UG24034 |
| Ananta Krishna | PES1UG24036 |


# Reliable File Transfer over UDP

A custom reliable file transfer protocol built on top of UDP in Python.  
Implements chunking, sliding window, SHA-256 integrity checks, acknowledgements,
and resume support — entirely at the application layer.

---

## Features

- **Chunk-based transfer** — file split into 1024-byte packets
- **Sliding window** — multiple packets in flight for better throughput
- **SHA-256 checksums** — every chunk verified for integrity
- **ACK-based reliability** — lost packets detected and retransmitted
- **Resume support** — interrupted transfers continue from last received chunk
- **Multi-client support** — server handles multiple clients simultaneously
- **Performance metrics** — throughput and timing printed after transfer

---

## Requirements

- Python 3.x (no external libraries needed)
- Both machines on the same network (for cross-machine transfer)

---

## Setup

### 1. Files needed
```
client.py
server.py
README.md
```

### 2. Create a test file
```bash
python3 -c "open('file_to_send.txt', 'w').write('ABCDEFGHIJ' * 10000)"
```
This creates a ~100 KB file — good for demos.

---

## Usage

### Start the server
```bash
python3 server.py
```
You should see:
```
[SERVER] Listening on 0.0.0.0:5001
```

### Run the client
```bash
python3 client.py
```
You will be prompted for the server IP. Press Enter for same-machine, or type the server's IP for cross-machine transfer.

To find the server IP:
- **Mac:** `ipconfig getifaddr en0`
- **Windows:** `ipconfig` → IPv4 Address

---

## Demo: Resume Feature

1. Start server: `python3 server.py`
2. Start client: `python3 client.py`
3. Press `Ctrl+C` on the client mid-transfer
4. Run client again: `python3 client.py`
5. You will see: `[CLIENT] Resuming from chunk X`

The server saves each chunk to disk immediately as it arrives inside a
`chunks_file_to_send/` folder, so progress survives interruption.

---

## Demo: Performance Evaluation

Change `WINDOW_SIZE` in `client.py` and run 3 times:

| WINDOW_SIZE | Expected behaviour        |
|-------------|---------------------------|
| 1           | Slowest — one at a time   |
| 5           | Balanced (default)        |
| 10          | Fastest — more in flight  |

After every transfer the client prints:
```
==================================================
[CLIENT] Transfer complete!
  File size   : 102400 bytes (100.0 KB)
  Chunks      : 100
  Window size : 5
  Time taken  : 6.23 seconds
  Throughput  : 16.05 KB/s
  Packets sent: 100 (includes retransmissions)
==================================================
```

---

## Configuration

| Constant      | Default           | Description                        |
|---------------|-------------------|------------------------------------|
| `SERVER_PORT` | `5001`            | Port the server listens on         |
| `CHUNK_SIZE`  | `1024`            | Size of each packet in bytes       |
| `WINDOW_SIZE` | `5`               | Packets in flight simultaneously   |
| `TIMEOUT`     | `2`               | Seconds before retransmitting      |
| `FILENAME`    | `file_to_send.txt`| File to transfer (client side)     |

---

## How It Works
```
Client                            Server
  |                                 |
  |------ INIT (filename, n) -----> | Checks chunks already saved on disk
  |<----- RESUME (last_seq) ------- | Tells client where to resume from
  |                                 |
  |------ DATA (seq=0) -----------> | Verifies checksum
  |------ DATA (seq=1) -----------> | Saves chunk to disk immediately
  |------ DATA (seq=2) -----------> |
  |<----- ACK (seq=0) ------------ |
  |<----- ACK (seq=1) ------------ |
  |<----- ACK (seq=2) ------------ |
  |  (window slides forward)        |
  |  (all chunks received)          | Assembles final file, cleans up chunks
```

---

## Output Files

- **`received_file_to_send.bin`** — final assembled file on the server
- **`chunks_file_to_send/`** — temporary per-chunk folder (deleted on completion)

---

## Edge Cases Handled

- File not found or empty → client exits with clear error
- Server not responding → INIT retried 5 times before giving up
- Corrupt packet → checksum mismatch causes discard and retransmission
- Abrupt disconnection → chunks saved on disk, resumes on reconnect
- DATA before INIT → server ignores with warning
- Excessive timeouts → client exits after 20 consecutive retries
