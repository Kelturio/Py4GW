from __future__ import annotations
"""Demonstrate streaming Py4GW data into a standalone ImGui window."""

import random
import threading
import time
from typing import Dict, Optional

from Py4GWCoreLib.ExternalImGuiWindow import ExternalImGuiWindow


def draw_callback(imgui, state: Dict[str, float]) -> None:
    """Render the contents of the external ImGui window."""

    imgui.set_next_window_pos(20, 20, imgui.ONCE)
    imgui.set_next_window_size(360, 220, imgui.ONCE)
    if imgui.begin("Py4GW External Monitor"):
        imgui.text("Standalone ImGui window example")
        imgui.separator()
        imgui.text("Drag this window to another screen to keep an eye on data")
        imgui.new_line()

        imgui.text("Telemetry")
        imgui.bullet_text(f"Update #: {int(state.get('tick', 0))}")
        imgui.bullet_text(f"Average ping: {state.get('ping', 0.0):.0f} ms")
        imgui.bullet_text(f"Party health: {state.get('party_health', 0.0):.1f}%")

        imgui.new_line()
        if imgui.button("Reset counters"):
            # Push an event back to the worker thread via the shared state.
            state.get("reset_callback", lambda: None)()
    imgui.end()


def telemetry_worker(window: ExternalImGuiWindow) -> None:
    """Simulate updates from a background Py4GW workflow."""

    tick = 0

    def reset() -> None:
        nonlocal tick
        tick = 0

    while window.is_running():
        tick += 1
        window.update_state(
            tick=tick,
            ping=50 + random.random() * 25,
            party_health=max(0.0, 100.0 - tick * 0.2),
            reset_callback=reset,
        )
        time.sleep(0.5)


_WINDOW: Optional[ExternalImGuiWindow] = None
_WORKER: Optional[threading.Thread] = None
_LOCK = threading.Lock()


def _start_demo_if_needed() -> ExternalImGuiWindow:
    """Ensure the external window and telemetry worker are running."""

    global _WINDOW, _WORKER

    with _LOCK:
        if _WINDOW is None:
            window = ExternalImGuiWindow(draw_callback=draw_callback)
            worker = threading.Thread(target=telemetry_worker, args=(window,), daemon=True)
            worker.start()
            _WINDOW = window
            _WORKER = worker

        window = _WINDOW

    if window is None:  # pragma: no cover - defensive
        raise RuntimeError("Failed to create the external ImGui demo window.")

    return window


def _stop_demo() -> None:
    """Terminate the external window and worker thread if they are running."""

    global _WINDOW, _WORKER

    with _LOCK:
        if _WINDOW is not None:
            _WINDOW.stop()
            _WINDOW = None

        if _WORKER is not None:
            _WORKER.join(timeout=0.5)
            _WORKER = None


def main() -> None:
    """Entry point expected by the Py4GW runtime."""

    window = _start_demo_if_needed()
    if not window.is_running():
        _stop_demo()


def run_demo_blocking() -> None:
    """Start the demo and block until the window is closed."""

    try:
        window = _start_demo_if_needed()
        window.join()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_demo()


if __name__ == "__main__":
    run_demo_blocking()
