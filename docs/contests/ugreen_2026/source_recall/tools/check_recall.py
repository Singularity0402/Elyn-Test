"""Independent local reference checker. The Uliya Skill ZIP contains only Markdown."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat


MAX_MAP_BYTES = 8192
MAX_ENTRIES = 64
ID = re.compile(r"[a-z][a-z0-9-]{0,31}", re.ASCII)
BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.[A-Za-z0-9]{1,8}", re.ASCII)
DEVICE = re.compile(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", re.IGNORECASE | re.ASCII)
EDGE_KINDS = {("SOURCE", "WORK"), ("SOURCE", "EXPORT"), ("WORK", "EXPORT")}


@dataclass(frozen=True)
class Node:
    kind: str
    name: str | None
    line: int


@dataclass(frozen=True)
class Entry:
    name: str
    regular: bool


def valid_name(name: str) -> bool:
    return bool(BASENAME.fullmatch(name) and not DEVICE.fullmatch(name.split(".")[0]))


def parse_map(data: bytes) -> tuple[dict[str, Node], dict[str, list[str]]]:
    if not data or len(data) > MAX_MAP_BYTES:
        raise ValueError("Map is empty or exceeds 8192 bytes.")
    try:
        text = data.decode("ascii").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise ValueError("Map records require ASCII identifiers and filenames.") from None
    lines = text.removesuffix("\n").split("\n")
    if len(lines) < 3 or lines[0] != "SOURCE-RECALL 1" or lines[-1] != "END":
        raise ValueError("Expected the map header and final END marker.")
    nodes: dict[str, Node] = {}
    exports: set[str] = set()
    edges: dict[tuple[str, str], int] = {}
    for number, line in enumerate(lines[1:-1], 2):
        fields = line.split(" ")
        kind = fields[0]
        expected_fields = {"SOURCE": 2, "WORK": 2, "EXPORT": 3, "USES": 3}
        if expected_fields.get(kind) != len(fields) or not ID.fullmatch(fields[1]):
            raise ValueError(f"Line {number}: invalid record.")
        node_id = fields[1]
        if kind == "USES":
            target = fields[2]
            if not ID.fullmatch(target) or (node_id, target) in edges:
                raise ValueError(f"Line {number}: invalid or duplicate edge.")
            edges[node_id, target] = number
            continue
        if node_id in nodes:
            raise ValueError(f"Line {number}: duplicate ID.")
        name = fields[2] if kind == "EXPORT" else None
        if name is not None:
            if not valid_name(name) or name.casefold() in exports:
                raise ValueError(f"Line {number}: unsafe or duplicate export name.")
            exports.add(name.casefold())
        nodes[node_id] = Node(kind, name, number)

    if not 1 <= len(nodes) <= 24 or len(exports) > 16 or len(edges) > 36:
        raise ValueError("Map exceeds the node, export, or edge limit.")
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: set[str] = set()
    for (parent, child), number in edges.items():
        if parent not in nodes or child not in nodes:
            raise ValueError(f"Line {number}: undeclared endpoint.")
        if (nodes[parent].kind, nodes[child].kind) not in EDGE_KINDS:
            raise ValueError(f"Line {number}: unsupported edge direction.")
        outgoing[parent].append(child)
        incoming.add(child)
    for node_id, node in nodes.items():
        if node.kind != "SOURCE" and node_id not in incoming:
            raise ValueError(f"Line {node.line}: work or export has no recorded input.")
    return nodes, outgoing


def trace(source: str, nodes: dict[str, Node], outgoing: dict[str, list[str]]) -> dict[str, list[list[str]]]:
    if not ID.fullmatch(source) or source not in nodes or nodes[source].kind != "SOURCE":
        raise ValueError("Select an exact declared source ID.")
    paths: dict[str, list[list[str]]] = defaultdict(list)
    for child in outgoing.get(source, ()):
        if nodes[child].kind == "EXPORT":
            paths[child].append([source, child])
        else:
            for export in outgoing.get(child, ()):
                paths[export].append([source, child, export])
    return {key: sorted(paths[key]) for key in sorted(paths, key=lambda key: nodes[key].name)}


def is_link(info: os.stat_result) -> bool:
    reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(stat.S_ISLNK(info.st_mode) or reparse)


def safe_selection(path: Path, *, directory: bool) -> Path:
    if ".." in path.parts:
        raise ValueError("Selection contains a parent traversal.")
    path = path.absolute()
    for parent in reversed(path.parents):
        info = parent.lstat()
        if is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("Selection has an unsafe ancestor.")
    info = path.lstat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if is_link(info) or not expected_type(info.st_mode):
        raise ValueError("Selection has an unsafe type or redirects through a link.")
    return path


def inventory(folder: Path) -> list[Entry]:
    entries = []
    with os.scandir(folder) as listing:
        for entry in listing:
            if len(entries) == MAX_ENTRIES:
                raise ValueError("Inventory exceeds 64 direct entries.")
            info = entry.stat(follow_symlinks=False)
            entries.append(Entry(entry.name, stat.S_ISREG(info.st_mode) and not is_link(info)))
    return entries


def compare(nodes: dict[str, Node], paths: dict[str, list[list[str]]], entries: list[Entry]) -> dict:
    matches: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        matches[entry.name.casefold()].append(entry)
    mapped_names = {node.name.casefold() for node in nodes.values() if node.name is not None}
    untracked = [entry for entry in entries if entry.name.casefold() not in mapped_names]

    def state(name: str) -> tuple[str, str]:
        found = matches.get(name.casefold(), [])
        if not found:
            return "absent", "No matching entry in the complete inventory."
        if len(found) > 1:
            return "review", "Multiple case-equivalent entries."
        entry = found[0]
        if entry.name != name:
            return "review", "Filename case differs from the map."
        if not entry.regular:
            return "review", "The entry is not a verified regular file."
        return "hold", "Exact regular file observed."

    affected = []
    for key, routes in paths.items():
        name = nodes[key].name
        status, reason = state(name)
        affected.append({"name": name, "status": status, "reason": reason, "routes": routes})

    other_present = []
    other_review = []
    for key, node in nodes.items():
        if node.name is None or key in paths:
            continue
        status, reason = state(node.name)
        if status == "hold":
            other_present.append(node.name)
        if status == "review":
            other_review.append({"name": node.name, "reason": reason})
    return {
        "coverage": "complete",
        "entries_checked": len(entries),
        "affected": affected,
        "no_route_present": sorted(other_present),
        "other_entries_to_review": sorted(other_review, key=lambda row: row["name"]),
        "untracked": sorted(entry.name for entry in untracked if valid_name(entry.name)),
        "untracked_names_omitted": sum(not valid_name(entry.name) for entry in untracked),
    }


def run(source: str, map_path: Path, folder: Path) -> dict:
    map_path = safe_selection(map_path, directory=False)
    folder = safe_selection(folder, directory=True)
    if map_path.is_relative_to(folder):
        raise ValueError("Select a lineage map outside the export directory.")
    with map_path.open("rb") as file:
        nodes, outgoing = parse_map(file.read(MAX_MAP_BYTES + 1))
    paths = trace(source, nodes, outgoing)
    context = {"source": source, "map": map_path.name, "folder": folder.name}
    if not paths:
        return {**context, "coverage": "not inspected", "affected": [], "note": "No route in the supplied map."}
    try:
        return {**context, **compare(nodes, paths, inventory(folder))}
    except (OSError, ValueError):
        return {
            **context,
            "coverage": "unverified",
            "note": "Inventory failed, was unavailable, or exceeded the entry limit.",
            "affected": [
                {"name": nodes[key].name, "routes": routes, "status": "unverified"}
                for key, routes in paths.items()
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("map", type=Path)
    parser.add_argument("exports", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.source, args.map, args.exports)
    except (ValueError, OSError) as error:
        message = str(error) if isinstance(error, ValueError) else "Selected path could not be read."
        print(json.dumps({"coverage": "not inspected", "error": message}, indent=2))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 1 if report["coverage"] == "unverified" else 0


if __name__ == "__main__":
    raise SystemExit(main())
