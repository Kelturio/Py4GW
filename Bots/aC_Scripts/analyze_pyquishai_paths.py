"""Utilities for inspecting PyQuishAI map waypoints.

This script mirrors the dynamic loading logic used by ``PyQuishAI.py`` to
discover map modules within ``Bots/aC_Scripts/PyQuishAI_maps``.  For every
map it extracts the explorable and outpost waypoint lists, computes the
distance between successive coordinates, and emits both a human readable
summary and (optionally) a structured JSON report.

Example
-------
Run from the project root to analyse all known maps and write a JSON report::

    python Bots/aC_Scripts/analyze_pyquishai_paths.py \
        --output Bots/aC_Scripts/reports/pyquishai_path_report.json

The script prints a compact summary to stdout and stores the full per-step
metrics in the JSON file.  The resulting report can be used to spot unusually
long hops that may indicate out-of-bounds waypoints.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


DEFAULT_MAPS_DIR = Path("Bots") / "aC_Scripts" / "PyQuishAI_maps"


Coordinate = Tuple[float, float]


@dataclass
class SegmentStats:
    """Computed information for a single path (either map or outpost)."""

    waypoint_count: int
    total_distance: float
    segments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def max_segment(self) -> Dict[str, Any] | None:
        if not self.segments:
            return None
        return max(self.segments, key=lambda seg: seg["distance"])

    @property
    def min_segment(self) -> Dict[str, Any] | None:
        if not self.segments:
            return None
        return min(self.segments, key=lambda seg: seg["distance"])

    @property
    def average_segment(self) -> float:
        if not self.segments:
            return 0.0
        return self.total_distance / len(self.segments)


@dataclass
class MapReport:
    region: str
    map_name: str
    map_stats: SegmentStats
    outpost_stats: SegmentStats | None = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "region": self.region,
            "map": self.map_name,
            "map_path": {
                "waypoint_count": self.map_stats.waypoint_count,
                "total_distance": self.map_stats.total_distance,
                "segment_count": self.map_stats.segment_count,
                "segments": self.map_stats.segments,
            },
            "warnings": self.warnings,
        }
        if self.outpost_stats is not None:
            payload["outpost_path"] = {
                "waypoint_count": self.outpost_stats.waypoint_count,
                "total_distance": self.outpost_stats.total_distance,
                "segment_count": self.outpost_stats.segment_count,
                "segments": self.outpost_stats.segments,
            }
        return payload


def is_coordinate(candidate: Any) -> bool:
    """Return ``True`` if *candidate* looks like an (x, y) coordinate."""

    if not isinstance(candidate, (list, tuple)) or len(candidate) < 2:
        return False
    try:
        float(candidate[0])
        float(candidate[1])
    except (TypeError, ValueError):
        return False
    return True


def normalise_coordinate(value: Sequence[Any]) -> Coordinate:
    return float(value[0]), float(value[1])


def flatten_map_path(data: Any) -> Tuple[List[Coordinate], List[str]]:
    """Flatten the map path structure used by PyQuishAI scripts.

    Parameters
    ----------
    data:
        Raw ``<MapName>`` attribute from a map module.  This can be either a
        flat list of coordinate pairs or a list of dictionaries describing
        segments (with their actual coordinates stored under the ``"path"``
        key).

    Returns
    -------
    Tuple[List[Coordinate], List[str]]
        The ordered coordinate list and any warnings encountered while parsing
        the structure.
    """

    if isinstance(data, tuple):
        data = list(data)

    warnings: List[str] = []
    if not isinstance(data, list):
        warnings.append("Expected list for map path data; got %r" % (type(data).__name__,))
        return [], warnings

    if data and all(isinstance(segment, dict) for segment in data):
        coords: List[Coordinate] = []
        for index, segment in enumerate(data):
            path = segment.get("path") if isinstance(segment, dict) else None
            if isinstance(path, tuple):
                path = list(path)
            if not isinstance(path, list):
                warnings.append(
                    f"Segment {index} is missing a 'path' list; skipping"
                )
                continue
            for point_index, point in enumerate(path):
                if not is_coordinate(point):
                    warnings.append(
                        f"Segment {index} point {point_index} is not a 2D coordinate; skipping"
                    )
                    continue
                coords.append(normalise_coordinate(point))
        return coords, warnings

    coords = []
    for idx, point in enumerate(data):
        if not is_coordinate(point):
            warnings.append(f"Entry {idx} is not a 2D coordinate; skipping")
            continue
        coords.append(normalise_coordinate(point))
    return coords, warnings


def compute_segments(points: Sequence[Coordinate]) -> SegmentStats:
    """Calculate step distances and totals for an ordered waypoint list."""

    segments: List[Dict[str, Any]] = []
    total = 0.0
    for idx in range(len(points) - 1):
        x1, y1 = points[idx]
        x2, y2 = points[idx + 1]
        distance = math.hypot(x2 - x1, y2 - y1)
        total += distance
        segments.append(
            {
                "from_index": idx,
                "to_index": idx + 1,
                "from": [x1, y1],
                "to": [x2, y2],
                "distance": distance,
            }
        )

    return SegmentStats(waypoint_count=len(points), total_distance=total, segments=segments)


def load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to create spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_map_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def analyse_map_file(path: Path, module_index: int) -> MapReport:
    relative_path = path.relative_to(DEFAULT_MAPS_DIR)
    region = relative_path.parts[0] if len(relative_path.parts) > 1 else ""
    map_name = path.stem
    module_name = f"_pyquishai_map_{module_index}_{map_name}"

    module = load_module(path, module_name)

    raw_map_path = getattr(module, map_name, [])
    raw_outpost_path = getattr(module, f"{map_name}_outpost_path", None)

    map_points, map_warnings = flatten_map_path(raw_map_path)
    map_stats = compute_segments(map_points)

    outpost_stats = None
    warnings = list(map_warnings)

    if raw_outpost_path is not None:
        outpost_points, outpost_warnings = flatten_map_path(raw_outpost_path)
        warnings.extend(outpost_warnings)
        outpost_stats = compute_segments(outpost_points)

    return MapReport(region=region, map_name=map_name, map_stats=map_stats, outpost_stats=outpost_stats, warnings=warnings)


def format_summary(report: MapReport) -> str:
    map_stats = report.map_stats
    lines = [
        f"{report.region}/{report.map_name}" if report.region else report.map_name,
        f"  map_path: {map_stats.waypoint_count} waypoints, {map_stats.segment_count} segments, total distance {map_stats.total_distance:,.2f}",
    ]
    if map_stats.segment_count:
        lines.append(
            f"    avg segment {map_stats.average_segment:,.2f}, max {map_stats.max_segment['distance']:,.2f}, min {map_stats.min_segment['distance']:,.2f}"
        )
    if report.outpost_stats is not None:
        op = report.outpost_stats
        lines.append(
            f"  outpost_path: {op.waypoint_count} waypoints, {op.segment_count} segments, total distance {op.total_distance:,.2f}"
        )
        if op.segment_count:
            lines.append(
                f"    avg segment {op.average_segment:,.2f}, max {op.max_segment['distance']:,.2f}, min {op.min_segment['distance']:,.2f}"
            )
    if report.warnings:
        for warning in report.warnings:
            lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def write_report(reports: Sequence[MapReport], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialisable = [report.to_dict() for report in reports]
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(serialisable, handle, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse PyQuishAI waypoint distances")
    parser.add_argument(
        "--maps-dir",
        type=Path,
        default=DEFAULT_MAPS_DIR,
        help="Root directory that contains PyQuishAI map scripts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write a JSON report with per-segment distances",
    )
    args = parser.parse_args()

    maps_dir = args.maps_dir
    if not maps_dir.exists():
        raise SystemExit(f"Map directory not found: {maps_dir}")

    reports: List[MapReport] = []
    for index, path in enumerate(iter_map_files(maps_dir), start=1):
        try:
            report = analyse_map_file(path, index)
        except Exception as exc:  # pragma: no cover - defensive logging only
            rel = path.relative_to(maps_dir)
            raise RuntimeError(f"Failed to analyse {rel}: {exc}") from exc
        reports.append(report)
        print(format_summary(report))

    if args.output:
        write_report(reports, args.output)
        print(f"\nWrote detailed report to {args.output}")

    print(f"\nAnalysed {len(reports)} map files from {maps_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
