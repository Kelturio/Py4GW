import os
from datetime import datetime

import Py4GW  # type: ignore
from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import IniHandler
from Py4GWCoreLib import PyImGui
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer
from Py4GWCoreLib import ActionQueue


MODULE_NAME = "Chat Log Saver"


script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_directory, os.pardir))


CONFIG_BASE = os.path.join(project_root, "Widgets/Config")
os.makedirs(CONFIG_BASE, exist_ok=True)
CONFIG_PATH = os.path.join(CONFIG_BASE, "ChatLogSaver.ini")


ini_handler = IniHandler(CONFIG_PATH)
save_window_timer = Timer()
save_window_timer.Start()


first_run = True


window_x = ini_handler.read_int(MODULE_NAME, "x", 100)
window_y = ini_handler.read_int(MODULE_NAME, "y", 100)
window_collapsed = ini_handler.read_bool(MODULE_NAME, "collapsed", False)


default_log_dir = os.path.join(project_root, "Logs")
log_directory = ini_handler.read_key(MODULE_NAME, "log_directory", default_log_dir)
file_prefix = ini_handler.read_key(MODULE_NAME, "file_prefix", "chat_log")
timestamp_lines = ini_handler.read_bool(MODULE_NAME, "timestamp_lines", True)
new_file_each_session = ini_handler.read_bool(MODULE_NAME, "new_file_each_session", True)
persist_enabled = ini_handler.read_bool(MODULE_NAME, "enabled", False)


logging_enabled = False
active_log_path = ""
pending_chat_request = False
skip_next_snapshot = False
last_processed_line: str | None = None
total_lines_written = 0
session_started_at: datetime | None = None
last_write_time: datetime | None = None
last_error_message = ""


chat_queue = ActionQueue()
chat_request_timer = Timer()
chat_request_timer.Start()
CHAT_REQUEST_INTERVAL_MS = 500


def get_log_directory_path() -> str:
    """Return the absolute path for the configured log directory."""

    configured = os.path.expanduser(log_directory.strip())
    if not configured:
        configured = default_log_dir

    if not os.path.isabs(configured):
        configured = os.path.abspath(os.path.join(project_root, configured))

    return configured


def ensure_log_directory() -> None:
    """Create the log directory if it doesn't already exist."""

    try:
        os.makedirs(get_log_directory_path(), exist_ok=True)
    except OSError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Unable to create log directory '{log_directory}': {exc}",
            Py4GW.Console.MessageType.Error,
        )
        raise


def build_log_file_path() -> str:
    """Return the full path of the log file for the current session."""

    file_name = file_prefix.strip() or "chat_log"

    if new_file_each_session:
        time_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"{file_name}_{time_stamp}.txt"
    elif not file_name.lower().endswith(".txt"):
        file_name = f"{file_name}.txt"

    return os.path.join(get_log_directory_path(), file_name)


def write_lines_to_file(lines: list[str]) -> None:
    """Append the provided chat lines to the active log file."""

    global total_lines_written, last_write_time, last_error_message, logging_enabled

    if not active_log_path:
        return

    try:
        ensure_log_directory()
        with open(active_log_path, "a", encoding="utf-8") as log_file:
            for line in lines:
                if timestamp_lines:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_file.write(f"[{timestamp}] {line}\n")
                else:
                    log_file.write(f"{line}\n")
        total_lines_written += len(lines)
        last_write_time = datetime.now()
        last_error_message = ""
    except OSError as exc:
        logging_enabled = False
        last_error_message = str(exc)
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Failed to write chat log '{active_log_path}': {exc}",
            Py4GW.Console.MessageType.Error,
        )


def request_chat_history_action() -> None:
    """Request a chat history update via the action queue."""

    global pending_chat_request

    try:
        GLOBAL_CACHE.Player.RequestChatHistory()
        pending_chat_request = True
    except Exception as exc:  # noqa: BLE001 - log unexpected errors
        pending_chat_request = False
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Failed to request chat history: {exc}",
            Py4GW.Console.MessageType.Error,
        )


def extract_new_lines(chat_lines: list[str]) -> list[str]:
    """Return the chat lines that were not previously processed."""

    global last_processed_line

    if not chat_lines:
        return []

    start_index = 0
    if last_processed_line is not None:
        for idx in range(len(chat_lines) - 1, -1, -1):
            if chat_lines[idx] == last_processed_line:
                start_index = idx + 1
                break

    new_lines = chat_lines[start_index:]
    last_processed_line = chat_lines[-1]
    return new_lines


