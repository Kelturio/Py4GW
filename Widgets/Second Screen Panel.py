import os
import time
import traceback
from typing import Tuple

import Py4GW  # type: ignore
from Py4GWCoreLib import IniHandler, PyImGui, Routines, Timer, ImGuiStyleVar

MODULE_NAME = "Second Screen Panel"

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))

BASE_DIR = os.path.join(project_root, "Widgets", "Config")
INI_WIDGET_WINDOW_PATH = os.path.join(BASE_DIR, "Second_Screen_Panel.ini")
os.makedirs(BASE_DIR, exist_ok=True)

ini_window = IniHandler(INI_WIDGET_WINDOW_PATH)
save_window_timer = Timer()
save_window_timer.Start()

X_POS = "x"
Y_POS = "y"
COLLAPSED = "collapsed"
LOCK_KEY = "lock_window"
SNAP_OFFSET_KEY = "snap_offset"
SPEED_KEY = "progress_speed"

window_x = ini_window.read_int(MODULE_NAME, X_POS, 160)
window_y = ini_window.read_int(MODULE_NAME, Y_POS, 160)
window_collapsed = ini_window.read_bool(MODULE_NAME, COLLAPSED, False)
lock_window = ini_window.read_bool(MODULE_NAME, LOCK_KEY, False)
second_screen_offset = max(0, ini_window.read_int(MODULE_NAME, SNAP_OFFSET_KEY, 40))
progress_speed = max(0.05, ini_window.read_float(MODULE_NAME, SPEED_KEY, 0.25))

style_var_enum = PyImGui.ImGuiStyleVar if hasattr(PyImGui, "ImGuiStyleVar") else ImGuiStyleVar

first_run = True

progress_value = 0.0
progress_direction = 1.0
last_progress_update = time.perf_counter()

session_timer = Timer()
session_timer.Start()

def _update_progress() -> None:
    global progress_value, progress_direction, last_progress_update

    now = time.perf_counter()
    delta = now - last_progress_update
    if delta <= 0:
        return
    last_progress_update = now

    step = delta * progress_speed
    progress_value += progress_direction * step

    if progress_value >= 1.0:
        progress_value = 1.0
        progress_direction = -1.0
    elif progress_value <= 0.0:
        progress_value = 0.0
        progress_direction = 1.0

def _draw_controls(window_pos: Tuple[float, float]) -> None:
    global lock_window, second_screen_offset, progress_speed

    io = PyImGui.get_io()

    PyImGui.text_wrapped(
        "Drag this floating panel onto a secondary monitor to keep essential data visible while you play."
    )
    PyImGui.spacing()

    PyImGui.text(f"Session timer: {session_timer.FormatElapsedTime('hh:mm:ss')}")
    PyImGui.text(f"ImGui FPS: {io.framerate:.1f}")
    PyImGui.text(f"Primary viewport: {int(io.display_size_x)} x {int(io.display_size_y)}")

    PyImGui.separator()
    PyImGui.text("Window behaviour")

    new_lock_window = PyImGui.checkbox("Lock window position", lock_window)
    if new_lock_window != lock_window:
        lock_window = new_lock_window
        ini_window.write_key(MODULE_NAME, LOCK_KEY, str(lock_window))

    PyImGui.same_line(0.0, 12.0)
    if PyImGui.button("Reset timer"):
        session_timer.Reset()

    offset_label = "Second screen offset" if io.display_size_x > 0 else "Offset"
    new_offset = PyImGui.input_int(offset_label, second_screen_offset, 5, 25, 0)
    if new_offset != second_screen_offset:
        second_screen_offset = max(0, new_offset)
        ini_window.write_key(MODULE_NAME, SNAP_OFFSET_KEY, str(second_screen_offset))

    if PyImGui.button("Snap to secondary monitor"):
        new_x = int(io.display_size_x) + max(0, second_screen_offset)
        PyImGui.set_window_pos(float(new_x), float(window_pos[1]))
        ini_window.write_key(MODULE_NAME, X_POS, str(new_x))

    PyImGui.separator()
    PyImGui.text("Status overview")

    new_speed = PyImGui.slider_float("Progress animation speed", progress_speed, 0.05, 1.5)
    if abs(new_speed - progress_speed) > 1e-4:
        progress_speed = max(0.05, new_speed)
        ini_window.write_key(MODULE_NAME, SPEED_KEY, f"{progress_speed:.4f}")

    _update_progress()
    PyImGui.progress_bar(progress_value, 0.0, f"{progress_value * 100:5.1f}%")

    PyImGui.spacing()
    PyImGui.text_wrapped(
        "Use this panel as a template for custom multi-monitor layouts. Add your own gauges, timers or party information in place"
        " of the demo controls."
    )


def draw_widget():
    global first_run, window_x, window_y, window_collapsed

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    window_flags = getattr(PyImGui.WindowFlags, "NoDocking", PyImGui.WindowFlags.NoFlag)
    if lock_window:
        window_flags |= PyImGui.WindowFlags.NoMove

    PyImGui.push_style_var(style_var_enum.WindowRounding, 6.0)
    PyImGui.push_style_var(style_var_enum.WindowBorderSize, 1.0)

    is_open = PyImGui.begin(MODULE_NAME, window_flags)
    new_collapsed = PyImGui.is_window_collapsed()
    current_pos = PyImGui.get_window_pos()

    if is_open:
        _draw_controls(current_pos)

    PyImGui.end()
    PyImGui.pop_style_var(2)

    if save_window_timer.HasElapsed(400):
        save_window_timer.Reset()
        updated_x, updated_y = int(current_pos[0]), int(current_pos[1])
        if (updated_x, updated_y) != (window_x, window_y):
            window_x, window_y = updated_x, updated_y
            ini_window.write_key(MODULE_NAME, X_POS, str(window_x))
            ini_window.write_key(MODULE_NAME, Y_POS, str(window_y))
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_window.write_key(MODULE_NAME, COLLAPSED, str(window_collapsed))

def configure():
    global lock_window, second_screen_offset, progress_speed

    PyImGui.set_next_window_size(360, 0)
    if PyImGui.begin(f"{MODULE_NAME} Settings", PyImGui.WindowFlags.AlwaysAutoResize):
        PyImGui.text("Adjust the defaults for the floating panel.")
        PyImGui.separator()

        new_lock = PyImGui.checkbox("Start locked", lock_window)
        if new_lock != lock_window:
            lock_window = new_lock
            ini_window.write_key(MODULE_NAME, LOCK_KEY, str(lock_window))

        new_offset = PyImGui.input_int("Default snap offset", second_screen_offset, 5, 25, 0)
        if new_offset != second_screen_offset:
            second_screen_offset = max(0, new_offset)
            ini_window.write_key(MODULE_NAME, SNAP_OFFSET_KEY, str(second_screen_offset))

        new_speed = PyImGui.slider_float("Default progress speed", progress_speed, 0.05, 1.5)
        if abs(new_speed - progress_speed) > 1e-4:
            progress_speed = max(0.05, new_speed)
            ini_window.write_key(MODULE_NAME, SPEED_KEY, f"{progress_speed:.4f}")

    PyImGui.end()


def main():
    try:
        if not Routines.Checks.Map.MapValid():
            return

        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            draw_widget()

    except ImportError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ImportError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except ValueError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"ValueError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except TypeError as exc:
        Py4GW.Console.Log(MODULE_NAME, f"TypeError encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)
    except Exception as exc:  # noqa: BLE001
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error encountered: {exc}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, traceback.format_exc(), Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
