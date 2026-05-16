import os
import json
import subprocess
import time
import signal
import psutil
import sys
import select
import argparse
import shutil

# --- Configuration Constants ---
CONFIG_DIR = os.path.expanduser('~/.config/DLNAencoder')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

# --- ANSI Color Codes ---
CLR_HDR   = '\033[1;97;44m' # Bold White on Blue
CLR_LABEL = '\033[1;34m'    # Bold Blue
CLR_VAL   = '\033[0m'       # Reset
CLR_BAR   = '\033[36m'      # Cyan
CLR_SPEED = '\033[1;32m'    # Bold Green
CLR_TEMP  = '\033[1;33m'    # Bold Yellow
CLR_RESET = '\033[0m'
CLR_ERR   = '\033[1;31m'    # Bold Red

def setup_config():
    """Interactive setup for DLNAencoder configuration."""
    print(f"{CLR_HDR}  DLNAencoder: First-time Setup  {CLR_RESET}")
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    input_dir = input(f"{CLR_LABEL}Default input directory:{CLR_VAL} ").strip()
    while not input_dir or not os.path.isdir(input_dir):
        print(f"{CLR_ERR}Error:{CLR_RESET} Please enter a valid directory.")
        input_dir = input(f"{CLR_LABEL}Default input directory:{CLR_VAL} ").strip()
        
    temp_dir = input(f"{CLR_LABEL}Default temporary directory:{CLR_VAL} ").strip()
    if not temp_dir:
        temp_dir = os.path.expanduser('~/DLNAencoder_temp')
    
    cpu_throttling = input(f"{CLR_LABEL}Enable CPU throttling? (y/n):{CLR_VAL} ").lower() == 'y'
    cpu_limit = 1.2
    if cpu_throttling:
        try:
            limit_input = input(f"{CLR_LABEL}CPU Frequency limit (GHz) [default 1.2]:{CLR_VAL} ").strip()
            if limit_input:
                cpu_limit = float(limit_input)
        except ValueError:
            print(f"{CLR_ERR}Invalid input.{CLR_RESET} Using default 1.2 GHz.")
            
    config = {
        "input_dir": os.path.abspath(input_dir),
        "temp_dir": os.path.abspath(temp_dir),
        "cpu_throttling_enabled": cpu_throttling,
        "cpu_limit_ghz": cpu_limit
    }
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    print(f"\n{CLR_SPEED}Configuration saved to {CONFIG_FILE}{CLR_RESET}\n")
    return config

def load_config():
    """Loads the configuration file or starts setup if missing."""
    if not os.path.exists(CONFIG_FILE):
        return setup_config()
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"{CLR_ERR}Error loading config:{CLR_RESET} {e}")
        return setup_config()

# Load configuration
config = load_config()

# Set variables from config
INPUT_DIR = config.get('input_dir')
TEMP_DIR = config.get('temp_dir')
CPU_THROTTLE_ENABLED = config.get('cpu_throttling_enabled', False)
CPU_LIMIT_GHZ = config.get('cpu_limit_ghz', 1.2)
PROGRESS_FILE = os.path.join(TEMP_DIR, 'ffmpeg_progress.txt')

os.makedirs(TEMP_DIR, exist_ok=True)

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="DLNAencoder Dashboard (Omarchy Support)")
parser.add_argument('path', nargs='?', default=INPUT_DIR, help=f"Path to encode (default: {INPUT_DIR})")
args = parser.parse_args()

target_path = os.path.abspath(args.path)

# --- File Scanning Logic ---
def scan_files(path):
    found = []
    if os.path.isfile(path):
        if not path.lower().endswith('.mp4') and path.lower().endswith(('.mkv', '.avi', '.webm', '.mov')):
            found.append(path)
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for f in files:
                full_path = os.path.join(root, f)
                if not f.lower().endswith('.mp4') and f.lower().endswith(('.mkv', '.avi', '.webm', '.mov')):
                    if not f.endswith('_tmp.mp4'):
                        found.append(full_path)
    return found

files = scan_files(target_path)
total = len(files)
count = 0
STOP_REQUESTED = False
ORIGINAL_CPU_MAX = None

