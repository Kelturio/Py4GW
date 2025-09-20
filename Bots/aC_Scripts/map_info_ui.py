"""UI helpers for displaying map information in the PyQuishAI window."""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Sequence

from Py4GWCoreLib import IconsFontAwesome5, PyImGui


StatsFn = Callable[[], Dict[str, Any]]
SegmentOffsetFn = Callable[[Sequence[Any], int], int]


def _render_label_value(label: str, value: Any, header_color: Sequence[float]) -> None:
    """Render a labelled value pair on a single line."""
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    PyImGui.text(label)
    PyImGui.pop_style_color(1)
    PyImGui.same_line(0, 6)
    PyImGui.text(str(value))


def _render_selected_map_header(stats: Dict[str, Any], header_color: Sequence[float], icon_color: Sequence[float]) -> None:
    """Render the title row showing the currently selected map."""
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, icon_color)
    PyImGui.text(IconsFontAwesome5.ICON_MAP_MARKER_ALT)
    PyImGui.pop_style_color(1)
    PyImGui.same_line(0, 3)

    label = stats.get("map_name") or "No map selected"
    if stats.get("region"):
        label = f"{label} [{stats['region']}]"

    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    PyImGui.text(label)
    PyImGui.pop_style_color(1)


def _render_segment_waypoints(
    segment_index: int,
    waypoints: Iterable[Any],
    header_color: Sequence[float],
    fsm_vars: Any,
    global_offset: int,
) -> None:
    """Render the detailed waypoint listing for a single segment."""
    if waypoints:
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("  Waypoints:")
        PyImGui.pop_style_color(1)
        for wp_index, point in enumerate(waypoints, start=1):
            try:
                x, y = int(point[0]), int(point[1])
                PyImGui.text(f"  - WP {wp_index}: ({x},{y})")
            except Exception:
                PyImGui.text(f"  - WP {wp_index}: {point}")

            PyImGui.same_line(0, 6)
            global_idx = global_offset + (wp_index - 1)
            if PyImGui.button(f">##go_{segment_index}_{wp_index}", width=20):
                if fsm_vars.path_and_aggro:
                    fsm_vars.path_and_aggro.force_move_to_index(global_idx, sticky=True)
            PyImGui.same_line(0, 2)
            if PyImGui.button(f"I##set_{segment_index}_{wp_index}", width=18):
                if fsm_vars.path_and_aggro:
                    fsm_vars.path_and_aggro.set_active_index(global_idx)
    else:
        PyImGui.text("  - (no waypoints)")


def _render_segment_bless_points(bless_points: Iterable[Any], header_color: Sequence[float]) -> None:
    if not bless_points:
        return

    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    PyImGui.text("  Bless Points:")
    PyImGui.pop_style_color(1)
    for point in bless_points:
        try:
            bx, by = int(point[0]), int(point[1])
            PyImGui.text(f"  - ({bx},{by})")
        except Exception:
            PyImGui.text(f"  - {point}")


def _normalize_bless_points(raw_bless: Any) -> List[Any]:
    """Normalise the bless list so the UI can iterate consistently."""
    if raw_bless is None:
        return []
    if isinstance(raw_bless, (list, tuple)) and raw_bless and isinstance(raw_bless[0], (list, tuple)):
        return list(raw_bless)
    return [raw_bless]


def _render_structured_segments(
    map_path: Sequence[Any],
    bot_vars: Any,
    fsm_vars: Any,
    header_color: Sequence[float],
    segment_offset_fn: SegmentOffsetFn,
) -> None:
    for segment_index, segment in enumerate(map_path):
        waypoints = segment.get("path", []) or []
        bless_points = _normalize_bless_points(segment.get("bless"))

        PyImGui.text(
            f"Segment {segment_index + 1}: {len(waypoints)} WPs"
            + (f", Bless: {len(bless_points)}" if bless_points else "")
        )

        PyImGui.same_line(0, 12)
        is_open = bool(bot_vars.segment_open.get(segment_index, False))
        button_label = "Close" if is_open else "Open"
        if PyImGui.button(f"{button_label}##seg{segment_index}", width=60):
            bot_vars.segment_open[segment_index] = not is_open
            is_open = not is_open

        if is_open:
            base_index = segment_offset_fn(map_path, segment_index)
            _render_segment_waypoints(segment_index, waypoints, header_color, fsm_vars, base_index)
            _render_segment_bless_points(bless_points, header_color)


def _render_flat_segment(
    waypoints: Sequence[Any],
    bot_vars: Any,
    fsm_vars: Any,
    header_color: Sequence[float],
) -> None:
    PyImGui.text(f"Segment 1: {len(waypoints)} WPs")
    PyImGui.same_line(0, 12)
    is_open = bool(bot_vars.segment_open.get(0, False))
    button_label = "Close" if is_open else "Open"
    if PyImGui.button("%s##seg0" % button_label, width=60):
        bot_vars.segment_open[0] = not is_open
        is_open = not is_open

    if not is_open:
        return

    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    PyImGui.text("  Waypoints:")
    PyImGui.pop_style_color(1)

    for wp_index, point in enumerate(waypoints, start=1):
        try:
            x, y = int(point[0]), int(point[1])
            PyImGui.text(f"  - WP {wp_index}: ({x},{y})")
        except Exception:
            PyImGui.text(f"  - WP {wp_index}: {point}")

        PyImGui.same_line(0, 6)
        global_idx = wp_index - 1
        if PyImGui.button(f">##go_flat_{wp_index}", width=20):
            if fsm_vars.path_and_aggro:
                fsm_vars.path_and_aggro.force_move_to_index(global_idx, sticky=True)
        PyImGui.same_line(0, 2)
        if PyImGui.button(f"I##set_flat_{wp_index}", width=18):
            if fsm_vars.path_and_aggro:
                fsm_vars.path_and_aggro.set_active_index(global_idx)


