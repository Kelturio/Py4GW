import os
import traceback
from datetime import datetime

import Py4GW  # type: ignore
from Py4GWCoreLib import ActionQueueNode
from Py4GWCoreLib import IniHandler
from Py4GWCoreLib import PyImGui
from Py4GWCoreLib import Player
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer

MODULE_NAME = "Chat Logger"
DEFAULT_LOG_FILE_NAME = "chat_log.txt"
MAX_RECENT_LINES = 10

__widget__ = {
    "name": MODULE_NAME,
    "enabled": False,
    "category": "Coding",
    "subcategory": "Info",
    "icon": "ICON_SAVE",
    "quickdock": True,
}

script_directory = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.normpath(os.path.join(script_directory, ".."))
config_directory = os.path.join(project_root, "Widgets", "Config")
log_directory = os.path.join(project_root, "Logs")

os.makedirs(config_directory, exist_ok=True)
os.makedirs(log_directory, exist_ok=True)

ini_path = os.path.join(config_directory, "ChatLogger.ini")
ini_handler = IniHandler(ini_path)


class ChatLoggerConfig:
    def __init__(self):
        self.window_x = ini_handler.read_int(MODULE_NAME, "x", 120)
        self.window_y = ini_handler.read_int(MODULE_NAME, "y", 120)
        self.window_collapsed = ini_handler.read_bool(MODULE_NAME, "collapsed", False)
        self.logging_enabled = ini_handler.read_bool(MODULE_NAME, "logging_enabled", False)
        self.log_file_name = ini_handler.read_key(MODULE_NAME, "log_file_name", DEFAULT_LOG_FILE_NAME)
        if not self.log_file_name:
            self.log_file_name = DEFAULT_LOG_FILE_NAME
        self.append_timestamp = ini_handler.read_bool(MODULE_NAME, "append_timestamp", True)
        interval = ini_handler.read_int(MODULE_NAME, "request_interval_ms", 1000)
        self.request_interval_ms = max(250, interval)

    def save_window_state(self):
        ini_handler.write_key(MODULE_NAME, "x", self.window_x)
        ini_handler.write_key(MODULE_NAME, "y", self.window_y)
        ini_handler.write_key(MODULE_NAME, "collapsed", self.window_collapsed)

    def save_logging_enabled(self):
        ini_handler.write_key(MODULE_NAME, "logging_enabled", self.logging_enabled)

    def save_log_file_name(self):
        ini_handler.write_key(MODULE_NAME, "log_file_name", self.log_file_name)

    def save_append_timestamp(self):
        ini_handler.write_key(MODULE_NAME, "append_timestamp", self.append_timestamp)

    def save_request_interval(self):
        ini_handler.write_key(MODULE_NAME, "request_interval_ms", self.request_interval_ms)


def _sanitize_filename(candidate: str) -> str:
    sanitized = candidate.strip()
    if not sanitized:
        return ""
    sanitized = sanitized.replace("\\", "/")
    sanitized = os.path.basename(sanitized)
    return sanitized


def _current_log_path() -> str:
    name = _sanitize_filename(chat_logger_config.log_file_name) or DEFAULT_LOG_FILE_NAME
    return os.path.join(log_directory, name)


def _ensure_log_directory() -> bool:
    try:
        os.makedirs(log_directory, exist_ok=True)
        return True
    except OSError as e:
        message = f"Failed to create log directory: {e}"
        Py4GW.Console.Log(MODULE_NAME, message, Py4GW.Console.MessageType.Error)
        _update_status(message)
    return False


def _update_status(message: str) -> None:
    global status_message
    status_message = message


def _set_logging_enabled(enabled: bool) -> None:
    global session_has_header, total_lines_written, last_write_timestamp
    if chat_logger_config.logging_enabled == enabled:
        return
    chat_logger_config.logging_enabled = enabled
    chat_logger_config.save_logging_enabled()
    session_has_header = False
    total_lines_written = 0
    last_write_timestamp = ""
    _update_status("Logging enabled" if enabled else "Logging paused")


def _apply_file_name(raw_name: str) -> None:
    global file_name_buffer, session_has_header, total_lines_written, last_write_timestamp
    sanitized = _sanitize_filename(raw_name)
    if not sanitized:
        sanitized = DEFAULT_LOG_FILE_NAME
    if chat_logger_config.log_file_name != sanitized:
        chat_logger_config.log_file_name = sanitized
        chat_logger_config.save_log_file_name()
        session_has_header = False
        total_lines_written = 0
        last_write_timestamp = ""
        _update_status(f"Using log file: {sanitized}")
    file_name_buffer = sanitized


def _write_lines_to_file(lines: list[str]) -> None:
    global session_has_header, total_lines_written, last_write_timestamp
    if not _ensure_log_directory():
        return

    log_path = _current_log_path()

    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            if not session_has_header:
                header = f"=== Session started {datetime.now().isoformat(timespec='seconds')} ===\n"
                log_file.write(header)
                session_has_header = True
            for line in lines:
                if not isinstance(line, str):
                    line = str(line)
                line = line.replace("\r", "").rstrip("\n")
                entry = line
                if chat_logger_config.append_timestamp:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    entry = f"[{timestamp}] {entry}"
                log_file.write(entry + "\n")
            total_lines_written += len(lines)
    except OSError as e:
        message = f"Failed to write chat log: {e}"
        Py4GW.Console.Log(MODULE_NAME, message, Py4GW.Console.MessageType.Error)
        _update_status(message)
        return

    last_write_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _update_status(f"Captured {len(lines)} lines")


