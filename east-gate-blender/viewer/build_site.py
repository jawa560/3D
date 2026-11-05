#!/usr/bin/env python3
"""組合展示頁：把統計與階段資料填入範本，並收集算圖、GLB 與 Draco 解碼器。

用法：python build_site.py <out 目錄> <參考照片> <three 套件目錄> <輸出目錄>
"""
import csv
import json
import os
import shutil
import sys

out, ref, three_pkg, site = sys.argv[1:5]
here = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(site, 'draco'), exist_ok=True)

phases = list(csv.DictReader(open(os.path.join(out, 'phases.csv'), encoding='utf-8-sig')))
steps = list(csv.DictReader(open(os.path.join(out, 'steps.csv'), encoding='utf-8-sig')))
data = [{'name': p['階段'], 'from': int(p['起']), 'to': int(p['迄']), 'count': int(p['步數']), 'note': p['說明']} for p in phases]
tiles = sum(1 for s in steps if '筒瓦' in s['說明'])
stones = sum(1 for s in steps if '砂岩條石' in s['說明'])

html = open(os.path.join(here, 'index.template.html'), encoding='utf-8').read()
html = (html.replace('/*PHASES*/[]', json.dumps(data, ensure_ascii=False))
            .replace('/*TOTAL*/', format(len(steps), ','))
            .replace('/*TILES*/', format(tiles, ','))
            .replace('/*STONES*/', format(stones, ',')))
open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(html)

R = os.path.join(out, 'renders')
for f in ['photo_angle.jpg', 'aerial.jpg', 'roof_corner.jpg'] + ['phase_%02d.jpg' % (i + 1) for i in range(len(phases))]:
    shutil.copy(os.path.join(R, f), os.path.join(site, f))
shutil.copy(ref, os.path.join(site, 'reference.jpg'))
shutil.copy(os.path.join(out, 'east_gate.glb'), os.path.join(site, 'east_gate.glb'))
import base64
with open(os.path.join(out, 'east_gate.glb'), 'rb') as fh:
    b64 = base64.b64encode(fh.read()).decode('ascii')
with open(os.path.join(site, 'model.js'), 'w') as fh:
    fh.write('window.GATE_GLB_B64="%s";\n' % b64)
shutil.copy(os.path.join(three_pkg, 'examples/js/libs/draco/draco_decoder.js'), os.path.join(site, 'draco', 'draco_decoder.js'))
print('site ready: %d steps, %d tiles, %d stones' % (len(steps), tiles, stones))
