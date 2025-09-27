"""Utilities for running a standalone Dear ImGui desktop window.

This module provides a thin helper around the ``pyimgui`` + ``glfw`` stack so
Py4GW tools can display information on another monitor without having to reuse
Guild Wars' in-game overlay surface.  The implementation focuses on being
light-weight, thread friendly and easy to embed from existing scripts.

Example
-------
>>> from Py4GWCoreLib.ExternalImGuiWindow import ExternalImGuiWindow
>>> def draw(imgui, state):
...     imgui.set_next_window_pos(20, 20, imgui.ONCE)
...     if imgui.begin("External Monitor"):
...         imgui.text("This window lives outside the Guild Wars overlay!")
...         imgui.text(f"Latest agent count: {state.get('agents', 'unknown')}")
...     imgui.end()
...
>>> with ExternalImGuiWindow(draw_callback=draw) as window:
...     window.update_state(agents=5)
...     window.join()  # Blocks until the user closes the desktop window.

The demo window can run in its own background thread so scripts can keep
interacting with the Guild Wars client while the external UI is visible.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple


class _ImGuiBackend:  # pragma: no cover - thin import wrapper
    """Import helpers grouped together to centralise ImportError handling."""

    def __init__(self) -> None:
        try:
            import glfw  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised at runtime
            raise ImportError(
                "glfw is required to run the standalone ImGui window. "
                "Install it with `pip install imgui[glfw] glfw`."
            ) from exc

        try:
            import imgui  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised at runtime
            raise ImportError(
                "pyimgui is required to run the standalone ImGui window. "
                "Install it with `pip install imgui[glfw]`."
            ) from exc

        try:
            from OpenGL import GL  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised at runtime
            raise ImportError(
                "PyOpenGL is required to run the standalone ImGui window. "
                "Install it with `pip install PyOpenGL`."
            ) from exc

        from imgui.integrations.glfw import GlfwRenderer  # type: ignore

        self.glfw = glfw
        self.imgui = imgui
        self.GL = GL
        self.GlfwRenderer = GlfwRenderer


@dataclass
class ExternalImGuiWindow:
    """Manage a Dear ImGui desktop window in a background thread."""

    title: str = "Py4GW External UI"
    size: Tuple[int, int] = (420, 320)
    clear_color: Tuple[float, float, float, float] = (0.08, 0.08, 0.10, 1.0)
    frame_rate_limit: Optional[int] = 60
    draw_callback: Optional[Callable[[Any, Dict[str, Any]], None]] = None
    auto_start: bool = True
    _state: Dict[str, Any] = field(default_factory=dict, init=False)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _backend: _ImGuiBackend = field(default_factory=_ImGuiBackend, init=False, repr=False)
    _ready_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _exception: Optional[BaseException] = field(default=None, init=False, repr=False)
    _renderer: Optional[Any] = field(default=None, init=False, repr=False)
    _window: Optional[Any] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.auto_start:
            self.start()

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def start(self) -> None:
        """Launch the ImGui window loop in a background daemon thread."""

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._ready_event.clear()
        self._exception = None
        self._thread = threading.Thread(target=self._run, name="ExternalImGuiWindow", daemon=True)
        self._thread.start()
        # Wait until the backend finished initialising (or crashed).
        self._ready_event.wait()
        if self._exception:
            raise self._exception

    def stop(self) -> None:
        """Signal the window loop to terminate."""

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join()

    def join(self) -> None:
        """Block until the window thread terminates."""

        if self._thread and self._thread.is_alive():
            self._thread.join()

    def is_running(self) -> bool:
        """Return ``True`` while the window thread is active."""

        thread_alive = self._thread is not None and self._thread.is_alive()
        return thread_alive and not self._stop_event.is_set()

    # ------------------------------------------------------------------
    # Context-manager support
    def __enter__(self) -> "ExternalImGuiWindow":
        if not self._thread or not self._thread.is_alive():
            self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        self.stop()

    # ------------------------------------------------------------------
    # State synchronisation
    def update_state(self, **values: Any) -> None:
        """Update key/value pairs visible to the draw callback."""

        with self._state_lock:
            self._state.update(values)

    def replace_state(self, new_state: Dict[str, Any]) -> None:
        """Replace the shared state with a new mapping."""

        with self._state_lock:
            self._state.clear()
            self._state.update(new_state)

    def snapshot_state(self) -> Dict[str, Any]:
        """Return a shallow copy of the state mapping."""

        with self._state_lock:
            return dict(self._state)

    # ------------------------------------------------------------------
    # Internal helpers
    def _run(self) -> None:
        try:
            self._main_loop()
        except BaseException as exc:  # pragma: no cover - logged to caller
            self._exception = exc
        finally:
            self._ready_event.set()

    def _main_loop(self) -> None:
        backend = self._backend
        glfw = backend.glfw
        imgui = backend.imgui
        GL = backend.GL

        if not glfw.init():
            raise RuntimeError("glfw.init() failed; cannot create external ImGui window.")

        try:
            glfw.window_hint(glfw.VISIBLE, glfw.TRUE)
            window = glfw.create_window(self.size[0], self.size[1], self.title, None, None)
            if not window:
                raise RuntimeError("Failed to create GLFW window for external ImGui UI.")

            glfw.make_context_current(window)
            glfw.swap_interval(1 if self.frame_rate_limit else 0)

            imgui.create_context()
            renderer = backend.GlfwRenderer(window)
            renderer.refresh_font_texture()

            self._renderer = renderer
            self._window = window

            # Signal to the creator that the window is ready.
            self._ready_event.set()

            previous_frame_time = time.perf_counter()

            while not glfw.window_should_close(window) and not self._stop_event.is_set():
                glfw.poll_events()
                renderer.process_inputs()

                imgui.new_frame()
                state_snapshot = self.snapshot_state()
                if self.draw_callback:
                    self.draw_callback(imgui, state_snapshot)
                else:
                    self._default_draw(imgui, state_snapshot)

                imgui.render()

                framebuffer_width, framebuffer_height = glfw.get_framebuffer_size(window)
                GL.glViewport(0, 0, framebuffer_width, framebuffer_height)
                GL.glClearColor(*self.clear_color)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT)
                renderer.render(imgui.get_draw_data())
                glfw.swap_buffers(window)

                if self.frame_rate_limit:
                    frame_duration = time.perf_counter() - previous_frame_time
                    min_frame_time = 1.0 / float(self.frame_rate_limit)
                    if frame_duration < min_frame_time:
                        time.sleep(min_frame_time - frame_duration)
                    previous_frame_time = time.perf_counter()
        finally:
            self._stop_event.set()
            self._shutdown_backend()

    def _default_draw(self, imgui: Any, state: Dict[str, Any]) -> None:
        imgui.set_next_window_size(self.size[0] - 40, self.size[1] - 40, imgui.ONCE)
        imgui.set_next_window_pos(20, 20, imgui.ONCE)
        if imgui.begin("Py4GW External UI"):
            imgui.text("External ImGui window is running.")
            if state:
                imgui.separator()
                imgui.text("Shared state snapshot:")
                for key, value in state.items():
                    imgui.bullet_text(f"{key}: {value}")
        imgui.end()

    def _shutdown_backend(self) -> None:
        backend = self._backend
        glfw = backend.glfw
        imgui = backend.imgui

        try:
            if self._renderer is not None:
                try:
                    self._renderer.shutdown()
                finally:
                    self._renderer = None
        except Exception:  # pragma: no cover - best effort cleanup
            pass

        try:
            if self._window is not None:
                glfw.destroy_window(self._window)
                self._window = None
        except Exception:  # pragma: no cover - best effort cleanup
            pass

        try:
            imgui.destroy_context()
        except Exception:  # pragma: no cover - best effort cleanup
            pass

        try:
            glfw.terminate()
        except Exception:  # pragma: no cover - best effort cleanup
            pass


__all__ = ["ExternalImGuiWindow"]
