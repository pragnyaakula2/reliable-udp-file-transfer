import socket
import json
import hashlib
import os
import time
import base64
import sys

# ─── ANSI Colors ─────────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    WHITE   = "\033[97m"
    DIM     = "\033[2m"
    BLUE    = "\033[94m"

def banner():
    print(f"\n{C.CYAN}{C.BOLD}{'━'*52}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}     UDP Reliable File Transfer — CLIENT{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}{'━'*52}{C.RESET}")

def section(label):
    print(f"\n{C.DIM}{'─'*52}{C.RESET}")
    print(f"{C.BOLD}  {label}{C.RESET}")
    print(f"{C.DIM}{'─'*52}{C.RESET}")

def progress_bar(current, total, width=30):
    filled   = int(width * current / total)
    bar      = "█" * filled + "░" * (width - filled)
    percent  = int(100 * current / total)
    return f"{C.CYAN}[{bar}]{C.RESET} {C.BOLD}{percent}%{C.RESET}  {current}/{total} chunks"

def print_progress(current, total):
    bar = progress_bar(current, total)
    sys.stdout.write(f"\r  {bar}   ")
    sys.stdout.flush()

# ─── Configuration ───────────────────────────────────────────────────────────
SERVER_PORT = 5001
BUFFER_SIZE = 65535
CHUNK_SIZE  = 1024
WINDOW_SIZE = 5
TIMEOUT     = 2
FILENAME    = "file_to_send.txt"

banner()

SERVER_IP = input(f"\n{C.BOLD}  Enter server IP (Enter = 127.0.0.1): {C.RESET}").strip() or "127.0.0.1"

# ─── Input validation ────────────────────────────────────────────────────────
if not os.path.exists(FILENAME):
    print(f"\n{C.RED}  ✖  File '{FILENAME}' not found.{C.RESET}\n")
    exit(1)

file_size = os.path.getsize(FILENAME)
if file_size == 0:
    print(f"\n{C.RED}  ✖  File '{FILENAME}' is empty.{C.RESET}\n")
    exit(1)

total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

print(f"\n{C.WHITE}  File     :{C.RESET} {FILENAME} ({file_size/1024:.1f} KB, {total_chunks} chunks)")
print(f"{C.WHITE}  Server   :{C.RESET} {SERVER_IP}:{SERVER_PORT}")
print(f"{C.WHITE}  Window   :{C.RESET} {WINDOW_SIZE} packets")
print(f"{C.CYAN}{'━'*52}{C.RESET}")

# ─── Setup socket ─────────────────────────────────────────────────────────────
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(TIMEOUT)

# ─── Phase 1: INIT + Resume handshake ────────────────────────────────────────
section("Connecting to server...")

MAX_INIT_RETRIES = 5
start_seq = 0

for attempt in range(1, MAX_INIT_RETRIES + 1):
    try:
        init_packet = {"type": "INIT", "filename": FILENAME, "total_chunks": total_chunks}
        sock.sendto(json.dumps(init_packet).encode(), (SERVER_IP, SERVER_PORT))
        response, _ = sock.recvfrom(BUFFER_SIZE)
        resume_info = json.loads(response.decode())

        if resume_info.get("type") != "RESUME":
            print(f"\n{C.RED}  ✖  Unexpected server response.{C.RESET}\n")
            exit(1)

        start_seq = resume_info["last_seq"]
        if start_seq > 0:
            print(f"  {C.YELLOW}⟳  Resuming from chunk {start_seq} (skipping {start_seq} already received){C.RESET}")
        else:
            print(f"  {C.GREEN}✔  Server ready. Starting fresh transfer.{C.RESET}")
        break

    except socket.timeout:
        print(f"  {C.YELLOW}⚠  Attempt {attempt}/{MAX_INIT_RETRIES} timed out — retrying...{C.RESET}")
else:
    print(f"\n{C.RED}  ✖  Server not responding at {SERVER_IP}:{SERVER_PORT}{C.RESET}")
    print(f"{C.RED}     Check the server is running and the IP is correct.{C.RESET}\n")
    sock.close()
    exit(1)

# ─── Phase 2: Sliding window transfer ────────────────────────────────────────
section("Transferring file...")

base         = start_seq
acks         = set(range(start_seq))
retries      = 0
MAX_RETRIES  = 20
packets_sent = 0

transfer_start = time.time()

with open(FILENAME, "rb") as f:
    while base < total_chunks:

        if retries >= MAX_RETRIES:
            print(f"\n\n{C.RED}  ✖  Too many retries. Server may be down.{C.RESET}\n")
            sock.close()
            exit(1)

        window_end = min(base + WINDOW_SIZE, total_chunks)

        # Send unACKed packets in window
        for seq in range(base, window_end):
            if seq in acks:
                continue
            f.seek(seq * CHUNK_SIZE)
            chunk    = f.read(CHUNK_SIZE)
            checksum = hashlib.sha256(chunk).hexdigest()
            packet   = {
                "type":     "DATA",
                "seq":      seq,
                "data":     base64.b64encode(chunk).decode(),
                "checksum": checksum
            }
            sock.sendto(json.dumps(packet).encode(), (SERVER_IP, SERVER_PORT))
            packets_sent += 1
            time.sleep(0.05)

        # Collect ACKs
        try:
            while True:
                ack_raw, _ = sock.recvfrom(BUFFER_SIZE)
                ack = json.loads(ack_raw.decode())
                if ack.get("type") == "ACK":
                    acks.add(ack["seq"])
                    retries = 0
                while base in acks:
                    base += 1
                # Update progress bar
                print_progress(min(base, total_chunks), total_chunks)
                if base >= window_end:
                    break

        except socket.timeout:
            retries += 1
            print(f"\n  {C.YELLOW}⚠  Timeout — resending window from seq={base} (retry {retries}/{MAX_RETRIES}){C.RESET}")

# ─── Summary ──────────────────────────────────────────────────────────────────
elapsed    = time.time() - transfer_start
throughput = (file_size / 1024) / elapsed

print(f"\n\n{C.GREEN}{C.BOLD}{'━'*52}{C.RESET}")
print(f"{C.GREEN}{C.BOLD}    Transfer Complete!{C.RESET}")
print(f"{C.GREEN}{'━'*52}{C.RESET}")
print(f"{C.WHITE}  File size   :{C.RESET} {file_size} bytes ({file_size/1024:.1f} KB)")
print(f"{C.WHITE}  Chunks      :{C.RESET} {total_chunks}")
print(f"{C.WHITE}  Window size :{C.RESET} {WINDOW_SIZE}")
print(f"{C.WHITE}  Time taken  :{C.RESET} {elapsed:.2f} seconds")
print(f"{C.WHITE}  Throughput  :{C.RESET} {C.BOLD}{throughput:.2f} KB/s{C.RESET}")
print(f"{C.WHITE}  Pkts sent   :{C.RESET} {packets_sent} (includes retransmissions)")
print(f"{C.GREEN}{'━'*52}{C.RESET}\n")

sock.close()