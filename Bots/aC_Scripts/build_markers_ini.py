#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build a combined markers.ini from Guild Wars map path scripts.

Key features:
- Recursively scans a folder for .py files and safely imports them.
- Detects map datasets of two shapes:
    1) list[dict] segments with {"path": [(x,y), ...], optional "bless": (x,y)}
    2) list[(x,y), ...] as a single segment (no bless)
- Emits two sets of lines per map file:
    * Explorable map (uses map_id)
    * Outpost map (uses outpost_id)
- Coloring:
    * Normal path segments alternate between --color-a and --color-b (starting with A)
    * Bless link (bless -> first waypoint) uses --bless-color
    * NEW: Connector between segments uses --connector-color
      - From last wp of segment N → next segment's bless (if present) else next first wp
- Colors must be provided as 0xAARRGGBB (e.g., 0xFFFF8800). They’re written unquoted.

Usage:
  python build_markers_ini.py ^
      --root "path\\to\\maps" ^
      --out "markers.ini" ^
      --color-a 0xFFFF8800 ^
      --color-b 0xFF00AAFF ^
      --bless-color 0xFFFFFF00 ^
      --connector-color 0xFFFF00FF ^
      --start-index 4
"""

import argparse
import importlib.util
import os
import re
import sys
import types
from typing import Any, Dict, Iterable, List, Sequence, Tuple, Optional

Coord = Tuple[float, float]

# ---------- Helpers for data shapes ----------

def float_pair(t: Sequence[Any]) -> Coord:
    return (float(t[0]), float(t[1]))

def is_tuple_pair(v: Any) -> bool:
    return (isinstance(v, (tuple, list))
            and len(v) == 2
            and all(isinstance(x, (int, float)) for x in v))

def is_list_of_tuple_pairs(v: Any) -> bool:
    return isinstance(v, list) and all(is_tuple_pair(x) for x in v)

def is_segment_dict(d: Any) -> bool:
    # Segment shape: {"path": [(x,y), ...], optional "bless": (x,y)}
    if not isinstance(d, dict):
        return False
    if "path" not in d:
        return False
    p = d["path"]
    return is_list_of_tuple_pairs(p)

def is_list_of_segment_dicts(v: Any) -> bool:
    return isinstance(v, list) and all(is_segment_dict(x) for x in v)

# ---------- Color parsing/validation ----------

HEX8_RE = re.compile(r"^(0x)?([0-9A-Fa-f]{8})$")

def color_arg(s: str) -> str:
    """
    Accepts:
      - '0xAARRGGBB' (preferred)
      - 'AARRGGBB' (adds 0x)
      - '#RRGGBB' (auto-upgrades to 0xFFRRGGBB)
    Returns normalized '0xAARRGGBB' (uppercase).
    """
    s = s.strip()
    if s.startswith("#"):
        # upgrade #RRGGBB -> 0xFFRRGGBB
        rgb = s[1:]
        if len(rgb) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", rgb):
            raise argparse.ArgumentTypeError(f"Invalid color '{s}'. Use 0xAARRGGBB.")
        return f"0xFF{rgb.upper()}"

    m = HEX8_RE.match(s)
    if m:
        hexpart = m.group(2).upper()
        return f"0x{hexpart}"

    raise argparse.ArgumentTypeError(
        f"Invalid color '{s}'. Expected 0xAARRGGBB (e.g., 0xFFFF8800)."
    )

# ---------- Import & discovery ----------

def safe_import(filepath: str, unique_name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(unique_name, filepath)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load spec for {filepath}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # Executes the file; assumes trusted data files.
    return mod

def iter_py_files(root: str) -> Iterable[str]:
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith(".py"):
                yield os.path.join(dirpath, fn)

def normalize_var_base_names(mod: types.ModuleType) -> List[str]:
    """
    Find candidate base names that have an accompanying *_ids dict.
    These are the authoritative "map names" we will process.
    """
    base_names: List[str] = []
    for k, v in vars(mod).items():
        if k.endswith("_ids") and isinstance(v, dict):
            base_names.append(k[:-4])
    return sorted(set(base_names))

def pick_map_data(mod: types.ModuleType, base: str):
    """
    Returns (data, outpost, ids) for a given base name.
    - data: either list[tuple] or list[dict{path, bless?}]
    - outpost: list[tuple]
    - ids: dict with map_id and outpost_id
    """
    data = getattr(mod, base, None)
    outpost = getattr(mod, f"{base}_outpost_path", None)
    ids = getattr(mod, f"{base}_ids", None)

    if not isinstance(ids, dict) or "map_id" not in ids or "outpost_id" not in ids:
        return None, None, None

    # Accept two forms for explorable data:
    if is_list_of_segment_dicts(data) or is_list_of_tuple_pairs(data):
        pass
    else:
        data = None  # Unsupported shape; skip

    if not is_list_of_tuple_pairs(outpost):
        outpost = []  # Tolerate missing outpost path

    return data, outpost, ids

# ---------- INI section builders ----------

def line_sections_from_waypoints(
    name_prefix: str,
    points: List[Coord],
    map_id: int,
    section_index_start: int,
    color_a: str,
    color_b: str,
    start_wp_index: int = 1,
) -> Tuple[List[str], int, int]:
    """
    Build INI sections from a sequence of waypoints (pairs of consecutive points).
    Alternates colors A/B starting with A on the first segment.

    Returns:
      (list_of_sections, next_section_index, next_wp_index)
    """
    sections: List[str] = []
    color_toggle = True  # True -> A, False -> B
    wp_idx = start_wp_index

    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        color = color_a if color_toggle else color_b
        color_toggle = not color_toggle

        section_name = f"customline{section_index_start:03d}"
        pretty_name = f"{name_prefix}_wp{wp_idx:03d}"
        s = (
            f"[{section_name}]\n"
            f"name = {pretty_name}\n"
            f"x1 = {x1:.6f}\n"
            f"y1 = {y1:.6f}\n"
            f"x2 = {x2:.6f}\n"
            f"y2 = {y2:.6f}\n"
            f"color = {color}\n"
            f"map = {map_id}\n"
            f"visible = true\n"
            f"draw_on_terrain = true\n\n"
        )
        sections.append(s)
        section_index_start += 1
        wp_idx += 1

    return sections, section_index_start, wp_idx

def add_connector_section(
    section_index: int,
    name_prefix: str,
    start_pt: Coord,
    end_pt: Coord,
    map_id: int,
    connector_color: str,
) -> Tuple[str, int]:
    section_name = f"customline{section_index:03d}"
    pretty_name = f"{name_prefix}_connector"
    s = (
        f"[{section_name}]\n"
        f"name = {pretty_name}\n"
        f"x1 = {start_pt[0]:.6f}\n"
        f"y1 = {start_pt[1]:.6f}\n"
        f"x2 = {end_pt[0]:.6f}\n"
        f"y2 = {end_pt[1]:.6f}\n"
        f"color = {connector_color}\n"
        f"map = {map_id}\n"
        f"visible = true\n"
        f"draw_on_terrain = true\n\n"
    )
    return s, section_index + 1

def sections_for_explorable(
    base: str,
    data: Any,
    map_id: int,
    section_index_start: int,
    color_a: str,
    color_b: str,
    bless_color: str,
    connector_color: str,
) -> Tuple[List[str], int]:
    """
    Build sections for the explorable map. Supports:
      - list of dict segments with optional 'bless'
      - list of (x,y) as a single segment
    Special rules:
      - If segment has "bless", add one line from bless -> first waypoint using bless_color.
      - Add connector from last wp of seg N to next seg's bless (if present) or first wp.
    """
    sections: List[str] = []

    if is_list_of_segment_dicts(data):
        seg_paths: List[List[Coord]] = []
        seg_bless: List[Optional[Coord]] = []

        # First pass: normalize segments
        for seg in data:
            path = [float_pair(p) for p in seg["path"]]
            seg_paths.append(path)
            seg_bless.append(float_pair(seg["bless"]) if "bless" in seg else None)

        # Second pass: emit per-segment lines (+ bless link) and connectors
        for idx, path in enumerate(seg_paths, start=1):
            seg_prefix = f"{base}_seg{idx:02d}"

            # Bless link (bless -> first waypoint) if present and segment has at least one waypoint
            if seg_bless[idx - 1] is not None and path:
                bx, by = seg_bless[idx - 1]
                x2, y2 = path[0]
                section_name = f"customline{section_index_start:03d}"
                pretty_name = f"{seg_prefix}_bless_to_wp001"
                s = (
                    f"[{section_name}]\n"
                    f"name = {pretty_name}\n"
                    f"x1 = {bx:.6f}\n"
                    f"y1 = {by:.6f}\n"
                    f"x2 = {x2:.6f}\n"
                    f"y2 = {y2:.6f}\n"
                    f"color = {bless_color}\n"
                    f"map = {map_id}\n"
                    f"visible = true\n"
                    f"draw_on_terrain = true\n\n"
                )
                sections.append(s)
                section_index_start += 1

            # Segment path with alternating colors
            if len(path) >= 2:
                seg_sections, section_index_start, _ = line_sections_from_waypoints(
                    name_prefix=seg_prefix,
                    points=path,
                    map_id=map_id,
                    section_index_start=section_index_start,
                    color_a=color_a,
                    color_b=color_b,
                    start_wp_index=1,
                )
                sections.extend(seg_sections)

            # Connector to next segment (if any and we have a starting point)
            if idx < len(seg_paths):
                if path:
                    start_pt = path[-1]
                    next_path = seg_paths[idx]
                    next_bless = seg_bless[idx]
                    if next_bless is not None:
                        end_pt = next_bless
                    elif next_path:
                        end_pt = next_path[0]
                    else:
                        end_pt = None

                    if end_pt is not None:
                        connector_name = f"{base}_seg{idx:02d}_to_seg{idx+1:02d}"
                        s, section_index_start = add_connector_section(
                            section_index=section_index_start,
                            name_prefix=connector_name,
                            start_pt=start_pt,
                            end_pt=end_pt,
                            map_id=map_id,
                            connector_color=connector_color,
                        )
                        sections.append(s)

    elif is_list_of_tuple_pairs(data):
        # Single segment (no bless, no connectors)
        path = [float_pair(p) for p in data]
        seg_prefix = f"{base}_seg01"
        seg_sections, section_index_start, _ = line_sections_from_waypoints(
            name_prefix=seg_prefix,
            points=path,
            map_id=map_id,
            section_index_start=section_index_start,
            color_a=color_a,
            color_b=color_b,
            start_wp_index=1,
        )
        sections.extend(seg_sections)

    return sections, section_index_start

def sections_for_outpost(
    base: str,
    outpost: List[Coord],
    outpost_id: int,
    section_index_start: int,
    color_a: str,
    color_b: str,
) -> Tuple[List[str], int]:
    if not outpost or not is_list_of_tuple_pairs(outpost):
        return [], section_index_start

    points = [float_pair(p) for p in outpost]
    name_prefix = f"{base}_outpost"
    seg_sections, section_index_start, _ = line_sections_from_waypoints(
        name_prefix=name_prefix,
        points=points,
        map_id=outpost_id,
        section_index_start=section_index_start,
        color_a=color_a,
        color_b=color_b,
        start_wp_index=1,
    )
    return seg_sections, section_index_start

def process_module(
    mod: types.ModuleType,
    filepath: str,
    section_index_start: int,
    color_a: str,
    color_b: str,
    bless_color: str,
    connector_color: str,
) -> Tuple[List[str], int]:
    """
    Returns (sections, next_section_index)
    """
    sections: List[str] = []
    bases = normalize_var_base_names(mod)
    if not bases:
        return sections, section_index_start

    for base in bases:
        data, outpost, ids = pick_map_data(mod, base)
        if ids is None:
            continue
        map_id = int(ids["map_id"])
        outpost_id = int(ids["outpost_id"])

        # Explorable
        if data is not None:
            expl_sections, section_index_start = sections_for_explorable(
                base, data, map_id, section_index_start, color_a, color_b, bless_color, connector_color
            )
            sections.extend(expl_sections)

        # Outpost
        out_sections, section_index_start = sections_for_outpost(
            base, outpost, outpost_id, section_index_start, color_a, color_b
        )
        sections.extend(out_sections)

    return sections, section_index_start

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Combine map path data into markers.ini (colors in 0xAARRGGBB).")
    ap.add_argument("--root", required=True, help="Root folder to scan for .py files")
    ap.add_argument("--out", required=True, help="Output INI file path (e.g., markers.ini)")
    ap.add_argument("--color-a", type=color_arg, default="0xFFFF8800", help="Primary alternating color (0xAARRGGBB)")
    ap.add_argument("--color-b", type=color_arg, default="0xFF00AAFF", help="Secondary alternating color (0xAARRGGBB)")
    ap.add_argument("--bless-color", type=color_arg, default="0xFFFFFF00", help="Special color for bless → first waypoint (0xAARRGGBB)")
    ap.add_argument("--connector-color", type=color_arg, default="0xFFFF00FF", help="Special color for inter-segment connectors (0xAARRGGBB)")
    ap.add_argument("--start-index", type=int, default=4, help="Starting numeric index for [customlineNNN] (e.g., 4 -> customline004)")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"[ERROR] Root path not found or not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    all_sections: List[str] = []
    next_idx = max(0, args.start_index)

    for pyfile in iter_py_files(root):
        if os.path.basename(pyfile) == "__init__.py":
            continue
        unique_mod_name = f"mapdata_{abs(hash(pyfile))}"
        try:
            mod = safe_import(pyfile, unique_mod_name)
        except Exception as e:
            print(f"[WARN] Skipping {pyfile}: import failed: {e}", file=sys.stderr)
            continue

        try:
            sections, next_idx = process_module(
                mod,
                pyfile,
                next_idx,
                color_a=args.color_a,
                color_b=args.color_b,
                bless_color=args.bless_color,
                connector_color=args.connector_color,
            )
            if sections:
                all_sections.extend(sections)
                print(f"[OK] {pyfile}: added {len(sections)} line(s)")
            else:
                print(f"[INFO] {pyfile}: no eligible map data found")
        except Exception as e:
            print(f"[WARN] Error processing {pyfile}: {e}", file=sys.stderr)

    if not all_sections:
        print("[INFO] No sections generated. Nothing to write.")
        return

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(all_sections)

    print(f"[DONE] Wrote {len(all_sections)} sections to {out_path}")

if __name__ == "__main__":
    main()