def start_logging() -> None:
    """Initialize logging state and prepare a log file for the session."""

    global logging_enabled, active_log_path, total_lines_written, session_started_at
    global last_write_time, pending_chat_request, skip_next_snapshot, last_processed_line
    global persist_enabled

    try:
        ensure_log_directory()
    except OSError:
        return

    active_path = build_log_file_path()
    base_dir = os.path.dirname(active_path)
    try:
        os.makedirs(base_dir, exist_ok=True)
    except OSError as exc:
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Unable to prepare chat log path '{active_path}': {exc}",
            Py4GW.Console.MessageType.Error,
        )
        return

    logging_enabled = True
    persist_enabled = True
    active_log_path = active_path
    total_lines_written = 0
    session_started_at = datetime.now()
    last_write_time = None
    pending_chat_request = False
    skip_next_snapshot = True
    last_processed_line = None
    chat_queue.clear()
    chat_request_timer.Reset()
    ini_handler.write_key(MODULE_NAME, "enabled", "True")


def stop_logging() -> None:
    """Stop capturing chat history and reset runtime state."""

    global logging_enabled, pending_chat_request, skip_next_snapshot, persist_enabled

    logging_enabled = False
    persist_enabled = False
    pending_chat_request = False
    skip_next_snapshot = False
    chat_queue.clear()
    ini_handler.write_key(MODULE_NAME, "enabled", "False")


def update_settings() -> None:
    """Persist configuration values to the INI file."""

    ini_handler.write_key(MODULE_NAME, "log_directory", log_directory)
    ini_handler.write_key(MODULE_NAME, "file_prefix", file_prefix)
    ini_handler.write_key(MODULE_NAME, "timestamp_lines", str(timestamp_lines))
    ini_handler.write_key(MODULE_NAME, "new_file_each_session", str(new_file_each_session))


def process_chat_updates() -> None:
    """Poll the chat system and write any new lines to disk."""

    global pending_chat_request, skip_next_snapshot

    if not logging_enabled:
        return

    if not pending_chat_request and chat_request_timer.HasElapsed(CHAT_REQUEST_INTERVAL_MS):
        chat_queue.add_action(request_chat_history_action)
        chat_request_timer.Reset()

    chat_queue.execute_next()

    if GLOBAL_CACHE.Player.IsChatHistoryReady():
        chat_lines = GLOBAL_CACHE.Player.GetChatHistory() or []
        pending_chat_request = False

        if skip_next_snapshot:
            skip_next_snapshot = False
            if chat_lines:
                # Establish baseline without writing out existing history.
                global last_processed_line
                last_processed_line = chat_lines[-1]
            return

        new_lines = extract_new_lines(chat_lines)
        if new_lines:
            write_lines_to_file(new_lines)


def draw_widget() -> None:
    """Render the Chat Log Saver control window."""

    global first_run, window_x, window_y, window_collapsed
    global log_directory, file_prefix, timestamp_lines, new_file_each_session

    if first_run:
        PyImGui.set_next_window_pos(window_x, window_y)
        PyImGui.set_next_window_collapsed(window_collapsed, 0)
        first_run = False

    is_window_open = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_window_open:
        PyImGui.text(f"Status: {'Recording' if logging_enabled else 'Stopped'}")
        if logging_enabled:
            if session_started_at is not None:
                PyImGui.text(f"Started: {session_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
            PyImGui.text(f"File: {active_log_path if active_log_path else 'Not set'}")
            PyImGui.text(f"Lines written: {total_lines_written}")
            if last_write_time is not None:
                PyImGui.text(f"Last write: {last_write_time.strftime('%H:%M:%S')}")
            if PyImGui.button("Stop Logging"):
                stop_logging()
        else:
            if PyImGui.button("Start Logging"):
                start_logging()

        if last_error_message:
            PyImGui.separator()
            PyImGui.text_colored("Last error:", (1.0, 0.4, 0.4, 1.0))
            PyImGui.text_wrapped(last_error_message)

        PyImGui.separator()
        log_directory = PyImGui.input_text("Log Directory", log_directory, 260)
        file_prefix = PyImGui.input_text("File Prefix", file_prefix, 128)
        timestamp_lines = PyImGui.checkbox("Timestamp each line", timestamp_lines)
        new_file_each_session = PyImGui.checkbox("Create new file per session", new_file_each_session)

        if PyImGui.button("Save Settings"):
            update_settings()

    PyImGui.end()

    if save_window_timer.HasElapsed(1000):
        if (int(end_pos[0]), int(end_pos[1])) != (window_x, window_y):
            window_x, window_y = int(end_pos[0]), int(end_pos[1])
            ini_handler.write_key(MODULE_NAME, "x", str(window_x))
            ini_handler.write_key(MODULE_NAME, "y", str(window_y))
        if new_collapsed != window_collapsed:
            window_collapsed = new_collapsed
            ini_handler.write_key(MODULE_NAME, "collapsed", str(window_collapsed))
        save_window_timer.Reset()


def configure():
    draw_widget()


def main():
    try:
        if not Routines.Checks.Map.MapValid():
            return

        if persist_enabled and not logging_enabled:
            start_logging()

        process_chat_updates()

        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            draw_widget()

    except Exception as exc:  # noqa: BLE001 - ensure stability
        Py4GW.Console.Log(
            MODULE_NAME,
            f"Unexpected error: {exc}",
            Py4GW.Console.MessageType.Error,
        )


if __name__ == "__main__":
    main()

