# -*- coding: utf-8 -*-
"""
04_합성.py - 세종사이버대 AI창작 공모전 컷툰 '서울에 졌습니다' 말풍선/대사 합성기

역할
  - ChatGPT 등으로 만든 '글자 없는' 컷 이미지 8장에 한글 말풍선, 해설 상자, 효과음, 제목을 합성한다.
  - 이미지 AI에는 한글을 맡기지 않는다. 모든 글자는 이 스크립트가 SCDream5.otf 로 그린다.
  - 결과는 4:5 (기본 1440x1800, 공고 최소 1080x1350 이상) JPG 또는 PNG.
  - 말풍선·구역 데이터는 같은 폴더의 cuts.json (07_지시문_가이드_생성.py 가 만든다)에서 읽는다.

세 가지 모드(결과물이 서로 섞이지 않도록 폴더와 파일 이름 앞머리가 다르다)
  제출본 : python -I 04_합성.py --images 컷이미지 --name 이름
           8장이 모두 있어야만 만들어진다. 하나라도 없으면 아무것도 쓰지 않고 오류 종료(종료코드 2).
           폴더 '출력_제출', 파일명 [지원분야]_[작품제목]_[이름]_NN.jpg
           (--sheet 미리보기와 --zip 묶음은 제출 파일과 섞이지 않게 '출력_제출_미리보기', '출력_제출_zip' 폴더에 따로 저장)
  점검본 : python -I 04_합성.py --images 컷이미지 --show-zones
           빨간 구역선과 '점검본' 표시가 들어간다. 폴더 '출력_점검', 파일명 앞에 '점검_'
  시험본 : python -I 04_합성.py --preview
           이미지가 없는 컷은 회색 자리표시. 'SAMPLE' 표시. 폴더 '출력_시험', 파일명 앞에 '시험_'
  (--no-text 는 글자 없이 크롭·리사이즈만: 폴더 '출력_원본', 파일명 앞에 '원본_')

기타 옵션
  --backing   구역마다 종이색 판을 깔아 글자 가독성을 지킨다(AI가 구역을 못 비웠을 때 재생성 없이 쓰는 안전장치)
  --six       6컷 압축안(컷 1,3,4,6,7,8). 파일 번호는 01~06 으로 새로 매긴다.
  --zip       제출본을 [지원분야]_[작품제목]_[이름].zip 으로도 묶는다(문의 회신이 압축 허용일 때)
  --lint      cuts.json 의 말풍선이 구역 안에 있는지, 글자가 최소 크기를 지키는지 검사만 한다

컷 이미지 파일명 규칙: 이름이 숫자(1~2자리)로 시작하거나 '컷'/'cut' 뒤에 숫자가 오는 것. 예) 컷03.png, cut3.png, 3.jpg
같은 번호 파일이 여럿이면 수정 시각이 가장 최근인 것을 쓰고 목록을 경고로 보여 준다.
이미지가 4:5 가 아니면 가운데를 기준으로 4:5 로 잘라 낸다(2:3 원본이면 위아래 8.3% 제거).
필요 패키지: Pillow (pip install pillow)

말풍선 좌표(box, tail, zones)는 모두 4:5 프레임 기준 0~1 정규화 좌표(x, y, w, h)이다.
"""
import argparse
import json
import math
import os
import re
import sys
import zipfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    print("Pillow 가 필요합니다: pip install pillow")
    sys.exit(1)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
