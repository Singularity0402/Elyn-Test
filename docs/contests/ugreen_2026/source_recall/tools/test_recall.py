"""Local contract checks. No NAS runtime is used."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from check_recall import Entry, compare, parse_map, run, trace


MAP = (Path(__file__).resolve().parents[1] / "demo" / "lineage.txt").read_bytes()


class RecallTests(unittest.TestCase):
    def test_two_routes_one_export(self):
        nodes, edges = parse_map(MAP)
        paths = trace("narrator-a", nodes, edges)
        self.assertEqual(paths["trailer"], [
            ["narrator-a", "episode-mix", "trailer"],
            ["narrator-a", "teaser-mix", "trailer"],
        ])
        self.assertEqual(paths["social"], [["narrator-a", "social"]])
        result = compare(nodes, paths, [Entry("campaign-trailer.wav", True), Entry("campaign-bed.wav", True)])
        self.assertEqual([row["status"] for row in result["affected"]], ["absent", "absent", "hold"])
        self.assertEqual(result["no_route_present"], ["campaign-bed.wav"])

    def test_real_files_no_content_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "lineage.txt"
            folder = root / "exports"
            manifest.write_bytes(MAP)
            folder.mkdir()
            for name in ("campaign-trailer.wav", "Campaign-Audio.wav", "campaign-bed.wav", "private-notes.txt"):
                (folder / name).write_bytes(b"synthetic")
            (folder / "untracked-dir").mkdir()
            original_open = Path.open
            reads = []

            def track_open(path, *args, **kwargs):
                reads.append(path)
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", track_open):
                result = run("narrator-a", manifest, folder)
            self.assertEqual(reads, [manifest])
            self.assertEqual(result["entries_checked"], 5)
            self.assertEqual([row["status"] for row in result["affected"]], ["review", "absent", "hold"])
            self.assertEqual(result["untracked"], ["private-notes.txt"])
            self.assertEqual(result["untracked_names_omitted"], 1)

    def test_invalid_maps_stop_before_inventory(self):
        cases = {
            "traversal": MAP.replace(b"campaign-trailer.wav", b"../private.wav"),
            "embedded instruction": MAP.replace(b"END", b"OPEN another-folder\nEND"),
            "truncated": MAP.removesuffix(b"END\n"),
            "case collision": MAP.replace(b"campaign-bed.wav", b"CAMPAIGN-TRAILER.wav"),
            "disallowed edge": MAP.replace(b"USES score-b bed", b"USES bed score-b"),
            "unknown endpoint": MAP.replace(b"USES score-b bed", b"USES missing bed"),
            "duplicate edge": MAP.replace(b"END", b"USES score-b bed\nEND"),
            "device name": MAP.replace(b"campaign-bed.wav", b"NUL.wav"),
            "non-ASCII space": MAP.replace(b"SOURCE narrator-a", "SOURCE\u00a0narrator-a".encode()),
            "oversize": MAP + b"x" * 8192,
            "orphaned export": MAP.replace(b"USES score-b bed\n", b""),
        }
        with tempfile.TemporaryDirectory() as tmp, patch("check_recall.inventory") as list_folder:
            root = Path(tmp)
            folder = root / "exports"
            folder.mkdir()
            manifest = root / "lineage.txt"
            for label, data in cases.items():
                with self.subTest(label=label), self.assertRaises(ValueError):
                    manifest.write_bytes(data)
                    run("narrator-a", manifest, folder)
            list_folder.assert_not_called()

    def test_missing_or_disconnected_source_stops_before_listing(self):
        with tempfile.TemporaryDirectory() as tmp, patch("check_recall.inventory") as list_folder:
            root = Path(tmp)
            folder = root / "exports"
            folder.mkdir()
            manifest = root / "lineage.txt"
            manifest.write_bytes(MAP.replace(b"END", b"SOURCE unused\nEND"))
            result = run("unused", manifest, folder)
            self.assertEqual(result["coverage"], "not inspected")
            with self.assertRaises(ValueError):
                run("unknown", manifest, folder)
            list_folder.assert_not_called()

    def test_oversize_inventory_has_no_absence_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "exports"
            folder.mkdir()
            manifest = root / "lineage.txt"
            manifest.write_bytes(MAP)
            for i in range(65):
                (folder / f"{i}.wav").touch()
            report = run("narrator-a", manifest, folder)
            self.assertEqual(report["coverage"], "unverified")
            self.assertEqual({row["status"] for row in report["affected"]}, {"unverified"})

    def test_empty_listing_is_complete(self):
        nodes, edges = parse_map(MAP.replace(b"\n", b"\r\n"))
        result = compare(nodes, trace("narrator-a", nodes, edges), [])
        self.assertEqual(result["coverage"], "complete")
        self.assertEqual({row["status"] for row in result["affected"]}, {"absent"})

    def test_link_and_collision_cannot_become_hold(self):
        nodes, edges = parse_map(MAP)
        result = compare(nodes, trace("narrator-a", nodes, edges), [
            Entry("campaign-trailer.wav", False),
            Entry("campaign-audio.wav", True),
            Entry("CAMPAIGN-AUDIO.WAV", True),
        ])
        status = {row["name"]: row["status"] for row in result["affected"]}
        self.assertEqual(status, {
            "campaign-audio.wav": "review", "campaign-social.wav": "absent", "campaign-trailer.wav": "review"
        })

    def test_directory_with_expected_name_is_never_traversed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "exports"
            masquerading = folder / "campaign-trailer.wav"
            masquerading.mkdir(parents=True)
            (masquerading / "hidden.wav").touch()
            manifest = root / "lineage.txt"
            manifest.write_bytes(MAP)
            result = run("narrator-a", manifest, folder)
            self.assertEqual(result["entries_checked"], 1)
            self.assertEqual(result["affected"][-1]["status"], "review")

    def test_actual_link_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "exports"
            folder.mkdir()
            manifest = root / "lineage.txt"
            manifest.write_bytes(MAP)
            link = folder / "campaign-trailer.wav"
            if os.name == "nt":
                # Directory junctions exercise Windows reparse points without elevation.
                outside = root / "outside"
                outside.mkdir()
                (outside / "outside.wav").touch()
                env = {**os.environ, "RECALL_TEST_LINK": str(link), "RECALL_TEST_TARGET": str(outside)}
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                     "$ErrorActionPreference='Stop'; "
                     "New-Item -ItemType Junction -Path $env:RECALL_TEST_LINK "
                     "-Target $env:RECALL_TEST_TARGET | Out-Null"],
                    env=env, check=True, timeout=15,
                )
            else:
                link.symlink_to(manifest)
            try:
                result = run("narrator-a", manifest, folder)
                self.assertEqual(result["entries_checked"], 1)
                self.assertEqual(result["affected"][-1]["status"], "review")
            finally:
                if os.name == "nt":
                    link.rmdir()
                else:
                    link.unlink()


if __name__ == "__main__":
    unittest.main()