def timed_input(prompt, timeout=300):
    """Wait for input with a countdown, defaults to 'y' on timeout."""
    start_time = time.time()
    print('\033[?25h', end='') # Show cursor
    while True:
        elapsed = time.time() - start_time
        remaining = int(timeout - elapsed)
        if remaining <= 0:
            print(f"\033[8;1H\033[K {CLR_LABEL}Timeout reached. Proceeding...{CLR_RESET}")
            return 'y'
        
        print(f"\033[8;1H\033[K {CLR_LABEL}{prompt}{CLR_RESET} ({remaining}s) [Y/n]: ", end='', flush=True)
        
        rlist, _, _ = select.select([sys.stdin], [], [], 1)
        if rlist:
            res = sys.stdin.readline().strip().lower()
            return res if res else 'y'
        
        if STOP_REQUESTED:
            return 'n'

def get_cpu_max_freq():
    try:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq', 'r') as f:
            return f.read().strip()
    except Exception:
        return None

def set_cpu_limit(freq_ghz):
    try:
        subprocess.run(['sudo', 'cpupower', 'frequency-set', '-u', f'{freq_ghz}GHz'], 
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def restore_cpu_limit(freq_khz):
    if freq_khz:
        try:
            freq_ghz = f"{int(freq_khz) / 1000000:.2f}GHz"
            subprocess.run(['sudo', 'cpupower', 'frequency-set', '-u', freq_ghz], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def verify_integrity(file_path):
    """Checks if the file is a valid video and not empty."""
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return False
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        output = subprocess.check_output(cmd).decode().strip()
        return float(output) > 0
    except Exception:
        return False

def draw_bar(p, label=""):
    w = 35
    p = max(0, min(100, p))
    filled_len = int(p * w / 100)
    filled = '█' * filled_len
    empty = ' ' * (w - filled_len)
    return f'{CLR_BAR}▕{filled}{empty}▏{CLR_RESET} {p:5.1f}% {label}'

def cleanup(sig, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def get_cpu_info():
    try:
        freq = psutil.cpu_freq().current / 1000.0
        temps = psutil.sensors_temperatures()
        cpu_temp = 0
        for name in ['k10temp', 'coretemp', 'cpu_thermal', 'acpitz']:
            if name in temps:
                cpu_temp = temps[name][0].current
                break
        return freq, cpu_temp
    except Exception:
        return 0.0, 0.0

# --- Execution ---

if total == 0:
    print(f"{CLR_LABEL}SCAN COMPLETE:{CLR_VAL} No files needing encoding found in {target_path}.")
    exit(0)

print(f"{CLR_LABEL}FOUND {total} FILES IN {target_path}:{CLR_RESET}")
for f in files:
    print(f"  • {os.path.basename(f)}")

if input(f"\n{CLR_LABEL}Start batch encoding?{CLR_RESET} (y/n): ").lower() != 'y':
    print("Exiting.")
    exit(0)

print('\033[2J\033[H\033[?25l', end='')
print(f"{CLR_HDR}  DLNAencoder DASHBOARD (Omarchy Support)  {CLR_RESET}")
print("-" * 65)

if CPU_THROTTLE_ENABLED:
    ORIGINAL_CPU_MAX = get_cpu_max_freq()
    if ORIGINAL_CPU_MAX:
        print(f"\033[7;1H\033[K {CLR_LABEL}STATUS:{CLR_RESET} Initializing CPU Throttle ({CPU_LIMIT_GHZ}GHz)...")
        set_cpu_limit(CPU_LIMIT_GHZ)

try:
    for file_path in files:
        if STOP_REQUESTED:
            break
        
        count += 1
        filename = os.path.basename(file_path)
        file_dir = os.path.dirname(file_path)
        temp_out = os.path.join(TEMP_DIR, f'{os.path.splitext(filename)[0]}_tmp.mp4')
        final_out = os.path.join(file_dir, f'{os.path.splitext(filename)[0]}.mp4')

        try:
            duration_sec = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]))
            duration_us = int(duration_sec * 1000000)
        except Exception:
            print(f'\033[7;1H\033[K{CLR_ERR}ERROR:{CLR_RESET} ffprobe failed for {filename}')
            continue

        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', 
            '-i', file_path, 
            '-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', 
            '-profile:v', 'high', '-level', '4.1', '-pix_fmt', 'yuv420p', 
            '-c:a', 'libmp3lame', '-q:a', '2', 
            '-movflags', '+faststart', 
            '-progress', PROGRESS_FILE, temp_out, '-y'
        ]
        
        if os.path.exists(PROGRESS_FILE): os.remove(PROGRESS_FILE)
            
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        while process.poll() is None:
            if STOP_REQUESTED:
                process.terminate()
                break
            
            out_time_us = 0
            speed_str = '0.00x'
            speed_float = 0.0

            if os.path.exists(PROGRESS_FILE):
                try:
                    with open(PROGRESS_FILE, 'r') as f:
                        lines = f.readlines()
                        for line in reversed(lines):
                            if 'out_time_ms=' in line:
                                out_time_us = int(line.split('=')[1])
                            if 'speed=' in line:
                                speed_str = line.split('=')[1].strip()
                                speed_float = float(speed_str.replace('x', '')) if 'x' in speed_str else 0.0
                            if out_time_us > 0 and speed_float > 0:
                                break
                except Exception: pass

            current_p = (out_time_us * 100.0) / duration_us if duration_us > 0 else 0
            overall_p = ((count - 1) * 100.0 + current_p) / total
            freq, temp = get_cpu_info()
            
            eta_str = "--:--:--"
            if speed_float > 0.01:
                rem_sec = ((duration_us - out_time_us) / 1000000.0) / speed_float
                if rem_sec > 0: eta_str = time.strftime('%H:%M:%S', time.gmtime(rem_sec))

            display_name = filename if len(filename) < 25 else filename[:22] + "..."
            
            print(f"\033[3;1H\033[K {CLR_LABEL}OVERALL {CLR_RESET} {draw_bar(overall_p, f'({count}/{total})')}")
            print(f"\033[4;1H\033[K {CLR_LABEL}CURRENT {CLR_RESET} {draw_bar(current_p, f'({display_name})')}")
            print("-" * 65)
            print(f"\033[6;1H\033[K {CLR_LABEL}SPEED:{CLR_VAL} {CLR_SPEED}{speed_str:<7}{CLR_RESET} | {CLR_LABEL}CPU:{CLR_VAL} {freq:.2f}GHz | {CLR_LABEL}TEMP:{CLR_VAL} {CLR_TEMP}{temp:.1f}°C{CLR_RESET} | {CLR_LABEL}ETA:{CLR_VAL} {eta_str}")
            
            time.sleep(1)

        process.wait()
        
        if not STOP_REQUESTED:
            if verify_integrity(temp_out):
                if os.path.exists(file_path): os.remove(file_path)
                if os.path.exists(temp_out): shutil.move(temp_out, final_out)
            else:
                print(f'\033[7;1H\033[K{CLR_ERR}CRITICAL ERROR:{CLR_RESET} Integrity check failed for {filename}.')
                if os.path.exists(temp_out): os.remove(temp_out)
                STOP_REQUESTED = True
                break
            
            if count < total:
                if timed_input(f"Batch progress: {count}/{total} complete. Continue?", timeout=300) == 'n':
                    STOP_REQUESTED = True
                    break
                print('\033[?25l', end='')
        else:
            if os.path.exists(temp_out): os.remove(temp_out)
            break

finally:
    if ORIGINAL_CPU_MAX:
        print(f"\033[8;1H\033[K {CLR_LABEL}STATUS:{CLR_RESET} Restoring CPU speed...")
        restore_cpu_limit(ORIGINAL_CPU_MAX)
    print('\033[?25h')
    if STOP_REQUESTED:
        print(f'\n{CLR_ERR}Encoding cancelled by user.{CLR_RESET}')
    else:
        print(f'\n{CLR_SPEED}Success!{CLR_RESET} Finished processing {total} files.')
