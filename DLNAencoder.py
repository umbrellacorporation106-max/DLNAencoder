#!/usr/bin/env python3

import os
import json
import subprocess
import curses
import psutil
import signal
import time
import shutil
from datetime import timedelta, datetime

# --- Configuration ---
VERSION = "2.2.2"
CONFIG_DIR = os.path.expanduser('~/.config/DLNAencoder')
LOG_DIR = os.path.expanduser('~/.config/DLNAencoder/logs')
os.makedirs(LOG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
LAST_RUN_FILE = os.path.join(CONFIG_DIR, 'last_run.json')

def detect_hw_accel():
    """Proactively test if hardware encoders can actually be initialized."""
    for codec in ['h264_nvenc', 'h264_vaapi']:
        try:
            # Try to run a dummy encoding test to check if the encoder is functional
            # -f null - allows us to test the encoder without creating a file
            subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'testsrc=size=64x64:rate=1', 
                            '-c:v', codec, '-f', 'null', '-'], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return codec.split('_')[1] # returns 'nvenc' or 'vaapi'
        except subprocess.CalledProcessError:
            continue
    return None

hw_accel = detect_hw_accel()

def get_cpu_max_freq():
    """Reads the hardware maximum frequency in KHz."""
    try:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq', 'r') as f:
            return int(f.read().strip())
    except:
        return None

def get_cpu_governor():
    """Reads the current CPU governor."""
    try:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor', 'r') as f:
            return f.read().strip()
    except:
        return None

import threading

def run_cmd_async(cmd):
    """Run command in background to keep UI responsive."""
    def target():
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    threading.Thread(target=target, daemon=True).start()

def set_cpu_throttle(freq_ghz):
    """Limits frequency without forcing a specific governor."""
    run_cmd_async(['sudo', 'cpupower', 'frequency-set', '-u', f"{freq_ghz}GHz"])

def set_cpu_full_speed(freq_khz):
    """Sets governor to performance and resets frequency limit."""
    if freq_khz:
        freq_ghz = freq_khz / 1000000
        run_cmd_async(['sudo', 'cpupower', 'frequency-set', '-u', f"{freq_ghz}GHz"])
    run_cmd_async(['sudo', 'cpupower', 'frequency-set', '-g', 'performance'])

