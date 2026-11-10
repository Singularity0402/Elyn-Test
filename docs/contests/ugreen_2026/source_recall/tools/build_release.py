"""Build the submission files and a local evidence demonstration."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from wave import open as wave_open
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from check_recall import run


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "source-recall"
OUTPUT = ROOT / "submission"
DEMO = ROOT / "demo"
MEMBERS = ("SKILL.md", "references/map-and-report.md")
NAVY = "#152437"
PAPER = "#F8F7F2"
TEAL = "#166858"
INK = "#233448"
MUTED = "#45586B"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def package_and_check(checker: Path) -> dict:
    zip_path = OUTPUT / "source-recall.zip"
    expected = sorted(MEMBERS)
    if sorted(str(path.relative_to(PACKAGE).as_posix()) for path in PACKAGE.rglob("*") if path.is_file()) != expected:
        raise ValueError("Skill contents differ from the two reviewed Markdown members.")
    with ZipFile(zip_path, "w") as bundle:
        for name in MEMBERS:
            entry = ZipInfo(name, (2026, 11, 11, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            bundle.writestr(entry, (PACKAGE / name).read_bytes())
    if zip_path.stat().st_size > 10_000_000:
        raise ValueError("Package exceeds the submission limit.")
    with tempfile.TemporaryDirectory(prefix="source-recall-") as scratch:
        extracted = Path(scratch) / "source-recall"
        with ZipFile(zip_path) as bundle:
            if sorted(bundle.namelist()) != expected or bundle.testzip() is not None:
                raise ValueError("Archive entry or CRC mismatch.")
            for name in MEMBERS:
                target = extracted / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(name))
                if digest(target) != digest(PACKAGE / name):
                    raise ValueError(f"Archive content mismatch: {name}")
        process = subprocess.run(
            ["node", str(checker), str(extracted)],
            capture_output=True, encoding="utf-8", check=False, timeout=30,
        )
        result = json.loads(process.stdout)
        if (process.returncode or result["status"] != "static-pass"
                or result["summary"]["errors"] or result["summary"]["warnings"]):
            raise ValueError(f"Official checker rejected the release: {process.stdout}")
        for entry in result["files"]:
            if digest(extracted / entry["path"]) != entry["sha256"]:
                raise ValueError("Official checker reported a different file digest.")
    save_json(OUTPUT / "official-check.json", result)
    return {"sha256": digest(zip_path), "bytes": zip_path.stat().st_size, "members": list(MEMBERS)}


def make_proposal() -> dict:
    answers = json.loads((OUTPUT / "proposal.json").read_text(encoding="utf-8"))
    if len(answers) != 10:
        raise ValueError("The proposal requires ten substantive answers.")
    words = sum(len(re.findall(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b", body)) for _, body in answers)
    with_questions = sum(len(re.findall(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b", q)) for q, _ in answers) + words
    if with_questions > 500:
        raise ValueError(f"Proposal exceeds the conservative word budget: {with_questions}")
    pdf_path = OUTPUT / "source-recall-proposal.pdf"
    pdf = Canvas(str(pdf_path), pagesize=A4, invariant=1)
    pdf.setTitle("Source Recall | UGREEN AI NAS Hackathon proposal")
    width, height = A4
    margin = 47
    column_width = width - 2 * margin
    body_style = ParagraphStyle("body", fontName="Helvetica", fontSize=11, leading=16, textColor=colors.HexColor(INK))

    for page in range(2):
        pdf.setFillColor(colors.HexColor(PAPER))
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor(NAVY))
        pdf.rect(0, height - 159, width, 159, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#C0E5D9"))
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margin, height - 49, "UGREEN AI NAS HACKATHON  /  UNLEASH YOUR CREATIVITY")
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 38)
        pdf.drawString(margin, height - 105, "Source Recall")
        pdf.setFont("Helvetica", 12)
        subtitle = "Trace a withdrawn source into every recorded export" if page == 0 else "NAS workflow, validation and operating limits"
        pdf.drawString(margin, height - 130, subtitle)

        y = height - 199
        if page == 0:
            gap = 11
            tile = (column_width - 2 * gap) / 3
            for index, (label, text) in enumerate([
                ("SOURCE", "Narrator A"),
                ("WORK", "Episode mix"),
                ("EXPORT", "Campaign trailer"),
            ]):
                x = margin + index * (tile + gap)
                pdf.setFillColor(colors.HexColor("#E2EEE8"))
                pdf.roundRect(x, y - 44, tile, 54, 6, fill=1, stroke=0)
                pdf.setFillColor(colors.HexColor(TEAL))
                pdf.setFont("Helvetica-Bold", 8)
                pdf.drawString(x + 11, y - 9, label)
                pdf.setFillColor(colors.HexColor(NAVY))
                pdf.setFont("Helvetica-Bold", 12)
                pdf.drawString(x + 11, y - 28, text)
            y -= 77

        for index in range(page * 5, (page + 1) * 5):
            question, answer = answers[index]
            pdf.setFillColor(colors.HexColor(TEAL))
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(margin, y, f"{index + 1:02d}")
            pdf.setFillColor(colors.HexColor(NAVY))
            pdf.drawString(margin + 27, y, question)
            paragraph = Paragraph(escape(answer), body_style)
            _, height_used = paragraph.wrap(column_width - 27, 450)
            paragraph.drawOn(pdf, margin + 27, y - height_used - 9)
            y -= height_used + 36
        if y < 72:
            raise ValueError(f"Proposal page {page + 1} has insufficient footer clearance.")
        pdf.setStrokeColor(colors.HexColor("#B8C6C0"))
        pdf.line(margin, 65, width - margin, 65)
        pdf.setFillColor(colors.HexColor(MUTED))
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margin, 45, "ROUND 1  /  INITIAL SKILL PROPOSAL")
        pdf.drawRightString(width - margin, 45, f"{page + 1} / 2")
        pdf.showPage()
    pdf.save()
    return {"sha256": digest(pdf_path), "substantive_words": words, "words_including_questions": with_questions, "pages": 2}


def wave_fixture(path: Path, byte_value: int) -> None:
    with wave_open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(1)
        recording.setframerate(8000)
        recording.writeframes(bytes([byte_value]) * 800)


def make_demo() -> None:
    fixture_dir = DEMO / "exports"
    fixture_dir.mkdir(exist_ok=True)
    for name, value in [
        ("campaign-trailer.wav", 128), ("Campaign-Audio.wav", 129), ("campaign-bed.wav", 130)
    ]:
        wave_fixture(fixture_dir / name, value)
    (fixture_dir / "editor-notes.txt").write_text("Fictional studio demo. Keep notes outside delivery folders.\n", encoding="utf-8")
    if {p.name for p in fixture_dir.iterdir()} != {
        "campaign-trailer.wav", "Campaign-Audio.wav", "campaign-bed.wav", "editor-notes.txt"
    }:
        raise ValueError("Demo folder has unexpected files.")
    report = run("narrator-a", DEMO / "lineage.txt", fixture_dir)
    if report["coverage"] != "complete":
        raise ValueError("Demo inventory is incomplete.")
    save_json(DEMO / "local-report.json", report)

    counts = Counter(row["status"] for row in report["affected"])
    labels = {"hold": "Hold", "absent": "Absent", "review": "Review"}
    overview = "\n".join(
        f'<div class="metric {key}"><strong>{counts[key]}</strong><span>{label}</span></div>'
        for key, label in labels.items()
    )
    rows = []
    for row in report["affected"]:
        routes = "".join(f'<li>{" &rarr; ".join(map(escape, route))}</li>' for route in row["routes"])
        rows.append(
            f'<article><div class="file-heading"><h2>{escape(row["name"])}</h2>'
            f'<span class="state {row["status"]}">{labels[row["status"]]}</span></div>'
            f'<p>{escape(row["reason"])}</p><ul class="routes">{routes}</ul></article>'
        )
    other = ", ".join(map(escape, report["no_route_present"]))
    untracked = ", ".join(map(escape, report["untracked"]))
    template = (ROOT / "tools" / "report.html").read_text(encoding="utf-8")
    for token, value in {
        "@SOURCE@": escape(report["source"]),
        "@COUNT@": str(report["entries_checked"]),
        "@OVERVIEW@": overview,
        "@ROWS@": "\n".join(rows),
        "@OTHER@": other,
        "@UNTRACKED@": untracked,
    }.items():
        template = template.replace(token, value)
    (DEMO / "local-report.html").write_text(template, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official_checker", type=Path, help="Path to UGREEN check-skill.mjs")
    args = parser.parse_args()
    if not args.official_checker.is_file() or not shutil.which("node"):
        parser.error("The official checker and Node.js are required.")
    package = package_and_check(args.official_checker.resolve())
    proposal = make_proposal()
    make_demo()
    save_json(OUTPUT / "release-check.json", {"package": package, "proposal": proposal, "nas_runtime": "pending"})
    print(f"Official checker: zero errors and warnings. ZIP: {package['bytes']} bytes. Proposal: {proposal['substantive_words']} words.")


if __name__ == "__main__":
    main()
