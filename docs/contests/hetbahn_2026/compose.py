"""햇반 30주년 AI 공모전 출품 이미지 마무리 도구.

공식 로고 PNG(주최 측 구글 드라이브의 1080x1350 또는 1080x1080 투명 PNG)를 그대로 얹는다.
로고를 AI로 만들거나 고치지 않기 위해서다(공모전 유의사항: 로고를 AI 생성·임의 변경하면 제외).

사용 예 (PowerShell, 이 파일이 있는 폴더에서):
  python compose.py fit 원본.png 햇반30주년_로고가이드_이미지_4x5_red-red.png 1장.png
  python compose.py fit 원본.png 로고.png 4장.png --text "김이 걷히면 사라지는, 한 끼 분량의 편지" --note
  python compose.py grid a.png b.png c.png d.png 3장_바탕.png --cols 2
  python compose.py grid 절기01.png ... 절기24.png 1장_바탕.png --cols 6
  (grid 결과에는 로고가 없다. 그 결과를 다시 fit에 넣어 로고를 얹는다.)

필요: pip install pillow
"""
import argparse
import sys

from PIL import Image, ImageDraw, ImageFont, ImageStat

FONT_DEFAULT = r"C:\Users\user\S-Core_Dream_OTF\SCDream5.otf"
NOTE_TEXT = "※ 공모전을 위해 상상한 콘셉트이며 실제 제품이 아닙니다."
LOGO_ZONE = (0.03, 0.02, 0.25, 0.11)  # 로고가 놓이는 왼쪽 위 영역(가로·세로 비율)


def crop_to(img, w, h):
    """가운데를 기준으로 w:h 비율로 자른 뒤 w x h로 맞춘다."""
    src_w, src_h = img.size
    target = w / h
    if src_w / src_h > target:
        new_w = round(src_h * target)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = round(src_w / target)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    if img.size[0] < w:
        print(f"주의: 원본이 {img.size[0]}px라 {w}px로 늘립니다. 업스케일 후 다시 넣는 편이 좋습니다.")
    return img.resize((w, h), Image.LANCZOS)


def check_logo_zone(img):
    w, h = img.size
    box = tuple(round(v) for v in (LOGO_ZONE[0] * w, LOGO_ZONE[1] * h, LOGO_ZONE[2] * w, LOGO_ZONE[3] * h))
    stat = ImageStat.Stat(img.crop(box).convert("L"))
    mean, std = stat.mean[0], stat.stddev[0]
    print(f"로고 자리 밝기 평균 {mean:.0f}/255, 얼룩 정도 {std:.0f}")
    if std > 45:
        print("주의: 로고 자리 배경이 복잡합니다. 그 자리를 단순한 벽·하늘 등으로 다시 만드세요.")
    if mean < 90:
        print("참고: 배경이 어둡습니다. red-red와 red-white 두 파일을 다 얹어 보고 잘 보이는 쪽을 고르세요.")


def wrap(draw, text, font, max_w):
    lines, line = [], ""
    for ch in text:
        trial = line + ch
        if draw.textlength(trial, font=font) > max_w and line:
            cut = line.rfind(" ")
            if cut > 0:
                lines.append(line[:cut])
                line = line[cut + 1:] + ch
            else:
                lines.append(line)
                line = ch
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def add_text(img, text, font_path):
    w, h = img.size
    size = round(w / 22)
    font = ImageFont.truetype(font_path, size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    lines = wrap(draw, text, font, w * 0.84)
    line_h = round(size * 1.5)
    band_h = line_h * len(lines) + size * 2
    draw.rectangle((0, h - band_h - round(h * 0.04), w, h - round(h * 0.04)), fill=(0, 0, 0, 120))
    y = h - band_h - round(h * 0.04) + size
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        draw.text(((w - tw) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += line_h
    return Image.alpha_composite(img, layer)


def add_note(img, font_path):
    w, h = img.size
    font = ImageFont.truetype(font_path, round(w / 54))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    tw = draw.textlength(NOTE_TEXT, font=font)
    x, y = w - tw - round(w * 0.03), h - round(h * 0.03) - font.size
    draw.text((x + 1, y + 1), NOTE_TEXT, font=font, fill=(0, 0, 0, 140))
    draw.text((x, y), NOTE_TEXT, font=font, fill=(255, 255, 255, 230))
    return Image.alpha_composite(img, layer)


def cmd_fit(a):
    logo = Image.open(a.logo).convert("RGBA")
    w, h = logo.size
    if (w, h) not in ((1080, 1350), (1080, 1080)):
        sys.exit(f"로고 파일 크기가 {w}x{h}입니다. 주최 측 이미지용 로고 PNG(1080x1350 또는 1080x1080)를 넣으세요.")
    img = crop_to(Image.open(a.src).convert("RGB"), w, h)
    check_logo_zone(img)
    img = img.convert("RGBA")
    if a.text:
        img = add_text(img, a.text, a.font)
    if a.note:
        img = add_note(img, a.font)
    img = Image.alpha_composite(img, logo)
    img.convert("RGB").save(a.out)
    print(f"저장: {a.out} ({w}x{h})")


def cmd_grid(a):
    w, h = a.size
    cols = a.cols
    rows = -(-len(a.srcs) // cols)
    cell_w = (w - a.gap * (cols + 1)) // cols
    cell_h = (h - a.top - a.gap * (rows + 1)) // rows
    canvas = Image.new("RGB", (w, h), a.bg)
    for i, path in enumerate(a.srcs):
        r, c = divmod(i, cols)
        tile = crop_to(Image.open(path).convert("RGB"), cell_w, cell_h)
        canvas.paste(tile, (a.gap + c * (cell_w + a.gap), a.top + a.gap + r * (cell_h + a.gap)))
    canvas.save(a.out)
    print(f"저장: {a.out} ({cols}x{rows} 칸, 칸 {cell_w}x{cell_h})")


def main():
    p = argparse.ArgumentParser(description="햇반 공모전 이미지 마무리")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fit", help="비율 맞춤 + 공식 로고 얹기")
    f.add_argument("src")
    f.add_argument("logo")
    f.add_argument("out")
    f.add_argument("--text", help="아래쪽에 넣을 한글 문구")
    f.add_argument("--note", action="store_true", help="'실제 제품이 아닙니다' 작은 안내 넣기")
    f.add_argument("--font", default=FONT_DEFAULT)
    f.set_defaults(func=cmd_fit)

    g = sub.add_parser("grid", help="여러 장을 한 장에 칸으로 배치(로고 없음)")
    g.add_argument("srcs", nargs="+")
    g.add_argument("out")
    g.add_argument("--cols", type=int, default=2)
    g.add_argument("--size", type=int, nargs=2, default=(1080, 1350))
    g.add_argument("--gap", type=int, default=12)
    g.add_argument("--top", type=int, default=160, help="위쪽 비울 높이(로고 자리)")
    g.add_argument("--bg", default="#f4efe6")
    g.set_defaults(func=cmd_grid)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
