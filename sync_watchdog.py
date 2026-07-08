import os
import shutil
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SOURCE = "/storage/emulated/0/termux/skriptorij_acode"
DEST = "/root/skriptorij"
SYNCING = False

def get_mtime(path):
    try:
        return os.path.getmtime(path)
    except:
        return 0

class SyncHandler(FileSystemEventHandler):
    def __init__(self, src_dir, dst_dir, direction):
        self.src_dir = src_dir
        self.dst_dir = dst_dir
        self.direction = direction
    
    def on_modified(self, event):
        global SYNCING
        if SYNCING or event.is_directory:
            return
        src_path = event.src_path
        
        if "__pycache__" in src_path or ".git" in src_path or "venv" in src_path or src_path.endswith(".pyc"):
            return
        
        if not os.path.exists(src_path):
            return
        
        rel_path = os.path.relpath(src_path, self.src_dir)
        dst_path = os.path.join(self.dst_dir, rel_path)
        
        src_mtime = get_mtime(src_path)
        dst_mtime = get_mtime(dst_path)
        
        if src_mtime <= dst_mtime:
            return
        
        try:
            SYNCING = True
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
            print(f"[{time.strftime('%H:%M:%S')}] {self.direction} {rel_path}")
        except:
            pass
        finally:
            SYNCING = False

if __name__ == "__main__":
    sdcard_handler = SyncHandler(SOURCE, DEST, "📱→🐧")
    sdcard_observer = Observer()
    sdcard_observer.schedule(sdcard_handler, SOURCE, recursive=True)
    
    ubuntu_handler = SyncHandler(DEST, SOURCE, "🐧→📱")
    ubuntu_observer = Observer()
    ubuntu_observer.schedule(ubuntu_handler, DEST, recursive=True)
    
    sdcard_observer.start()
    ubuntu_observer.start()
    
    print("🔄 Watchdog aktivan (samo novije verzije)")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sdcard_observer.stop()
        ubuntu_observer.stop()
    sdcard_observer.join()
    ubuntu_observer.join()
