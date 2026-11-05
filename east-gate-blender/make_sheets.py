#!/usr/bin/env python3
"""把各施工階段算圖排成對照表（phases_sheet.jpg）與建造動畫（build.gif）。

用法：python make_sheets.py out
需要 Pillow；中文標籤使用系統的文泉驛正黑（找不到時退回預設字型）。
"""
import csv
import os
import sys

from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1] if len(sys.argv) > 1 else 'out'
R = os.path.join(out, 'renders')
phases = list(csv.DictReader(open(os.path.join(out, 'phases.csv'), encoding='utf-8-sig')))
imgs = [Image.open(os.path.join(R, 'phase_%02d.jpg' % (i + 1))).convert('RGB') for i in range(len(phases))]

FONT = None
for path in ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'):
    if os.path.exists(path):
        FONT = path
        break


def font(size):
    return ImageFont.truetype(FONT, size) if FONT else ImageFont.load_default()


def label(im, p, big=26, small=18):
    d = ImageDraw.Draw(im, 'RGBA')
    w = im.width
    d.rectangle([0, 0, w, 74], fill=(20, 18, 16, 170))
    d.text((18, 10), '第 %s 階段　%s' % (p['階段編號'], p['階段']), font=font(big), fill=(255, 255, 255))
    d.text((18, 44), '步驟 %s–%s（%s 步）' % (format(int(p['起']), ','), format(int(p['迄']), ','), format(int(p['步數']), ',')),
           font=font(small), fill=(235, 220, 190))
    return im


tw, th = 640, 427
cols = 4
rows = (len(imgs) + cols - 1) // cols
pad = 10
sheet = Image.new('RGB', (cols * tw + (cols + 1) * pad, rows * th + (rows + 1) * pad), (238, 233, 224))
for i, (im, p) in enumerate(zip(imgs, phases)):
    t = label(im.resize((tw, th), Image.LANCZOS), p, 22, 15)
    sheet.paste(t, (pad + (i % cols) * (tw + pad), pad + (i // cols) * (th + pad)))
sheet.save(os.path.join(R, 'phases_sheet.jpg'), quality=88)

frames = [label(im.resize((720, 480), Image.LANCZOS), p) for im, p in zip(imgs, phases)]
durations = [900] * (len(frames) - 1) + [2600]
frames[0].save(os.path.join(R, 'build.gif'), save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
print('wrote phases_sheet.jpg and build.gif')
