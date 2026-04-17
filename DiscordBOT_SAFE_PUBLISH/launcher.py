import socket
import threading
import time
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen

from app import run_web_app


HOST = "127.0.0.1"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def wait_for_server(url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2):
                return
        except URLError:
            time.sleep(0.2)
    raise RuntimeError("The local Warlords server did not start in time.")


def start_server(port: int) -> None:
    thread = threading.Thread(
        target=run_web_app,
        kwargs={"host": HOST, "port": port, "debug": False},
        daemon=True,
    )
    thread.start()


def main() -> None:
    port = find_free_port()
    url = f"http://{HOST}:{port}"
    start_server(port)
    wait_for_server(url)
    webbrowser.open(url)

    # Keep the process alive while the local server runs.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
