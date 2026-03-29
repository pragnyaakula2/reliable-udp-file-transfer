import socket
import json
import hashlib
import os
import base64
import time

# ─── ANSI Colors ─────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    WHITE  = "\033[97m"
    DIM    = "\033[2m"
    BLUE   = "\033[94m"

def banner():
    print(f"\n{C.CYAN}{C.BOLD}{'━'*52}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}    UDP Reliable File Transfer — SERVER{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}{'━'*52}{C.RESET}")

def log_info(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  {C.DIM}[{ts}]{C.RESET} {msg}")

def log_ok(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  {C.DIM}[{ts}]{C.RESET} {C.GREEN}✔{C.RESET}  {msg}")

def log_warn(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  {C.DIM}[{ts}]{C.RESET} {C.YELLOW}⚠{C.RESET}  {msg}")

def log_err(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  {C.DIM}[{ts}]{C.RESET} {C.RED}✖{C.RESET}  {msg}")

def log_send(seq, addr):
    ts = time.strftime("%H:%M:%S")
    print(f"  {C.DIM}[{ts}]{C.RESET} {C.BLUE}↓{C.RESET}  seq={C.BOLD}{seq}{C.RESET}  from {addr[0]}:{addr[1]}")

# ─── Configuration ───────────────────────────────────────────────────────────
SERVER_IP   = "0.0.0.0"
SERVER_PORT = 5001
BUFFER_SIZE = 65535
CHUNK_SIZE  = 1024

banner()
print(f"\n{C.WHITE}  Host     :{C.RESET} {SERVER_IP}")
print(f"{C.WHITE}  Port     :{C.RESET} {SERVER_PORT}")
print(f"{C.WHITE}  Chunk sz :{C.RESET} {CHUNK_SIZE} bytes")
print(f"{C.CYAN}{'━'*52}{C.RESET}\n")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((SERVER_IP, SERVER_PORT))

print(f"  {C.GREEN}{C.BOLD}Listening for connections...{C.RESET}\n")
print(f"{C.DIM}{'─'*52}{C.RESET}")

client_data = {}

while True:
    try:
        raw, addr = sock.recvfrom(BUFFER_SIZE)
        packet = json.loads(raw.decode())
        ptype  = packet.get("type")

        if addr not in client_data:
            client_data[addr] = {
                "received_chunks": set(),
                "expected_chunks": None,
                "save_file":       "",
                "temp_dir":        ""
            }

        # ── INIT ─────────────────────────────────────────────────────────────
        if ptype == "INIT":
            total_chunks = packet["total_chunks"]
            filename     = packet["filename"]
            base_name    = os.path.splitext(filename)[0]
            save_file    = f"received_{base_name}.bin"
            temp_dir     = f"chunks_{base_name}"

            client_data[addr]["expected_chunks"] = total_chunks
            client_data[addr]["save_file"]       = save_file
            client_data[addr]["temp_dir"]        = temp_dir

            os.makedirs(temp_dir, exist_ok=True)
            saved_seqs = set()
            for fn in os.listdir(temp_dir):
                if fn.startswith("chunk_") and fn.endswith(".bin"):
                    try:
                        saved_seqs.add(int(fn.split("_")[1].split(".")[0]))
                    except:
                        pass
            client_data[addr]["received_chunks"] = saved_seqs

            last_seq = total_chunks
            for i in range(total_chunks):
                if i not in saved_seqs:
                    last_seq = i
                    break

            print()
            log_info(f"{C.BOLD}New client:{C.RESET} {addr[0]}:{addr[1]}")
            log_info(f"File: {C.BOLD}{filename}{C.RESET} | Chunks: {total_chunks} | Resume from: {C.YELLOW}{last_seq}{C.RESET}")
            print(f"{C.DIM}{'─'*52}{C.RESET}")

            response = {"type": "RESUME", "last_seq": last_seq}
            sock.sendto(json.dumps(response).encode(), addr)

        # ── DATA ─────────────────────────────────────────────────────────────
        elif ptype == "DATA":

            # Guard: DATA before INIT
            if client_data[addr]["expected_chunks"] is None:
                log_warn(f"DATA received before INIT from {addr} — ignoring")
                continue

            seq        = packet["seq"]
            checksum   = packet["checksum"]
            chunk_data = base64.b64decode(packet["data"])

            # Integrity check
            if hashlib.sha256(chunk_data).hexdigest() != checksum:
                log_warn(f"Checksum FAILED seq={seq} from {addr[0]}:{addr[1]} — discarded")
                continue

            temp_dir   = client_data[addr]["temp_dir"]
            chunk_path = os.path.join(temp_dir, f"chunk_{seq}.bin")

            if seq not in client_data[addr]["received_chunks"]:
                with open(chunk_path, "wb") as cf:
                    cf.write(chunk_data)
                client_data[addr]["received_chunks"].add(seq)

            log_send(seq, addr)

            ack = {"type": "ACK", "seq": seq}
            sock.sendto(json.dumps(ack).encode(), addr)

            # ── Check complete ────────────────────────────────────────────
            expected = client_data[addr]["expected_chunks"]
            received = client_data[addr]["received_chunks"]

            if expected is not None and len(received) == expected:
                save_file = client_data[addr]["save_file"]

                with open(save_file, "wb") as f:
                    for i in range(expected):
                        cp = os.path.join(temp_dir, f"chunk_{i}.bin")
                        with open(cp, "rb") as cf:
                            f.write(cf.read())

                for fn in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, fn))
                os.rmdir(temp_dir)

                print(f"{C.DIM}{'─'*52}{C.RESET}")
                log_ok(f"{C.GREEN}{C.BOLD}Transfer complete{C.RESET} from {addr[0]}:{addr[1]}")
                log_ok(f"Saved as {C.BOLD}'{save_file}'{C.RESET}")
                print(f"{C.DIM}{'─'*52}{C.RESET}\n")

                del client_data[addr]

    except json.JSONDecodeError:
        log_warn("Received malformed packet — ignored")
    except Exception as e:
        log_err(f"Unexpected error: {e}")