import os
import subprocess
import sys
import time
from pathlib import Path


def setup_console():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


def free_port(port: int = 2666):
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = int(parts[-1])
                    if pid != os.getpid():
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
        except Exception:
            pass


def load_logo() -> str:
    logo_path = Path(__file__).resolve().parent / "assets" / "logo.txt"
    if logo_path.is_file():
        with open(logo_path, "r", encoding="utf-8") as file_handle:
            return file_handle.read()
    return ""


def start():
    setup_console()
    free_port(2666)

    logo = load_logo()
    if logo:
        print(logo)
    print("""
Author: Eleferia Labs
License: MIT
API running on http://localhost:2666 
Have fun! :)
    """)

    api_path = Path(__file__).resolve().parent / "api.py"
    process = subprocess.Popen(
        [sys.executable, str(api_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        while process.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    start()