chat_logger_config = ChatLoggerConfig()

file_name_buffer = chat_logger_config.log_file_name
status_message = "Logging enabled" if chat_logger_config.logging_enabled else "Logging paused"
last_write_timestamp = ""
total_lines_written = 0
recent_chat_lines: list[str] = []
last_chat_line_count = 0
session_has_header = False

request_timer = Timer()
request_timer.Start()

window_save_timer = Timer()
window_save_timer.Start()

chat_request_queue = ActionQueueNode(250)

first_run = True


def draw_widget():
    global first_run, file_name_buffer

    if first_run:
        PyImGui.set_next_window_pos(chat_logger_config.window_x, chat_logger_config.window_y)
        PyImGui.set_next_window_collapsed(chat_logger_config.window_collapsed, 0)
        first_run = False

    is_open = PyImGui.begin(MODULE_NAME, PyImGui.WindowFlags.AlwaysAutoResize)
    new_collapsed = PyImGui.is_window_collapsed()
    end_pos = PyImGui.get_window_pos()

    if is_open:
        PyImGui.text_wrapped("Capture chat messages and append them to a log file on disk.")
        PyImGui.separator()

        enabled_now = PyImGui.checkbox("Enable logging", chat_logger_config.logging_enabled)
        if enabled_now != chat_logger_config.logging_enabled:
            _set_logging_enabled(enabled_now)

        PyImGui.same_line()
        PyImGui.text(f"Status: {'active' if chat_logger_config.logging_enabled else 'paused'}")

        PyImGui.text_wrapped(f"Log file: {_current_log_path()}")

        file_name_buffer = PyImGui.input_text("File name", file_name_buffer)
        if PyImGui.button("Apply file name"):
            _apply_file_name(file_name_buffer)

        append_ts = PyImGui.checkbox("Add timestamps to entries", chat_logger_config.append_timestamp)
        if append_ts != chat_logger_config.append_timestamp:
            chat_logger_config.append_timestamp = append_ts
            chat_logger_config.save_append_timestamp()

        request_interval = PyImGui.slider_int("Update interval (ms)", chat_logger_config.request_interval_ms, 250, 5000)
        if request_interval != chat_logger_config.request_interval_ms:
            chat_logger_config.request_interval_ms = request_interval
            chat_logger_config.save_request_interval()
            _update_status(f"Request interval set to {request_interval} ms")

        PyImGui.separator()
        PyImGui.text(f"Lines captured this session: {total_lines_written}")
        PyImGui.text(f"Last write: {last_write_timestamp or 'n/a'}")
        PyImGui.text_wrapped(f"{status_message}")

        if recent_chat_lines:
            PyImGui.separator()
            PyImGui.text("Recent chat:")
            for line in recent_chat_lines[-MAX_RECENT_LINES:]:
                PyImGui.text_wrapped(line)

    PyImGui.end()

    if window_save_timer.HasElapsed(1000):
        new_x, new_y = int(end_pos[0]), int(end_pos[1])
        if (new_x, new_y) != (chat_logger_config.window_x, chat_logger_config.window_y):
            chat_logger_config.window_x = new_x
            chat_logger_config.window_y = new_y
            chat_logger_config.save_window_state()
        if new_collapsed != chat_logger_config.window_collapsed:
            chat_logger_config.window_collapsed = new_collapsed
            chat_logger_config.save_window_state()
        window_save_timer.Reset()


def _process_chat_history(chat_lines: list[str]) -> None:
    global last_chat_line_count, recent_chat_lines
    if not isinstance(chat_lines, (list, tuple)):
        return

    chat_lines = list(chat_lines)
    recent_chat_lines = chat_lines[-MAX_RECENT_LINES:]

    total_lines = len(chat_lines)
    if total_lines < last_chat_line_count:
        last_chat_line_count = total_lines
        return

    if total_lines == last_chat_line_count:
        return

    new_lines = chat_lines[last_chat_line_count:]
    last_chat_line_count = total_lines

    if chat_logger_config.logging_enabled and new_lines:
        _write_lines_to_file(new_lines)


def configure():
    draw_widget()


def main():
    global recent_chat_lines

    try:
        if not Routines.Checks.Map.MapValid():
            return

        if Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded():
            if request_timer.HasElapsed(chat_logger_config.request_interval_ms):
                if chat_request_queue.is_empty():
                    chat_request_queue.add_action(Player.RequestChatHistory)
                request_timer.Reset()

            chat_request_queue.ProcessQueue()

            if Player.IsChatHistoryReady():
                chat_lines = Player.GetChatHistory()
                _process_chat_history(chat_lines)

            draw_widget()

    except ImportError as e:
        Py4GW.Console.Log(MODULE_NAME, f"ImportError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except ValueError as e:
        Py4GW.Console.Log(MODULE_NAME, f"ValueError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except TypeError as e:
        Py4GW.Console.Log(MODULE_NAME, f"TypeError encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)
    except Exception as e:
        Py4GW.Console.Log(MODULE_NAME, f"Unexpected error encountered: {str(e)}", Py4GW.Console.MessageType.Error)
        Py4GW.Console.Log(MODULE_NAME, f"Stack trace: {traceback.format_exc()}", Py4GW.Console.MessageType.Error)


if __name__ == "__main__":
    main()
