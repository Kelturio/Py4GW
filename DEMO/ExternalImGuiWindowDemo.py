from __future__ import annotations
"""Demonstrate streaming Py4GW data into a standalone ImGui window."""

import random
import threading
import time
from typing import Dict

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


if __name__ == "__main__":
    window = ExternalImGuiWindow(draw_callback=draw_callback)
    worker = threading.Thread(target=telemetry_worker, args=(window,), daemon=True)
    worker.start()

    try:
        window.join()
    except KeyboardInterrupt:
        pass
    finally:
        window.stop()
