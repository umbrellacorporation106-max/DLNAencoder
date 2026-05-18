#!/usr/bin/env python3

import os
import json
import subprocess
import curses
import psutil
import signal
import time
import shutil
from datetime import timedelta

# --- Configuration ---
VERSION = "2.0.1"
CONFIG_DIR = os.path.expanduser('~/.config/DLNAencoder')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        config = {
            "input_dir": os.path.expanduser('~/Videos'),
            "temp_dir": os.path.expanduser('~/DLNAencoder_temp'),
            "cpu_limit_ghz": 1.2
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return config
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

config = load_config()
INPUT_DIR = config['input_dir']
TEMP_DIR = config['temp_dir']
PROGRESS_FILE = os.path.join(TEMP_DIR, 'ffmpeg_progress.txt')
os.makedirs(TEMP_DIR, exist_ok=True)

class EncoderApp:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.files = self.scan_files(INPUT_DIR)
        self.total_files = len(self.files)
        self.current_idx = 0
        self.paused = False
        self.running = True
        self.process = None
        self.file_statuses = [{'path': f, 'status': 'Pending', 'duration': 0} for f in self.files]
        self.progress_data = {'progress': 0, 'eta': 'N/A', 'speed': 'N/A'}
        
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100)
        
    def scan_files(self, path):
        found = []
        for root, _, files in os.walk(path):
            for f in files:
                if f.lower().endswith(('.mkv', '.avi', '.webm', '.mov')):
                    found.append(os.path.join(root, f))
        return found

    def get_duration(self, file_path):
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        try:
            return float(subprocess.check_output(cmd).decode().strip())
        except:
            return 0

    def update_progress(self, total_duration):
        try:
            if not os.path.exists(PROGRESS_FILE): return
            
            # Read last few lines to find current status
            with open(PROGRESS_FILE, 'r') as f:
                lines = f.readlines()
                if not lines: return
                
                status = {}
                for line in lines[-20:]: # Check last 20 lines
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        status[k] = v
                
                if 'out_time_ms' in status:
                    curr_ms = int(status['out_time_ms']) / 1000000
                    self.progress_data['progress'] = min(curr_ms / total_duration, 1.0) if total_duration > 0 else 0
                    
                    if 'speed' in status:
                        speed_str = status['speed'].replace('x', '')
                        self.progress_data['speed'] = f"{speed_str}x"
                        speed = float(speed_str)
                        if speed > 0:
                            rem_sec = (total_duration - curr_ms) / speed
                            self.progress_data['eta'] = str(timedelta(seconds=int(rem_sec)))
                        else:
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

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        
        # Header
        self.stdscr.attron(curses.A_REVERSE)
        self.stdscr.addstr(0, 0, " " * w)
        self.stdscr.addstr(0, 2, "DLNAencoder Dashboard")
        self.stdscr.attroff(curses.A_REVERSE)
        
        # System Metrics
        cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0
        temps = psutil.sensors_temperatures()
        temp_str = "N/A"
        if temps:
            for name, entries in temps.items():
                temp_str = f"{entries[0].current}°C"
                break

        self.stdscr.addstr(2, 2, f"CPU Freq: {cpu_freq/1000:.2f} GHz", curses.color_pair(3))
        self.stdscr.addstr(2, 25, f"CPU Temp: {temp_str}", curses.color_pair(2))
        self.stdscr.addstr(2, 45, f"Status: {'PAUSED' if self.paused else 'RUNNING'}")
        
        # Progress Bars
        overall_prog = self.current_idx / self.total_files if self.total_files > 0 else 1
        self.draw_progress_bar(4, 2, 40, overall_prog, "Overall", 1)
        self.stdscr.addstr(4, 60, f"({self.current_idx}/{self.total_files} COMPLETED)")
        
        # Current file progress
        self.draw_progress_bar(6, 2, 40, self.progress_data['progress'], "Current", 1)
        self.stdscr.addstr(6, 60, f"ETA: {self.progress_data['eta']}")
        self.stdscr.addstr(6, 75, f"Speed: {self.progress_data['speed']}")
        
        # Files List
        y = 8
        self.stdscr.addstr(y, 2, "File Queue:", curses.A_UNDERLINE)
        y += 1
        for i, entry in enumerate(self.file_statuses):
            if y >= h - 2: break
            color = curses.color_pair(1) if entry['status'] == 'Completed' else \
                    curses.color_pair(2) if entry['status'] == 'Encoding' else 0
            self.stdscr.addstr(y, 4, f"[{entry['status']}] {os.path.basename(entry['path'])}", color)
            y += 1
            
        self.stdscr.addstr(h-1, 0, " Controls: 'p' Pause | 'r' Resume | 'q' Quit ", curses.A_REVERSE)
        self.stdscr.refresh()

    def run(self):
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_BLACK)
        
        while self.running:
            key = self.stdscr.getch()
            if key == ord('q'):
                self.running = False
            elif key == ord('p'):
                self.paused = True
                if self.process: self.process.send_signal(signal.SIGSTOP)
            elif key == ord('r'):
                self.paused = False
                if self.process: self.process.send_signal(signal.SIGCONT)
                
            if not self.paused and self.current_idx < self.total_files:
                self.process_file()
            
            self.draw()
            time.sleep(0.1)
            
        if self.process: self.process.kill()

    def process_file(self):
        file_path = self.file_statuses[self.current_idx]['path']
        temp_out = os.path.join(TEMP_DIR, f"{os.path.basename(file_path)}_tmp.mp4")

        if not self.process:
            self.file_statuses[self.current_idx]['status'] = 'Encoding'
            self.file_statuses[self.current_idx]['duration'] = self.get_duration(file_path)
            
            if os.path.exists(PROGRESS_FILE): os.remove(PROGRESS_FILE)
            
            cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-progress', PROGRESS_FILE, '-i', file_path, '-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', temp_out]
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        self.update_progress(self.file_statuses[self.current_idx]['duration'])
            
        if self.process.poll() is not None:
            # Check if encoding was successful (return code 0 and non-empty file)
            if self.process.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                final_out = os.path.splitext(file_path)[0] + ".mp4"
                try:
                    # Move to final destination
                    shutil.move(temp_out, final_out)
                    
                    # Remove original source file if it was moved/copied successfully
                    # and it's not the same as the final output
                    if os.path.exists(file_path) and os.path.abspath(file_path) != os.path.abspath(final_out):
                        os.remove(file_path)
                    
                    self.file_statuses[self.current_idx]['status'] = 'Completed'
                except Exception:
                    self.file_statuses[self.current_idx]['status'] = 'Error'
            else:
                self.file_statuses[self.current_idx]['status'] = 'Failed'
                # Clean up temp file if it exists and failed
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