FONT_DEFAULT = r"C:\Users\user\S-Core_Dream_OTF\SCDream5.otf"
FONT_FALLBACKS = [r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"]

# ---- 팔레트 (07_지시문_가이드_생성.py 와 동일) ----
PAPER = "#EDE6D6"
NAVY = "#1F2A44"
GRAY_MID = "#5F6E85"
GRAY_LIGHT = "#C5CED8"
CREAM = "#F4F1E8"
ORANGE = "#E8591A"
INK = "#1B1B22"

SS = 2          # 슈퍼샘플링 배율(말풍선 가장자리 부드럽게)
LH = 1.28       # 줄 간격
MIN_PX_1080 = 17.0   # 1080 폭 기준 최소 글자 높이(px). 이보다 작아지면 오류


def log(msg):
    print(msg, flush=True)


def load_data(path):
    p = Path(path) if path else HERE / "cuts.json"
    if not p.is_file():
        log("[오류] %s 가 없습니다. 먼저 'python -I 07_지시문_가이드_생성.py' 를 실행하세요." % p)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def resolve_font(path_arg, allow_fallback):
    primary = []
    if path_arg:
        primary.append(path_arg)
    if os.environ.get("SCDREAM_FONT"):
        primary.append(os.environ["SCDREAM_FONT"])
    primary += [str(HERE / "fonts" / "SCDream5.otf"), FONT_DEFAULT]
    for c in primary:
        if c and Path(c).is_file():
            log("글꼴: %s" % c)
            return c
    if allow_fallback:
        for c in FONT_FALLBACKS:
            if Path(c).is_file():
                log("[경고] SCDream5.otf 를 찾지 못해 대체 글꼴을 씁니다: %s (제출본에는 권장하지 않음)" % c)
                return c
    log("[오류] SCDream5.otf 를 찾지 못했습니다. --font 로 경로를 주거나 환경변수 SCDREAM_FONT 를 설정하세요. "
        "대체 글꼴을 허용하려면 --allow-fallback-font 를 쓰세요.")
    sys.exit(1)


_font_cache = {}


def get_font(path, size):
    key = (path, int(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, int(size))
    return _font_cache[key]


def wrap_lines(draw, text, font, maxw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word) if cur else word
            if draw.textlength(trial, font=font) <= maxw:
                cur = trial
                continue
            if cur:
                lines.append(cur)
                cur = ""
            if draw.textlength(word, font=font) <= maxw:
                cur = word
            else:
                chunk = ""
                for ch in word:
                    if draw.textlength(chunk + ch, font=font) <= maxw:
                        chunk += ch
                    else:
                        lines.append(chunk)
                        chunk = ch
                cur = chunk
        lines.append(cur)
    return lines


def fit_text(draw, text, fpath, maxw, maxh, start, minimum, single_line=False):
    """(font, lines, size, fits) 를 돌려준다. fits=False 면 최소 크기로도 상자에 안 들어간다."""
    size = int(start)
    while size >= minimum:
        font = get_font(fpath, size)
        lines = [text] if single_line else wrap_lines(draw, text, font, maxw)
        w = max(draw.textlength(l, font=font) for l in lines)
        h = len(lines) * size * LH
        if w <= maxw and h <= maxh:
            return font, lines, size, True
        size -= max(1, size // 40)
    font = get_font(fpath, minimum)
    lines = [text] if single_line else wrap_lines(draw, text, font, maxw)
    w = max(draw.textlength(l, font=font) for l in lines)
    h = len(lines) * minimum * LH
    return font, lines, minimum, (w <= maxw and h <= maxh)


def draw_lines(draw, lines, font, size, cx, cy, fill, stroke=0, stroke_fill=None, bold=0):
    total = len(lines) * size * LH
    y = cy - total / 2 + size * LH / 2
    for line in lines:
        draw.text((cx, y), line, font=font, fill=fill, anchor="mm",
                  stroke_width=int(stroke + bold), stroke_fill=stroke_fill or fill)
        y += size * LH


def px_box(box, W, H):
    x, y, w, h = box
    return x * W, y * H, (x + w) * W, (y + h) * H


def draw_ellipse_bubble(d, rect, tail, lw, fill, outline):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    a, b = (x1 - x0) / 2, (y1 - y0) / 2
    d.ellipse([x0 - lw, y0 - lw, x1 + lw, y1 + lw], fill=outline)
    if tail:
        tx, ty = tail
        dx, dy = tx - cx, ty - cy
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        r = 1.0 / math.sqrt((ux / a) ** 2 + (uy / b) ** 2)
        if dist > r * 1.05:
            base = (cx + ux * r * 0.78, cy + uy * r * 0.78)
            px, py = -uy, ux
            off = min(a, b) * 0.22
            pts = [(base[0] + px * off, base[1] + py * off),
                   (base[0] - px * off, base[1] - py * off), (tx, ty)]
            d.polygon(pts, fill=fill, outline=outline, width=int(lw))
    d.ellipse([x0, y0, x1, y1], fill=fill)


def draw_round_rect(d, rect, lw, fill, outline, radius):
    x0, y0, x1, y1 = rect
    d.rounded_rectangle([x0 - lw, y0 - lw, x1 + lw, y1 + lw], radius=radius + lw, fill=outline)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


# kind -> (글자폭비, 글자높이비, 시작크기(u 배), 최소크기(u 배))   u = 가로 픽셀
FIT = {
    "say": (0.76, 0.66, 0.047, 0.018),
    "radio": (0.88, 0.76, 0.040, 0.018),
    "nar": (0.92, 0.76, 0.034, 0.016),
    "caption": (0.92, 0.70, 0.052, 0.020),
}


def render_overlay(W, H, elems, zones, fpath, backing=False, problems=None):
    """말풍선/글자 레이어(RGBA)를 SS 배율로 그려서 W x H 로 줄여 돌려준다."""
    w, h = W * SS, H * SS
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lw = max(2, round(3.2 * W / 1080 * SS))
    u = W * SS
    if backing:
        for z in zones:
            x0, y0, x1, y1 = px_box(z["box"], w, h)
            d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) * 0.08, fill=(237, 230, 214, 236))
    min_ok = MIN_PX_1080 * W / 1080.0 * SS
    for e in elems:
        kind, text = e["kind"], e["text"]
        x0, y0, x1, y1 = px_box(e["box"], w, h)
        bw, bh = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        tail = (e["tail"][0] * w, e["tail"][1] * h) if e.get("tail") else None
        fits, size = True, 0
        if kind == "say":
            draw_ellipse_bubble(d, (x0, y0, x1, y1), tail, lw, CREAM, INK)
            fa, fb, st, mn = FIT[kind]
            font, lines, size, fits = fit_text(d, text, fpath, bw * fa, bh * fb, u * st, u * mn)
            draw_lines(d, lines, font, size, cx, cy, INK, bold=SS * 0.4)
        elif kind == "radio":
            draw_round_rect(d, (x0, y0, x1, y1), lw, CREAM, GRAY_MID, radius=bh * 0.18)
            if tail:
                tx, ty = tail
                base_x = min(max(tx, x0 + bw * 0.2), x1 - bw * 0.2)
                d.polygon([(base_x - bw * 0.03, y1 - lw), (base_x + bw * 0.03, y1 - lw), (tx, ty)], fill=GRAY_MID)
            fa, fb, st, mn = FIT[kind]
            font, lines, size, fits = fit_text(d, text, fpath, bw * fa, bh * fb, u * st, u * mn)
            draw_lines(d, lines, font, size, cx, cy, NAVY, bold=SS * 0.3)
        elif kind == "nar":
            draw_round_rect(d, (x0, y0, x1, y1), 0, NAVY, NAVY, radius=bh * 0.14)
            fa, fb, st, mn = FIT[kind]
            font, lines, size, fits = fit_text(d, text, fpath, bw * fa, bh * fb, u * st, u * mn)
            draw_lines(d, lines, font, size, cx, cy, CREAM, bold=SS * 0.25)
        elif kind == "caption":
            draw_round_rect(d, (x0, y0, x1, y1), 0, NAVY, NAVY, radius=bh * 0.10)
            d.rectangle([x0 + bw * 0.04, y0 + bh * 0.10, x0 + bw * 0.96, y0 + bh * 0.10 + max(2, SS * 3)], fill=ORANGE)
            fa, fb, st, mn = FIT[kind]
            font, lines, size, fits = fit_text(d, text, fpath, bw * fa, bh * fb, u * st, u * mn)
            draw_lines(d, lines, font, size, cx, cy + bh * 0.04, CREAM, bold=SS * 0.4)
        elif kind == "title":
            font, lines, size, fits = fit_text(d, text, fpath, bw, bh, u * 0.14, u * 0.04, single_line=True)
            draw_lines(d, lines, font, size, cx, cy, NAVY, stroke=SS * 5, stroke_fill=PAPER, bold=SS * 1.2)
        elif kind == "sub":
            font, lines, size, fits = fit_text(d, text, fpath, bw, bh, u * 0.04, u * 0.016, single_line=True)
            draw_lines(d, lines, font, size, cx, cy, NAVY, stroke=SS * 2.5, stroke_fill=PAPER, bold=SS * 0.3)
        elif kind == "sfx":
            tmp = Image.new("RGBA", (int(bw * 1.6), int(bh * 1.6)), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            font, lines, size, fits = fit_text(td, text, fpath, bw * 0.92, bh * 0.80, u * 0.16, u * 0.04, single_line=True)
            st = max(SS * 3, int(size * 0.11))
            draw_lines(td, lines, font, size, tmp.width / 2, tmp.height / 2, ORANGE, stroke=st, stroke_fill=INK, bold=SS)
            tmp = tmp.rotate(e.get("rot", 0), resample=Image.BICUBIC, expand=True)
            layer.alpha_composite(tmp, (int(cx - tmp.width / 2), int(cy - tmp.height / 2)))
        else:
            raise ValueError("알 수 없는 kind: %s" % kind)
        if problems is not None:
            if not fits:
                problems.append("'%s' 글자가 상자에 안 들어감(최소 크기에서도 넘침)" % text[:12].replace("\n", " "))
            elif kind not in ("title", "sfx") and size < min_ok:
                problems.append("'%s' 글자 높이 %.0fpx(1080 기준 %.0f) < 최소 %.0f" % (
                    text[:12].replace("\n", " "), size / SS, size / SS * 1080 / W, MIN_PX_1080))
    return layer.resize((W, H), Image.LANCZOS)


NUM_RE = re.compile(r"^(?:컷|cut|Cut|CUT|c|C)?[_\- ]?0*(\d{1,2})(?!\d)")


def find_image(folder, n):
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    hits = []
    for p in folder.iterdir():
        if p.suffix.lower() not in exts:
            continue
        m = NUM_RE.match(p.stem)
        if m and int(m.group(1)) == n:
            hits.append(p)
    if not hits:
        return None
    hits.sort(key=lambda p: p.stat().st_mtime)
    if len(hits) > 1:
        log("[경고] 컷%d 후보가 %d개: %s -> 수정 시각이 가장 최근인 %s 사용" % (
            n, len(hits), ", ".join(p.name for p in hits), hits[-1].name))
    return hits[-1]


def make_placeholder(W, H, cut, fpath):
    img = Image.new("RGB", (W, H), "#B9B9B9")
    d = ImageDraw.Draw(img)
    for i in range(-H, W, int(W / 12)):
        d.line([(i, 0), (i + H, H)], fill="#AEAEAE", width=max(1, W // 540))
    big = get_font(fpath, int(W * 0.07))
    mid = get_font(fpath, int(W * 0.028))
    d.text((W / 2, H * 0.47), "CUT %02d" % cut["no"], font=big, fill="#6A6A6A", anchor="mm")
    d.text((W / 2, H * 0.53), "이미지 자리표시", font=mid, fill="#6A6A6A", anchor="mm")
    font, lines, size, _ = fit_text(d, cut.get("label", ""), fpath, W * 0.84, H * 0.08, W * 0.026, W * 0.014)
    draw_lines(d, lines, font, size, W / 2, H * 0.60, "#5A5A5A")
    return img


def stamp(img, fpath, text, color=(200, 40, 40, 150)):
    W, H = img.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = get_font(fpath, int(W * 0.13))
    d.text((W / 2, H / 2), text, font=f, fill=color, anchor="mm")
    layer = layer.rotate(25, resample=Image.BICUBIC)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def draw_zones(img, cut, fpath):
    W, H = img.size
    d = ImageDraw.Draw(img, "RGBA")
    f = get_font(fpath, max(10, int(W * 0.016)))
    for z in cut.get("zones", []):
        x0, y0, x1, y1 = px_box(z["box"], W, H)
        d.rectangle([x0, y0, x1, y1], outline=(200, 40, 40, 200), width=max(1, W // 540))
        d.text((x0 + 4, y0 + 2), z["id"], font=f, fill=(200, 40, 40, 255), anchor="la")


def crop_45(img, anchor):
    w, h = img.size
    target = 4 / 5
    cur = w / h
    if abs(cur - target) < 0.004:
        return img
    if cur > target:
        nw = int(round(h * target))
        left = int(round((w - nw) * 0.5))
        return img.crop((left, 0, left + nw, h))
    nh = int(round(w / target))
    top = int(round((h - nh) * anchor))
    return img.crop((0, top, w, top + nh))


def inside(inner, outer, tol=0.004):
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox - tol and iy >= oy - tol and ix + iw <= ox + ow + tol and iy + ih <= oy + oh + tol


def check_zones(cut):
    bad = 0
    zmap = {z["id"]: z["box"] for z in cut.get("zones", [])}
    for e in cut["elements"]:
        zid = e.get("zone")
        if zid not in zmap or not inside(e["box"], zmap[zid]):
            log("[경고] 컷%d '%s' 말풍선이 구역 %s 밖으로 나갑니다." % (cut["no"], e["text"][:12].replace("\n", " "), zid))
            bad += 1
    return bad


def select_cuts(data, six, only):
    cuts = data["cuts"]
    if six:
        keep = data.get("six_cuts", [1, 3, 4, 6, 7, 8])
        cuts = [c for c in cuts if c["no"] in keep]
    if only:
        cuts = [c for c in cuts if c["no"] in only]
    return cuts


def apply_six_override(cut):
    ov = cut.get("six_override") or {}
    if not ov:
        return cut["elements"]
    out = []
    for e in cut["elements"]:
        e2 = dict(e)
        e2["text"] = ov.get(e["text"], e["text"])
        out.append(e2)
    return out


def verify_outputs(files, count_expected, W, H, fmt):
    ok = True
    log("")
    log("제출본 검증")
    if len(files) != count_expected:
        log("  [실패] 파일 %d개 (기대 %d개)" % (len(files), count_expected))
        ok = False
    total = 0
    for p in files:
        with Image.open(p) as im:
            w, h = im.size
            f = im.format
        sz = p.stat().st_size
        total += sz
        good = (w * 5 == h * 4) and w >= 1080 and h >= 1350 and f == ("JPEG" if fmt == "jpg" else "PNG")
        bad_name = any(t in p.name for t in ("점검", "시험", "원본", "SAMPLE"))
        log("  %s %dx%d %s %.2fMB%s" % ("OK  " if good and not bad_name else "[실패]", w, h, f, sz / 1048576,
                                       "  (파일명에 시험/점검 표시)" if bad_name else ""))
        ok = ok and good and not bad_name
    log("  합계 %.2f MB (이메일 용량 제한은 공고에 없음: 문의로 확인 필요)" % (total / 1048576))
    return ok


def main():
    ap = argparse.ArgumentParser(description="컷툰 말풍선/대사 합성기")
    ap.add_argument("--images", help="컷 이미지 폴더")
    ap.add_argument("--cuts", help="cuts.json 경로(기본: 이 파일 옆)")
    ap.add_argument("--out", default=None, help="출력 폴더(기본: 모드에 따라 출력_제출/출력_점검/출력_시험/출력_원본)")
    ap.add_argument("--name", default=None, help="파일명에 넣을 지원자 이름(제출본에는 필수)")
    ap.add_argument("--field", default=None, help="파일명의 [지원분야] (기본: cuts.json 의 'AI 컷툰', 공고 표기)")
    ap.add_argument("--title", default=None, help="파일명의 [작품제목] (기본: cuts.json 의 제목)")
    ap.add_argument("--width", type=int, default=1440, help="출력 가로 px (세로는 5/4배, 최소 1080)")
    ap.add_argument("--format", choices=["jpg", "png"], default="jpg")
    ap.add_argument("--quality", type=int, default=95)
    ap.add_argument("--crop-anchor", type=float, default=0.5, help="세로로 긴 원본을 자를 때 위치(0=위, 0.5=가운데, 1=아래)")
    ap.add_argument("--font", default=None, help="글꼴 경로 (기본 SCDream5.otf)")
    ap.add_argument("--allow-fallback-font", action="store_true", help="SCDream5.otf 가 없을 때 맑은 고딕으로 대체 허용(제출본 비권장)")
    ap.add_argument("--show-zones", action="store_true", help="점검본: 구역선 표시(제출 금지)")
    ap.add_argument("--preview", action="store_true", help="시험본: 이미지가 없으면 자리표시로 대체(제출 금지)")
    ap.add_argument("--no-text", action="store_true", help="글자 없이 크롭/리사이즈만(원본 보관용)")
    ap.add_argument("--backing", action="store_true", help="구역마다 종이색 판을 깔아 가독성 확보")
    ap.add_argument("--six", action="store_true", help="6컷 압축안(컷 1,3,4,6,7,8)")
    ap.add_argument("--only", default="", help="일부 컷만 처리, 예: 1,3,8 (제출본에서는 쓸 수 없음)")
    ap.add_argument("--zip", action="store_true", help="제출본을 zip 으로도 묶음")
    ap.add_argument("--overwrite", action="store_true", help="출력 폴더가 비어 있지 않아도 같은 이름 파일을 덮어씀")
    ap.add_argument("--sheet", action="store_true", help="전체 컷 한눈에 보기 이미지 추가(제출 파일이 아님)")
    ap.add_argument("--lint", action="store_true", help="구역·글자 크기 검사만 하고 종료")
    args = ap.parse_args()

    data = load_data(args.cuts)
    field = args.field or data.get("field", "AI 컷툰")
    title = args.title or data.get("title", "작품")
    only = {int(x) for x in args.only.split(",") if x.strip().isdigit()}

    if args.width < 1080:
        log("[오류] 공고 최소 규격(1080x1350)보다 작습니다. --width 1080 이상으로 지정하세요.")
        return 1
    W = args.width
    H = int(round(W * 5 / 4))

    submit = not (args.show_zones or args.preview or args.no_text)
    if submit and only:
        log("[오류] 제출본은 --only 로 일부만 만들 수 없습니다. 점검용이면 --show-zones 나 --preview 와 함께 쓰세요.")
        return 1
    if submit and not args.lint:
        if not args.images:
            log("[오류] 제출본에는 --images 폴더가 필요합니다. 레이아웃만 보려면 --preview 를 쓰세요.")
            return 1
        if not args.name:
            log("[오류] 제출본에는 --name [지원자 이름] 이 필요합니다(파일명에 들어갑니다).")
            return 1
    prefix, outname = ("", "출력_제출")
    if args.show_zones:
        prefix, outname = "점검_", "출력_점검"
    elif args.preview:
        prefix, outname = "시험_", "출력_시험"
    elif args.no_text:
        prefix, outname = "원본_", "출력_원본"

    fpath = resolve_font(args.font, args.allow_fallback_font or not submit)
    cuts = select_cuts(data, args.six, only)

    # ---- lint (글 상자 크기 포함)
    probs_total = 0
    for cut in cuts:
        probs_total += check_zones(cut)
        pr = []
        render_overlay(W, H, apply_six_override(cut) if args.six else cut["elements"], cut.get("zones", []), fpath, False, pr)
        for t in pr:
            log("[경고] 컷%d %s" % (cut["no"], t))
        probs_total += len(pr)
    if args.lint:
        log("lint %s (문제 %d건)" % ("통과" if probs_total == 0 else "실패", probs_total))
        return 0 if probs_total == 0 else 1
    if submit and probs_total:
        log("[오류] 구역·글자 크기 문제가 %d건 있어 제출본을 만들지 않습니다. cuts.json(07 스크립트)을 고치세요." % probs_total)
        return 2

    folder = Path(args.images) if args.images else None
    if folder and not folder.is_dir():
        log("[오류] 이미지 폴더가 없습니다: %s" % folder)
        return 1

    # ---- 이미지 확보(제출본·점검본은 전부 있어야 한다)
    sources = {}
    missing = []
    for cut in cuts:
        src = find_image(folder, cut["no"]) if folder else None
        if src is None:
            missing.append(cut["no"])
        sources[cut["no"]] = src
    if missing and not args.preview:
        log("[오류] 이미지가 없는 컷: %s. 아무 파일도 만들지 않습니다. (레이아웃만 시험하려면 --preview)" % ",".join(map(str, missing)))
        return 2

    out = Path(args.out or outname)
    if out.exists() and any(out.iterdir()) and not args.overwrite:
        log("[오류] 출력 폴더 %s 가 비어 있지 않습니다. 비우거나 --out 으로 다른 폴더를 주거나 --overwrite 를 쓰세요(예전 결과물이 섞이는 것을 막기 위함)." % out)
        return 1
    out.mkdir(parents=True, exist_ok=True)

    nm = args.name or "이름"
    done, thumbs = [], []
    for seq, cut in enumerate(cuts, 1):
        n = cut["no"]
        src = sources[n]
        elems = apply_six_override(cut) if args.six else cut["elements"]
        if src is None:
            img = make_placeholder(W, H, cut, fpath)
            log("컷%02d: 이미지 없음 -> 자리표시(시험본)" % n)
        else:
            raw = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
            ratio = raw.width / raw.height
            if not (abs(ratio - 4 / 5) < 0.02 or abs(ratio - 2 / 3) < 0.02):
                log("[경고] 컷%02d 원본 비율 %.3f (4:5=0.8, 2:3=0.667 아님): 가운데 기준으로 잘립니다. 중요 요소가 잘리는지 확인하세요." % (n, ratio))
            img = crop_45(raw, args.crop_anchor)
            if img.width < W or img.height < H:
                log("컷%02d: 원본 %dx%d (크롭 후 %dx%d) -> %dx%d 로 확대 (업스케일 권장)" % (n, raw.width, raw.height, img.width, img.height, W, H))
            img = img.resize((W, H), Image.LANCZOS)
            log("컷%02d: %s" % (n, src.name))
        if not args.no_text:
            if args.show_zones or src is None:
                draw_zones(img, cut, fpath)
            overlay = render_overlay(W, H, elems, cut.get("zones", []), fpath, args.backing)
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        if args.show_zones:
            img = stamp(img, fpath, "점검본 제출금지")
        if src is None:
            img = stamp(img, fpath, "SAMPLE", (60, 60, 60, 120))
        num = seq if args.six else n
        fname = "%s%s_%s_%s_%02d.%s" % (prefix, field, title, nm, num, args.format)
        dest = out / fname
        if args.format == "jpg":
            img.save(dest, "JPEG", quality=args.quality, subsampling=0, optimize=True)
        else:
            img.save(dest, "PNG", optimize=True)
        done.append(dest)
        thumbs.append(img.copy())

    if args.sheet and thumbs:
        tw = 540
        th = int(tw * 5 / 4)
        cols = 4
        rows = int(math.ceil(len(thumbs) / cols))
        sheet = Image.new("RGB", (cols * tw + (cols + 1) * 16, rows * th + (rows + 1) * 16), PAPER)
        for i, t in enumerate(thumbs):
            r, c = divmod(i, cols)
            sheet.paste(t.resize((tw, th), Image.LANCZOS), (16 + c * (tw + 16), 16 + r * (th + 16)))
        pdir = out.parent / (out.name + "_미리보기")
        pdir.mkdir(parents=True, exist_ok=True)
        sp = pdir / "미리보기_제출아님_전체컷.jpg"
        sheet.save(sp, "JPEG", quality=90)
        log("미리보기(제출 파일 아님): %s" % sp)

    log("")
    log("출력 %d장 -> %s  (%dx%d, 4:5, %s)" % (len(done), out.resolve(), W, H, args.format.upper()))
    rc = 0
    if submit:
        ok = verify_outputs(done, len(cuts), W, H, args.format)
        if not ok:
            log("[실패] 제출본 검증에 실패했습니다. 위 항목을 고치고 다시 만드세요.")
            return 3
        if args.zip:
            zdir = out.parent / (out.name + "_zip")
            zdir.mkdir(parents=True, exist_ok=True)
            zp = zdir / ("%s_%s_%s.zip" % (field, title, nm))
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
                for p in done:
                    z.write(p, p.name)
            log("zip: %s" % zp)
        log("검증 통과. 그래도 제출 전에 8장을 눈으로 한 장씩 열어 보세요(글자 잘림, 말풍선이 호랑이 얼굴을 가리는지).")
    else:
        log("[알림] 이 결과물은 제출본이 아닙니다(%s). 제출용은 폴더 출력_제출 의 파일만 씁니다." % (prefix.rstrip("_") or "원본"))
        if args.show_zones:
            log("[주의] 점검본에는 빨간 구역선과 '점검본 제출금지' 표시가 들어 있습니다.")
        if missing:
            log("[알림] 자리표시로 대체된 컷: %s" % ",".join(map(str, missing)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
