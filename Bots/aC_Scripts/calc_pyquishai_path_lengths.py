"""Generate distance metrics for all PyQuishAI map files.

This helper mirrors the data-loading pattern used by ``PyQuishAI.py`` to
collect the waypoint coordinates from every map module under
``PyQuishAI_maps``.  For each map it calculates the Euclidean distance
between consecutive waypoints as well as the cumulative path length.

Usage
-----
python Bots/aC_Scripts/calc_pyquishai_path_lengths.py [--output OUTPUT]

If ``--output`` is supplied the report is written to that path as JSON.
Otherwise it is printed to stdout.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
MAP_ROOT = SCRIPT_DIR / "PyQuishAI_maps"


Coordinate = Tuple[float, float]


@dataclass
class SegmentDistance:
    index: int
    start: Coordinate
    end: Coordinate
    distance: float

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "from": list(self.start),
            "to": list(self.end),
            "distance": self.distance,
        }


@dataclass
class MapDistanceReport:
    map_id: str
    waypoint_count: int
    total_distance: float
    segments: List[SegmentDistance]
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "map": self.map_id,
            "waypoint_count": self.waypoint_count,
            "total_distance": self.total_distance,
            "segments": [segment.to_dict() for segment in self.segments],
            "warnings": list(self.warnings),
        }


def _is_coordinate(value: Sequence[object]) -> bool:
    """Return ``True`` if *value* looks like an ``(x, y)`` coordinate pair."""
    if not isinstance(value, (list, tuple)):
        return False
    if len(value) != 2:
        return False
    x, y = value
    return isinstance(x, (int, float)) and isinstance(y, (int, float))


def _merge_waypoints(data) -> List[Coordinate]:
    """Flatten map data into an ordered list of coordinate pairs."""
    if isinstance(data, dict):
        if "path" in data:
            return _merge_waypoints(data["path"])
        # Fall back to exploring values – allows nested dict structures.
        coords: List[Coordinate] = []
        for value in data.values():
            coords.extend(_merge_waypoints(value))
        return coords

    if isinstance(data, (list, tuple)):
        coords: List[Coordinate] = []
        for item in data:
            if _is_coordinate(item):
                x, y = item  # type: ignore[misc]
                coords.append((float(x), float(y)))
            else:
                coords.extend(_merge_waypoints(item))
        return coords

    return []


def _load_module_points(module_path: Path) -> Tuple[List[Coordinate], List[str]]:
    """Load a map module and return its merged waypoints and any warnings."""
    warnings: List[str] = []
    module_name = module_path.stem
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, module_name):
        warnings.append("Map variable not found in module.")
        return [], warnings

    data = getattr(module, module_name)
    waypoints = _merge_waypoints(data)

    if not waypoints:
        warnings.append("No waypoint data detected.")

    return waypoints, warnings


def _compute_distances(points: Sequence[Coordinate]) -> List[SegmentDistance]:
    segments: List[SegmentDistance] = []
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        distance = math.hypot(end[0] - start[0], end[1] - start[1])
        segments.append(SegmentDistance(index=index, start=start, end=end, distance=distance))
    return segments


def build_report() -> List[MapDistanceReport]:
    if not MAP_ROOT.exists():
        raise FileNotFoundError(f"Map directory not found: {MAP_ROOT}")

    reports: List[MapDistanceReport] = []

    for module_path in sorted(MAP_ROOT.rglob("*.py")):
        if module_path.name == "__init__.py":
            continue

        waypoints, warnings = _load_module_points(module_path)
        segments = _compute_distances(waypoints)
        total_distance = sum(segment.distance for segment in segments)

        relative_id = str(module_path.relative_to(MAP_ROOT).with_suffix(""))
        reports.append(
            MapDistanceReport(
                map_id=relative_id.replace(os.sep, "/"),
                waypoint_count=len(waypoints),
                total_distance=total_distance,
                segments=segments,
                warnings=warnings,
            )
        )

    return reports


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional path to write the JSON report. Printed to stdout when omitted.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    reports = build_report()

    payload = {
        "map_count": len(reports),
        "reports": [report.to_dict() for report in reports],
    }
    rendered = json.dumps(payload, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