def _render_segment_details(
    bot_vars: Any,
    fsm_vars: Any,
    header_color: Sequence[float],
    segment_offset_fn: SegmentOffsetFn,
) -> None:
    map_path = bot_vars.map_data.get("map_path", [])
    if not (isinstance(map_path, list) and map_path):
        return

    PyImGui.separator()
    PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
    PyImGui.text("Segment Details:")
    PyImGui.pop_style_color(1)

    if all(isinstance(entry, dict) for entry in map_path):
        _render_structured_segments(map_path, bot_vars, fsm_vars, header_color, segment_offset_fn)
    else:
        _render_flat_segment(map_path, bot_vars, fsm_vars, header_color)


def _render_blessing_summary(stats: Dict[str, Any], header_color: Sequence[float]) -> None:
    PyImGui.separator()
    _render_label_value("Bless Points (all):", str(stats.get("bless_count", 0)), header_color)
    for point in stats.get("bless_preview", []):
        try:
            bx, by = int(point[0]), int(point[1])
            PyImGui.text(f"- ({bx},{by})")
        except Exception:
            PyImGui.text(f"- {point}")


def _render_optional_paths(bot_vars: Any, fsm_vars: Any, header_color: Sequence[float]) -> None:
    PyImGui.separator()
    outpost_button = "Hide Outpost Path" if bot_vars.show_outpost_list else "Show Outpost Path"
    if PyImGui.button(outpost_button, width=140):
        bot_vars.show_outpost_list = not bot_vars.show_outpost_list

    PyImGui.same_line(0, 8)
    merged_button = "Hide Merged WPs" if bot_vars.show_merged_list else "Show Merged WPs"
    if PyImGui.button(merged_button, width=140):
        bot_vars.show_merged_list = not bot_vars.show_merged_list

    if bot_vars.show_outpost_list:
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Outpost Path:")
        PyImGui.pop_style_color(1)
        outpost_points = bot_vars.map_data.get("outpost_path", []) or []
        if outpost_points:
            for index, point in enumerate(outpost_points, start=1):
                try:
                    x, y = int(point[0]), int(point[1])
                    PyImGui.text(f"- OP {index}: ({x},{y})")
                except Exception:
                    PyImGui.text(f"- OP {index}: {point}")
        else:
            PyImGui.text("- (empty)")

    if bot_vars.show_merged_list:
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Explorable (merged) Waypoints:")
        PyImGui.pop_style_color(1)
        merged_points = fsm_vars.explorable_waypoints or []
        if merged_points:
            for index, point in enumerate(merged_points, start=1):
                try:
                    x, y = int(point[0]), int(point[1])
                    PyImGui.text(f"- WP {index}: ({x},{y})")
                except Exception:
                    PyImGui.text(f"- WP {index}: {point}")

                PyImGui.same_line(0, 6)
                global_idx = index - 1
                if PyImGui.button(f">##go_merge_{index}", width=20):
                    if fsm_vars.path_and_aggro:
                        fsm_vars.path_and_aggro.force_move_to_index(global_idx, sticky=True)
                PyImGui.same_line(0, 2)
                if PyImGui.button(f"I##set_merge_{index}", width=18):
                    if fsm_vars.path_and_aggro:
                        fsm_vars.path_and_aggro.set_active_index(global_idx)
        else:
            PyImGui.text("- (empty)")


def render_loaded_script_info_section(
    bot_vars: Any,
    fsm_vars: Any,
    header_color: Sequence[float],
    icon_color: Sequence[float],
    compute_stats: StatsFn,
    segment_offset_fn: SegmentOffsetFn,
) -> None:
    """Render the full "Loaded Script Info" section of the PyQuishAI UI."""
    stats = compute_stats()

    _render_selected_map_header(stats, header_color, icon_color)
    _render_label_value("MapID / OutpostID:", f"{stats['map_id']} / {stats['outpost_id']}", header_color)
    _render_label_value("Segments:", str(stats.get("segments", 0)), header_color)
    _render_label_value("Outpost WPs:", str(stats.get("outpost_wp_total", 0)), header_color)
    _render_label_value("Explorable WPs (merged):", str(stats.get("explorable_wp_total", 0)), header_color)

    segment_counts = stats.get("segments_wp_counts", [])
    if segment_counts:
        PyImGui.separator()
        PyImGui.push_style_color(PyImGui.ImGuiCol.Text, header_color)
        PyImGui.text("Per-Segment Waypoints:")
        PyImGui.pop_style_color(1)
        for index, count in enumerate(segment_counts, start=1):
            PyImGui.text(f"- Segment {index}: {count}")

    _render_segment_details(bot_vars, fsm_vars, header_color, segment_offset_fn)
    _render_blessing_summary(stats, header_color)
    _render_optional_paths(bot_vars, fsm_vars, header_color)

