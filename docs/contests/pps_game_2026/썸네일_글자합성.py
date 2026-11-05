# -*- coding: utf-8 -*-
"""
ChatGPT가 만든 글자 없는 썸네일 이미지 위에 한글 제목을 따로 얹는다. (이미지 AI에는 글자를 맡기지 않는다.)

사용법 (PowerShell):
  python 썸네일_글자합성.py 원본.png 결과.png --font "글꼴파일.ttf"

- 입력: ChatGPT 이미지 1536x1024(3:2). 위아래 80픽셀씩 잘라 1536x864(16:9)로 만든 뒤 1920x1080으로 키운다.
- 글꼴은 상업 이용을 직접 확인한 것만 쓴다. 이 스크립트는 특정 글꼴의 라이선스를 확인하지 않는다.
- 글자 위치와 크기는 02 문서 7번의 '글자 합성 사양'과 같다.
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageFilter

TITLE = "미리도착한하루"
SUB = "문질러서 색을 되돌려 주세요"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--font", required=True, help="한글 글꼴 파일(.ttf/.otf) 경로")
    a = ap.parse_args()

    im = Image.open(a.src).convert("RGB")
    if im.size != (1536, 1024):
        print("경고: 입력이 1536x1024가 아니다:", im.size, "- 비율이 3:2가 아니면 위치가 어긋난다.")
    w, h = im.size
    crop_px = int(round(h * 80 / 1024))
    im = im.crop((0, crop_px, w, h - crop_px))               # 3:2 -> 16:9
    im = im.resize((1920, 1080), Image.LANCZOS)
    W, H = im.size

    title_font = ImageFont.truetype(a.font, int(H * 0.075))   # 글자 높이 약 7.5%
    sub_font = ImageFont.truetype(a.font, int(H * 0.034))     # 약 3.4%

    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    def centered(draw, text, font, cy, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (W - tw) / 2 - bbox[0]
        y = cy - th / 2 - bbox[1]
        draw.text((x, y), text, font=font, fill=fill)
    centered(sd, TITLE, title_font, H * 0.135 + 4, (0, 0, 0, 150))
    centered(sd, SUB, sub_font, H * 0.225 + 3, (0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    im = Image.alpha_composite(im.convert("RGBA"), shadow)

    d = ImageDraw.Draw(im)
    centered(d, TITLE, title_font, H * 0.135, (255, 246, 224, 255))    # #FFF6E0
    centered(d, SUB, sub_font, H * 0.225, (244, 217, 139, 255))        # #F4D98B
    im.convert("RGB").save(a.dst)
    print("저장:", a.dst, im.size)

if __name__ == "__main__":
    main()