def restore_cpu_state(governor, freq_khz):
    """Restores the original governor and frequency limit."""
    try:
        # Restore frequency limit first
        if freq_khz:
            freq_ghz = freq_khz / 1000000
            subprocess.run(['sudo', 'cpupower', 'frequency-set', '-u', f"{freq_ghz}GHz"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Then restore original governor
        if governor:
            subprocess.run(['sudo', 'cpupower', 'frequency-set', '-g', governor], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        config = {
            "input_dir": os.path.expanduser('~/Videos'),
            "temp_dir": os.path.expanduser('~/DLNAencoder_temp'),
            "cpu_limit_ghz": 1.8, # Increased default to 1.8GHz for better balance
            "cpu_throttling_enabled": True
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return config
    with open(CONFIG_FILE, 'r') as f:
        cfg = json.load(f)
        if "cpu_limit_ghz" not in cfg:
            cfg["cpu_limit_ghz"] = 1.8
        if "cpu_throttling_enabled" not in cfg:
            cfg["cpu_throttling_enabled"] = True
        return cfg

def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=4)

config = load_config()
INPUT_DIR = config['input_dir']
TEMP_DIR = config['temp_dir']
CPU_LIMIT_GHZ = config.get('cpu_limit_ghz', 1.2)
CPU_THROTTLE_ENABLED = config.get('cpu_throttling_enabled', True)
PROGRESS_FILE = os.path.join(TEMP_DIR, 'ffmpeg_progress.txt')
os.makedirs(TEMP_DIR, exist_ok=True)

STATE_SELECTING = "SELECTING"
STATE_ENCODING = "ENCODING"
STATE_FINISHED = "FINISHED"

class EncoderApp:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.input_dir = INPUT_DIR
        self.files = self.scan_files(self.input_dir)
        self.file_statuses = [{'path': f, 'status': 'Pending', 'duration': 0, 'selected': True} for f in self.files]
        self.current_idx = 0
        self.cursor_idx = 0
        self.state = STATE_SELECTING
        self.paused = False
        self.running = True
        self.process = None
        self.log_file = None
        self.progress_data = {'progress': 0, 'eta': 'N/A', 'speed': 'N/A'}
        self.cpu_throttle_enabled = CPU_THROTTLE_ENABLED
        self.cpu_throttle_ghz = CPU_LIMIT_GHZ
        self.original_cpu_max = get_cpu_max_freq()
        self.original_governor = get_cpu_governor()
        self.show_help = False
        self.show_logs = False
        self.log_file = None
        
        # Persistent Summary Logic
        self.last_summary = self.load_last_run()
        self.is_persistent_summary = False
        if self.last_summary:
            self.state = STATE_FINISHED
            self.is_persistent_summary = True
            # Load the files list from disk or dummy it for display
            self.file_statuses = [{'path': 'Previous Batch', 'status': 'Completed' if i < self.last_summary['success'] else 'Failed'} for i in range(self.last_summary['total'])]
        
        if self.cpu_throttle_enabled:
            set_cpu_throttle(self.cpu_throttle_ghz)
        
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100)
        
    def scan_files(self, path):
        found = []
        if os.path.isfile(path):
            if path.lower().endswith(('.mkv', '.avi', '.webm', '.mov')):
                return [path]
            return []
        for root, _, files in os.walk(path):
            for f in files:
                if f.lower().endswith(('.mkv', '.avi', '.webm', '.mov')):
                    found.append(os.path.join(root, f))
        return sorted(found)

    def save_last_run(self):
        total = len(self.file_statuses)
        success = sum(1 for f in self.file_statuses if f['status'] == 'Completed')
        # Anything not 'Completed' is considered incomplete or failed
        failed = total - success
        self.last_summary = {
            'total': total,
            'success': success,
            'failed': failed
        }
        with open(LAST_RUN_FILE, 'w') as f:
            json.dump(self.last_summary, f)

    def load_last_run(self):
        if os.path.exists(LAST_RUN_FILE):
            try:
                with open(LAST_RUN_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return None

    def clear_last_run(self):
        if os.path.exists(LAST_RUN_FILE):
            try:
                os.remove(LAST_RUN_FILE)
            except:
                pass

    def get_duration(self, file_path):
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        try:
            return float(subprocess.check_output(cmd).decode().strip())
        except:
            return 0

    def update_progress(self, total_duration):
        try:
            if not os.path.exists(PROGRESS_FILE): return
            with open(PROGRESS_FILE, 'r') as f:
                lines = f.readlines()
                if not lines: return
                status = {}
                for line in lines[-20:]:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        status[k] = v
                if 'out_time_ms' in status:
                    curr_ms = int(status['out_time_ms']) / 1000000
                    self.progress_data['progress'] = min(curr_ms / total_duration, 1.0) if total_duration > 0 else 0
                    if 'speed' in status:
                        speed_str = status['speed'].replace('x', '')
                        self.progress_data['speed'] = f"{speed_str}x"
                        try:
                            speed = float(speed_str)
                            if speed > 0:
                                rem_sec = (total_duration - curr_ms) / speed
                                self.progress_data['eta'] = str(timedelta(seconds=int(rem_sec)))
                            else:
                                self.progress_data['eta'] = 'N/A'
                        except:
                            self.progress_data['eta'] = 'N/A'
                    else:
                        self.progress_data['speed'] = 'N/A'
                        self.progress_data['eta'] = 'N/A'
        except:
            pass

    def draw_progress_bar(self, y, x, width, fraction, label, color_pair):
        filled = int(width * fraction)
        percentage = int(fraction * 100)
        self.stdscr.attron(curses.color_pair(color_pair))
        self.stdscr.addstr(y, x, f"{label}: [")
        self.stdscr.addstr(y, x + len(label) + 3, "#" * filled)
        self.stdscr.addstr(y, x + len(label) + 3 + filled, "." * (width - filled) + "]")
        self.stdscr.addstr(y, x + len(label) + 3 + width + 2, f"{percentage}%")
        self.stdscr.attroff(curses.color_pair(color_pair))

    def get_input(self, prompt):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.attron(curses.A_REVERSE)
        self.stdscr.addstr(h-2, 0, " " * (w-1))
        self.stdscr.addstr(h-2, 2, f"{prompt}: ")
        self.stdscr.attroff(curses.A_REVERSE)
        
        self.stdscr.nodelay(False)
        curses.echo()
        curses.curs_set(1)
        input_str = self.stdscr.getstr(h-2, len(prompt) + 4).decode('utf-8')
        curses.noecho()
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        
        return input_str.strip()

    def toggle_throttle(self):
        self.cpu_throttle_enabled = not self.cpu_throttle_enabled
        if self.cpu_throttle_enabled:
            set_cpu_throttle(self.cpu_throttle_ghz)
        else:
            set_cpu_full_speed(self.original_cpu_max)

    def draw_help_screen(self):
        h, w = self.stdscr.getmaxyx()
        box_h, box_w = 16, 60
        start_y, start_x = (h - box_h) // 2, (w - box_w) // 2
        
        # Background "shadow" or just clear area
        for i in range(box_h):
            self.stdscr.addstr(start_y + i, start_x, " " * box_w, curses.A_REVERSE)
        
        self.stdscr.addstr(start_y + 1, start_x + 2, "--- DLNAencoder Controls ---", curses.A_REVERSE | curses.A_BOLD)
        
        controls = [
            ("Global:", ""),
            ("  q", "Quit"),
            ("  h", "Toggle Help"),
            ("  l", "View Error Logs"),
            ("  t", "Toggle CPU Throttle"),
            ("", ""),
            ("Selection:", ""),
            ("  Arrows", "Navigate Files"),
            ("  Space", "Toggle Selection"),
            ("  a / c / s", "Add / Change Dir / Speed"),
            ("  Enter", "Start Encoding"),
            ("", ""),
            ("Encoding:", ""),
            ("  p / r", "Pause / Resume"),
            ("  m", "Return to Menu (when finished)")
        ]
        
        for i, (key, desc) in enumerate(controls):
            if i + 3 < box_h:
                self.stdscr.addstr(start_y + 3 + i, start_x + 4, f"{key:<10} {desc}", curses.A_REVERSE)
        
        self.stdscr.addstr(start_y + box_h - 2, start_x + 2, "Press 'h' to close", curses.A_REVERSE | curses.A_ITALIC)

    def draw_log_viewer(self):
        h, w = self.stdscr.getmaxyx()
        box_h, box_w = h - 4, w - 4
        start_y, start_x = 2, 2
        
        for i in range(box_h):
            self.stdscr.addstr(start_y + i, start_x, " " * box_w, curses.A_REVERSE)
        
        # If no specific log is set, try to find the most recent one
        if not self.log_file or not os.path.exists(os.path.join(LOG_DIR, self.log_file)):
            logs = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')], key=lambda f: os.path.getmtime(os.path.join(LOG_DIR, f)), reverse=True)
            if logs:
                self.log_file = logs[0]
        
        self.stdscr.addstr(start_y + 1, start_x + 2, f"--- Error Log: {self.log_file if self.log_file else 'None'} ---", curses.A_REVERSE | curses.A_BOLD)
        
        if self.log_file and os.path.exists(os.path.join(LOG_DIR, self.log_file)):
            with open(os.path.join(LOG_DIR, self.log_file), 'r') as f:
                lines = f.readlines()
                # Display the last few lines that fit in the box
                display_lines = lines[-(box_h - 4):]
                for i, line in enumerate(display_lines):
                    self.stdscr.addstr(start_y + 3 + i, start_x + 2, line.strip()[:box_w-4], curses.A_REVERSE)
        else:
            self.stdscr.addstr(start_y + 3, start_x + 2, "No error log found.", curses.A_REVERSE)
        
        self.stdscr.addstr(start_y + box_h - 2, start_x + 2, "Press 'l' to close", curses.A_REVERSE | curses.A_ITALIC)

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        
        # Header
        self.stdscr.attron(curses.A_REVERSE)
        self.stdscr.addstr(0, 0, " " * (w-1))
        self.stdscr.addstr(0, 2, f"DLNAencoder Dashboard v{VERSION}")
        self.stdscr.attroff(curses.A_REVERSE)
        
        # Throttling Status (always visible)
        throttle_info = "Throttled" if self.cpu_throttle_enabled else "Full Speed"
        
        if self.state == STATE_SELECTING:
            self.stdscr.addstr(2, 2, f"Default Dir: {self.input_dir}", curses.color_pair(3))
            self.stdscr.addstr(3, 2, "Use Up/Down to move, Space to toggle, Enter to start encoding.", curses.A_BOLD)
            
            y = 5
            self.stdscr.addstr(y, 2, "File Selection:", curses.A_UNDERLINE)
            y += 1
            for i, entry in enumerate(self.file_statuses):
                if y >= h - 4: break
                cursor = "> " if i == self.cursor_idx else "  "
                checked = "[X]" if entry['selected'] else "[ ]"
                self.stdscr.addstr(y, 2, f"{cursor}{checked} {os.path.basename(entry['path'])}")
                y += 1
            
            # Use a slightly safer boundary to avoid _curses.error
            footer = " 'a' Add | 'c' Dir | 's' Speed | 't' Throttle | 'h' Help | 'l' Logs | Enter Start | 'q' Quit "
            if len(footer) < w:
                self.stdscr.addstr(h-1, 0, footer[:w-1], curses.A_REVERSE)

        elif self.state in [STATE_ENCODING, STATE_FINISHED]:
            # System Metrics
            cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0
            temps = psutil.sensors_temperatures()
            temp_str = "N/A"
            if temps:
                for name, entries in temps.items():
                    if entries: temp_str = f"{entries[0].current}°C"
                    break

            if self.state == STATE_FINISHED:
                header = "Welcome Back!" if self.is_persistent_summary else "Batch Complete!"
                self.stdscr.addstr(1, 2, header, curses.A_BOLD | curses.color_pair(1))
                
                if self.last_summary:
                    total = self.last_summary['total']
                    success = self.last_summary['success']
                    failed = self.last_summary['failed']
                else:
                    total = len(self.file_statuses)
                    success = sum(1 for f in self.file_statuses if f['status'] == 'Completed')
                    failed = total - success
                
                if failed == 0:
                    msg = f"[SUCCESS] All {total} files were encoded successfully!"
                    self.stdscr.addstr(3, 2, msg, curses.color_pair(1) | curses.A_BOLD)
                else:
                    msg = f"[COMPLETED] Batch finished! {success} succeeded, but {failed} file(s) were incomplete or failed."
                    self.stdscr.addstr(3, 2, msg, curses.color_pair(2) | curses.A_BOLD)

            status_text = "FINISHED" if self.state == STATE_FINISHED else ("PAUSED" if self.paused else f"RUNNING ({throttle_info})")
            # Move system metrics down if in FINISHED state to avoid overlap
            metrics_y = 5 if self.state == STATE_FINISHED else 2
            self.stdscr.addstr(metrics_y, 2, f"CPU Freq: {cpu_freq/1000:.2f} GHz", curses.color_pair(3))
            self.stdscr.addstr(metrics_y, 25, f"CPU Temp: {temp_str}", curses.color_pair(2))
            self.stdscr.addstr(metrics_y, 45, f"Status: {status_text}")
            
            # Progress Bars
            if not self.is_persistent_summary:
                pb_start_y = 7 if self.state == STATE_FINISHED else 4
                total_selected = len(self.file_statuses)
                overall_prog = self.current_idx / total_selected if total_selected > 0 else 1
                self.draw_progress_bar(pb_start_y, 2, 40, overall_prog, "Overall", 1)
                self.stdscr.addstr(pb_start_y, 60, f"({self.current_idx}/{total_selected} COMPLETED)")
                
                # Current file progress
                self.draw_progress_bar(pb_start_y + 2, 2, 40, self.progress_data['progress'], "Current", 1)
                self.stdscr.addstr(pb_start_y + 2, 60, f"ETA: {self.progress_data['eta']}")
                self.stdscr.addstr(pb_start_y + 2, 75, f"Speed: {self.progress_data['speed']}")
                
                # Files List
                y = pb_start_y + 4
                self.stdscr.addstr(y, 2, "Encoding Queue:", curses.A_UNDERLINE)
                y += 1
                for i, entry in enumerate(self.file_statuses):
                    if y >= h - 2: break
                    color = curses.color_pair(1) if entry['status'] == 'Completed' else \
                            curses.color_pair(2) if entry['status'] == 'Encoding' else 0
                    self.stdscr.addstr(y, 4, f"[{entry['status']}] {os.path.basename(entry['path'])}", color)
                    y += 1
            
            if self.state == STATE_ENCODING:
                footer = " 'p' Pause | 'r' Resume | 't' Toggle Throttle | 'h' Help | 'l' Logs | 'q' Quit "
            else:
                footer = " 'm' Menu | 't' Toggle Throttle | 'h' Help | 'l' Logs | 'q' Quit "
            if len(footer) < w:
                self.stdscr.addstr(h-1, 0, footer[:w-1], curses.A_REVERSE)


        if self.show_help:
            self.draw_help_screen()
        
        if self.show_logs:
            self.draw_log_viewer()

        self.stdscr.refresh()

    def run(self):
        try:
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_BLACK)
            
            while self.running:
                key = self.stdscr.getch()
                
                # Global Controls
                if key == ord('q'):
                    self.running = False
                elif key == ord('t'):
                    self.toggle_throttle()
                elif key == ord('h'):
                    self.show_help = not self.show_help
                elif key == ord('l'):
                    self.show_logs = not self.show_logs
                
                if self.state == STATE_SELECTING:
                    if key == curses.KEY_UP:
                        self.cursor_idx = max(0, self.cursor_idx - 1)
                    elif key == curses.KEY_DOWN:
                        self.cursor_idx = min(len(self.file_statuses) - 1, self.cursor_idx + 1)
                    elif key == ord(' '):
                        if self.file_statuses:
                            self.file_statuses[self.cursor_idx]['selected'] = not self.file_statuses[self.cursor_idx]['selected']
                    elif key == ord('a'):
                        path = self.get_input("Add Path")
                        if path and os.path.exists(path):
                            new_files = self.scan_files(path)
                            for nf in new_files:
                                if not any(f['path'] == nf for f in self.file_statuses):
                                    self.file_statuses.append({'path': nf, 'status': 'Pending', 'duration': 0, 'selected': True})
                    elif key == ord('c'):
                        new_dir = self.get_input("New Default Dir")
                        if new_dir and os.path.exists(new_dir):
                            self.input_dir = new_dir
                            config['input_dir'] = new_dir
                            save_config(config)
                            self.files = self.scan_files(self.input_dir)
                            self.file_statuses = [{'path': f, 'status': 'Pending', 'duration': 0, 'selected': True} for f in self.files]
                            self.cursor_idx = 0
                            self.current_idx = 0
                    elif key == ord('s'):
                        new_speed = self.get_input("Set Throttle Speed (GHz)")
                        try:
                            val = float(new_speed)
                            self.cpu_throttle_ghz = val
                            config['cpu_limit_ghz'] = val
                            save_config(config)
                        except:
                            pass
                    elif key in [10, 13]: # Enter
                        selected_files = [f for f in self.file_statuses if f['selected']]
                        if selected_files:
                            self.file_statuses = selected_files
                            self.state = STATE_ENCODING
                            self.current_idx = 0
                
                elif self.state == STATE_ENCODING:
                    if key == ord('p'):
                        self.paused = True
                        if self.process: self.process.send_signal(signal.SIGSTOP)
                    elif key == ord('r'):
                        self.paused = False
                        if self.process: self.process.send_signal(signal.SIGCONT)
                        
                    if not self.paused and self.current_idx < len(self.file_statuses):
                        self.process_file()
                    elif self.current_idx >= len(self.file_statuses):
                        self.state = STATE_FINISHED
                        self.save_last_run()
                        self.is_persistent_summary = False
                
                elif self.state == STATE_FINISHED:
                    if key == ord('m'):
                        self.clear_last_run()
                        self.last_summary = None
                        self.is_persistent_summary = False
                        self.state = STATE_SELECTING
                        # Re-scan and preserve status for display? No, reset for new batch
                        self.files = self.scan_files(self.input_dir)
                        self.file_statuses = [{'path': f, 'status': 'Pending', 'duration': 0, 'selected': True} for f in self.files]
                        self.current_idx = 0
                        self.cursor_idx = 0
                        self.progress_data = {'progress': 0, 'eta': 'N/A', 'speed': 'N/A'}

                self.draw()
                time.sleep(0.1)
        finally:
            if self.state == STATE_ENCODING:
                self.save_last_run()
            if self.process:
                try: self.process.kill()
                except: pass
            restore_cpu_state(self.original_governor, self.original_cpu_max)

    def process_file(self):
        file_path = self.file_statuses[self.current_idx]['path']
        temp_out = os.path.join(TEMP_DIR, f"{os.path.basename(file_path)}_tmp.mp4")
        log_name = f"{os.path.basename(file_path)}.log"

        if not self.process:
            # Check if file exists before processing
            if not os.path.exists(file_path):
                self.file_statuses[self.current_idx]['status'] = 'Failed'
                self.log_file = log_name
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(os.path.join(LOG_DIR, log_name), 'a') as f:
                    f.write(f"[{timestamp}] Encoding Failed:\nError: Input file does not exist: {file_path}\n")
                self.current_idx += 1
                return

            self.file_statuses[self.current_idx]['status'] = 'Encoding'
            self.file_statuses[self.current_idx]['duration'] = self.get_duration(file_path)
            if os.path.exists(PROGRESS_FILE): os.remove(PROGRESS_FILE)
            
            cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-progress', PROGRESS_FILE]
            cmd.extend(['-i', file_path])
            if hw_accel == 'nvenc':
                cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p6'])
            elif hw_accel == 'vaapi':
                cmd.extend(['-c:v', 'h264_vaapi'])
            else:
                cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast'])
            
            cmd.extend(['-crf', '23', temp_out])
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            
        self.update_progress(self.file_statuses[self.current_idx]['duration'])
            
        if self.process.poll() is not None:
            _, stderr = self.process.communicate()
            if self.process.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                final_out = os.path.splitext(file_path)[0] + ".mp4"
                try:
                    shutil.move(temp_out, final_out)
                    if os.path.exists(file_path) and os.path.abspath(file_path) != os.path.abspath(final_out):
                        os.remove(file_path)
                    self.file_statuses[self.current_idx]['status'] = 'Completed'
                except Exception:
                    self.file_statuses[self.current_idx]['status'] = 'Error'
            else:
                self.file_statuses[self.current_idx]['status'] = 'Failed'
                self.log_file = log_name
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Ensure directory exists just in case
                os.makedirs(LOG_DIR, exist_ok=True)
                with open(os.path.join(LOG_DIR, log_name), 'a') as f:
                    reason = "Encoding Interrupted" if self.process.returncode < 0 else "Encoder Error"
                    f.write(f"[{timestamp}] {reason} (Code {self.process.returncode}):\n{stderr.decode()}\n")
                if os.path.exists(temp_out):
                    try: os.remove(temp_out)
                    except: pass
            self.process = None
            self.progress_data = {'progress': 0, 'eta': 'N/A', 'speed': 'N/A'}
            self.current_idx += 1

def main(stdscr):
    app = EncoderApp(stdscr)
    app.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
