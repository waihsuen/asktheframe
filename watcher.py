import subprocess
import time
import os
import sys

CHECK_INTERVAL = 60  # seconds
MAIN_SCRIPT = ['python', 'app/main.py']  # Use `sys.executable` if using venv

def run_main():
    """Start main.py as a subprocess."""
    return subprocess.Popen(MAIN_SCRIPT)

def get_current_commit(ref='HEAD'):
    """Get the current commit hash of a ref (e.g., HEAD or origin/main)."""
    result = subprocess.run(['git', 'rev-parse', ref], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip() if result.returncode == 0 else None

def fetch_remote():
    """Fetch latest commits from remote."""
    subprocess.run(['git', 'fetch'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def pull_changes():
    """Pull changes from remote."""
    subprocess.run(['git', 'pull'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def watcher_loop():
    process = run_main()
    local_commit = get_current_commit('HEAD')

    while True:
        time.sleep(CHECK_INTERVAL)
        fetch_remote()
        remote_commit = get_current_commit('origin/main')

        if remote_commit and remote_commit != local_commit:
            print("Change detected on remote. Pulling and restarting main.py...")
            pull_changes()
            process.terminate()
            process.wait()
            process = run_main()
            local_commit = get_current_commit('HEAD')
        else:
            print("No remote changes. Still running.")

try:
    watcher_loop()
except KeyboardInterrupt:
    print("Watcher stopped.")