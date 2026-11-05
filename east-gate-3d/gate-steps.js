/*
 * 迎曦門（新竹東門城）程序化 3D 模型 — 一萬步建造清單產生器
 *
 * 同一份程式碼在 Node.js（匯出 CSV）與瀏覽器（Three.js 渲染）共用。
 * build() 會回傳恰好 10,000 個構件，每個構件就是一個建造步驟，
 * 依施工順序排列：石造台座 → 拱道穹窿 → … → 廣場鋪面。
 *
 * 座標系：y 向上，x 為城門長軸（左右），z 為穿越拱門的方向（前後）。單位：公尺。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.GateModel = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var TOTAL = 10000;

  // ---- 共用數值 ---------------------------------------------------------
  var PL = 22, PW = 11;            // 台座長、寬
  var BL = 1.0, BH = 0.44, BD = 0.5, NC = 16; // 砂岩塊：長、高、厚、層數
  var PH = NC * BH;                // 台座高 7.04
  var AW = 2.8, SP = 2.2, AR = 2.8; // 拱道半寬、起拱高、拱半徑（拱頂 5.0，依照片拱寬約為台座寬 0.27 倍）
  var FY = PH + 0.15;              // 台座頂面鋪石完成面
  var CL = 17, CW = 8.4;           // 下層柱列範圍
  var COL_H = 2.4;
  var CT = FY + 0.3 + COL_H;       // 下層柱頂 10.29
  var EY = CT + 1.2;               // 下層簷口高
  var D1 = 2.1;                    // 下層屋面落差
  var UL = 11, UW = 5.4;           // 上層樓身範圍
  var UY = EY + D1 - 0.24;         // 上層樓身底
  var UH = 1.7;
  var UCT = UY + UH;               // 上層柱頂
  var UEY = UCT + 1.15;            // 上層簷口高
  var D2 = 2.6;

  var PHASES = [
    { name: '石造台座', en: 'Stone podium', note: '以砂岩塊逐層砌築 16 層城台，正面與背面於拱門處改砌拱券石。' },
    { name: '拱道穹窿', en: 'Arch vault', note: '拱道兩側砌牆至起拱線，再以 22 道石環砌成半圓筒形穹窿。' },
    { name: '台座頂面', en: 'Platform slabs', note: '城台頂面鋪設大型石板，作為樓閣基礎。' },
    { name: '白色腰線', en: 'White string course', note: '沿台座頂緣安裝白色水泥腰線，分隔石砌與磚砌部分。' },
    { name: '白色女牆', en: 'Plastered parapet', note: '以磚砌築女牆 5 層並粉刷白灰，頂部安裝壓頂，形成照片中台座上方的白色厚帶。' },
    { name: '下層立柱', en: 'Lower columns', note: '安放柱礎後立起 18 根周邊朱紅木柱與 4 根內柱。' },
    { name: '下層樑枋斗栱', en: 'Lower beams & brackets', note: '架設額枋、藍彩樑枋，於柱頭與補間安裝斗栱。' },
    { name: '下層欄杆', en: 'Lower balustrade', note: '於各柱間安裝上下橫桿與直櫺欄杆。' },
    { name: '下層屋頂', en: 'Lower roof', note: '釘椽、封簷板，自簷口往上逐排鋪瓦，最後安垂脊。' },
    { name: '上層樓身', en: 'Upper storey', note: '立上層柱、砌紅牆板、安窗櫺與匾額，架樑枋斗栱。' },
    { name: '上層屋頂', en: 'Upper roof', note: '鋪設上層歇山屋面，安正脊、垂脊與燕尾脊飾。' },
    { name: '廣場設施', en: 'Plaza fixtures', note: '環繞城門安置石柱鏈欄、長椅，並栽植棕櫚。' },
    { name: '廣場鋪面', en: 'Plaza paving', note: '自城台向外一圈圈鋪設廣場石板，直到第 10,000 步完工。' }
  ];

  // ---- 工具 -----------------------------------------------------------
  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }

  var C = {
    sand: 0xcfbb90, sandDark: 0xb9a67c, slab: 0xbbb09a, white: 0xf1ede2,
    brick: 0xa84a30, red: 0xb3261e, base: 0x8d8576, blue: 0x2f5aa8, teal: 0x2e8b8b,
    rail: 0x8a2b1f, tile: 0xd4551c, tileRound: 0xc24a16, rafter: 0xc0402a, fascia: 0x2a4f9b,
    ridge: 0x25407c, hip: 0x2c4a8f, plaster: 0xebe5d6, coping: 0xd6cfbf, lantern: 0xf3efe4, cap: 0x2b2522, gold: 0xd9a521, wall: 0xa8281f, window: 0x2a1e1a,
    bollard: 0xcabca0, chain: 0x5f6268, trunk: 0x8a6a4a, frond: 0x3f8f3a, bench: 0xb9a98b,
    paveA: 0x9d9c95, paveB: 0x8e8d86
  };

  function build() {
    var els = [];
    var rand = mulberry32(20261104);
    var phase = 0;

    function jitter(hex, amt) {
      var f = 1 + (rand() * 2 - 1) * amt;
      var r = clamp(Math.round(((hex >> 16) & 255) * f), 0, 255);
      var g = clamp(Math.round(((hex >> 8) & 255) * f), 0, 255);
      var b = clamp(Math.round((hex & 255) * f), 0, 255);
      return (r << 16) | (g << 8) | b;
    }
    // g: 0 box, 1 cylinder, 2 sphere, 3 plaque（匾額，瀏覽器以文字貼圖呈現）
    function add(g, x, y, z, sx, sy, sz, c, d, rot) {
      els.push({ g: g, x: x, y: y, z: z, sx: sx, sy: sy, sz: sz,
        rx: rot ? rot[0] : 0, ry: rot ? rot[1] : 0, rz: rot ? rot[2] : 0,
        c: c, ph: phase, d: d });
    }
    function box(x, y, z, sx, sy, sz, c, d, rot) { add(0, x, y, z, sx, sy, sz, c, d, rot); }
    function cyl(x, y, z, dia, h, c, d, rot) { add(1, x, y, z, dia, h, dia, c, d, rot); }
    function sph(x, y, z, dia, c, d) { add(2, x, y, z, dia, dia, dia, c, d); }
    // 以兩端點定義的長條（箱體 x 軸沿方向），t1 = 高(y)、t2 = 厚(z)
    function bar(a, b, t1, t2, c, d) {
      var dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      var len = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (len < 1e-6) return;
      var flip = dx < -1e-6 || (Math.abs(dx) <= 1e-6 && dz < 0);
      if (flip) { dx = -dx; dy = -dy; dz = -dz; }
      els.push({ g: 0, x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2, z: (a[2] + b[2]) / 2,
        sx: len, sy: t1, sz: t2, dir: [dx / len, dy / len, dz / len], c: c, ph: phase, d: d });
    }
    function zh(n) { return String(n); }

    // ==== 1. 石造台座 ==================================================
    phase = 0;
    function openHalf(y) {
      if (y < SP) return AW;
      var d = y - SP;
      if (d >= AR) return 0;
      return Math.sqrt(AR * AR - d * d);
    }
    function course(len, c, cb) {
      var off = (c % 2) * BL / 2;
      var s = -len / 2 + off - BL;
      var i = 0;
      for (var a = s; a < len / 2; a += BL) {
        var xa = Math.max(a, -len / 2), xb = Math.min(a + BL, len / 2);
        if (xb - xa > 0.15) cb(xa, xb, ++i);
      }
    }
    var faceNames = ['正面', '背面'];
    for (var c = 0; c < NC; c++) {
      var yc = c * BH + BH / 2;
      var w = openHalf(c * BH);
      for (var f = 0; f < 2; f++) {
        var face = f === 0 ? 1 : -1;
        var zf = face * (PW / 2 - BD / 2);
        course(PL, c, function (xa, xb, i) {
          var parts = [];
          if (w > 0 && xa < w && xb > -w) {
            if (-w - xa > 0.15) parts.push([xa, -w]);
            if (xb - w > 0.15) parts.push([w, xb]);
          } else parts.push([xa, xb]);
          for (var p = 0; p < parts.length; p++) {
            var L = parts[p][1] - parts[p][0];
            box((parts[p][0] + parts[p][1]) / 2, yc, zf, L - 0.03, BH - 0.03, BD,
              jitter(C.sand, 0.07), '砌築城台第 ' + (c + 1) + ' 層砂岩，' + faceNames[f] + '第 ' + i + ' 塊');
          }
        });
      }
      for (var sgn = -1; sgn <= 1; sgn += 2) {
        var xs = sgn * (PL / 2 - BD / 2);
        course(PW - 2 * BD, c, function (za, zb, i) {
          var L = zb - za;
          box(xs, yc, (za + zb) / 2, BD, BH - 0.03, L - 0.03,
            jitter(C.sand, 0.07), '砌築城台第 ' + (c + 1) + ' 層砂岩，' + (sgn > 0 ? '右側' : '左側') + '第 ' + i + ' 塊');
        });
      }
    }
    for (var f2 = 0; f2 < 2; f2++) {
      var faceZ = (f2 === 0 ? 1 : -1) * (PW / 2 - BD / 2);
      var nV = 15;
      for (var i = 0; i < nV; i++) {
        var a = Math.PI * (i + 0.5) / nV;
        var r = AR + 0.32;
        var key = i === (nV - 1) / 2;
        box(r * Math.cos(a), SP + r * Math.sin(a), faceZ, key ? 0.76 : 0.64, key ? 0.56 : 0.46, BD + 0.12,
          jitter(C.sandDark, 0.05), (key ? '安放' + faceNames[f2] + '拱門拱心石' : '砌築' + faceNames[f2] + '拱券石第 ' + (i + 1) + ' 塊'),
          [0, 0, a]);
      }
    }

    // ==== 2. 拱道穹窿 ==================================================
    phase = 1;
    for (var c2 = 0; c2 < Math.round(SP / BH); c2++) {
      var y2 = c2 * BH + BH / 2;
      for (var sg = -1; sg <= 1; sg += 2) {
        var xw = sg * (AW - 0.2);
        course(PW - 0.6, c2, function (za, zb, i) {
          box(xw, y2, (za + zb) / 2, 0.4, BH - 0.03, zb - za - 0.03,
            jitter(C.sandDark, 0.06), '砌築拱道' + (sg > 0 ? '右' : '左') + '側牆第 ' + (c2 + 1) + ' 層第 ' + i + ' 塊');
        });
      }
    }
    var nRings = 22, ringStep = (PW - 0.5) / nRings;
    for (var k = 0; k < nRings; k++) {
      var zr = -PW / 2 + 0.25 + ringStep * (k + 0.5);
      var nB = 13;
      for (var i2 = 0; i2 < nB; i2++) {
        var a2 = Math.PI * (i2 + 0.5) / nB;
        var r2 = AR - 0.2;
        box(r2 * Math.cos(a2), SP + r2 * Math.sin(a2), zr, 0.4, 0.5, ringStep - 0.02,
          jitter(C.sandDark, 0.06), '砌築穹窿第 ' + (k + 1) + ' 道石環第 ' + (i2 + 1) + ' 塊', [0, 0, a2]);
      }
    }

    // ==== 3. 台座頂面 ==================================================
    phase = 2;
    var nx = 15, nz = 7, cx = PL / nx, cz = PW / nz;
    for (var j = 0; j < nz; j++) for (var i3 = 0; i3 < nx; i3++) {
      box(-PL / 2 + cx * (i3 + 0.5), PH + 0.075, -PW / 2 + cz * (j + 0.5), cx - 0.05, 0.15, cz - 0.05,
        jitter(C.slab, 0.05), '鋪設台座頂面石板，第 ' + (j + 1) + ' 排第 ' + (i3 + 1) + ' 塊');
    }

    // ==== 4. 白色腰線 ==================================================
    phase = 3;
    function perimeter(hx, hz, seg, cb) {
      var n = 0;
      var sides = [
        { from: [-hx, hz], to: [hx, hz], name: '正面' },
        { from: [hx, hz], to: [hx, -hz], name: '右側' },
        { from: [hx, -hz], to: [-hx, -hz], name: '背面' },
        { from: [-hx, -hz], to: [-hx, hz], name: '左側' }
      ];
      for (var s = 0; s < sides.length; s++) {
        var sd = sides[s];
        var L = Math.hypot(sd.to[0] - sd.from[0], sd.to[1] - sd.from[1]);
        var m = Math.max(1, Math.round(L / seg));
        for (var q = 0; q < m; q++) {
          var t0 = q / m, t1 = (q + 1) / m;
          var ax = lerp(sd.from[0], sd.to[0], t0), az = lerp(sd.from[1], sd.to[1], t0);
          var bx = lerp(sd.from[0], sd.to[0], t1), bz = lerp(sd.from[1], sd.to[1], t1);
          cb(ax, az, bx, bz, sd.name, q + 1, ++n, s);
        }
      }
    }
    perimeter(PL / 2 + 0.15, PW / 2 + 0.15, 1.5, function (ax, az, bx, bz, nm, q) {
      bar([ax, PH + 0.25, az], [bx, PH + 0.25, bz], 0.5, 0.3, C.white, '安裝' + nm + '白色腰線第 ' + q + ' 段');
    });

    // ==== 5. 紅磚女牆 ==================================================
    phase = 4;
    var BRL = 0.5, BRH = 0.2, BRD = 0.3;
    for (var c3 = 0; c3 < 5; c3++) {
      var yb = PH + 0.5 + c3 * BRH + BRH / 2;
      for (var f3 = 0; f3 < 2; f3++) {
        var zb2 = (f3 === 0 ? 1 : -1) * (PW / 2 - 0.2);
        var off3 = (c3 % 2) * BRL / 2, i4 = 0;
        for (var xb2 = -PL / 2 + off3 - BRL; xb2 < PL / 2; xb2 += BRL) {
          var xa3 = Math.max(xb2, -PL / 2), xb3 = Math.min(xb2 + BRL, PL / 2);
          if (xb3 - xa3 < 0.12) continue;
          box((xa3 + xb3) / 2, yb, zb2, xb3 - xa3 - 0.02, BRH - 0.02, BRD, jitter(C.plaster, 0.025),
            '砌築' + faceNames[f3] + '女牆第 ' + (c3 + 1) + ' 層磚第 ' + (++i4) + ' 塊');
        }
      }
      for (var sg3 = -1; sg3 <= 1; sg3 += 2) {
        var xs3 = sg3 * (PL / 2 - 0.2);
        var off4 = (c3 % 2) * BRL / 2, i5 = 0;
        var zlim = PW / 2 - 0.4;
        for (var zb3 = -zlim + off4 - BRL; zb3 < zlim; zb3 += BRL) {
          var za4 = Math.max(zb3, -zlim), zb4 = Math.min(zb3 + BRL, zlim);
          if (zb4 - za4 < 0.12) continue;
          box(xs3, yb, (za4 + zb4) / 2, BRD, BRH - 0.02, zb4 - za4 - 0.02, jitter(C.plaster, 0.025),
            '砌築' + (sg3 > 0 ? '右側' : '左側') + '女牆第 ' + (c3 + 1) + ' 層磚第 ' + (++i5) + ' 塊');
        }
      }
    }
    perimeter(PL / 2 + 0.05, PW / 2 + 0.05, 1.5, function (ax, az, bx, bz, nm, q) {
      bar([ax, PH + 1.5 + 0.08, az], [bx, PH + 1.5 + 0.08, bz], 0.16, 0.42, C.coping, '安裝' + nm + '女牆壓頂第 ' + q + ' 段');
    });

    // ==== 6. 下層立柱 ==================================================
    phase = 5;
    var ring = [];
    for (var i6 = 0; i6 < 7; i6++) ring.push([-CL / 2 + i6 * CL / 6, CW / 2]);
    for (var j6 = 1; j6 <= 2; j6++) ring.push([CL / 2, CW / 2 - j6 * CW / 3]);
    for (var i7 = 6; i7 >= 0; i7--) ring.push([-CL / 2 + i7 * CL / 6, -CW / 2]);
    for (var j7 = 2; j7 >= 1; j7--) ring.push([-CL / 2, CW / 2 - j7 * CW / 3]);
    for (var ci = 0; ci < ring.length; ci++) {
      var p = ring[ci];
      box(p[0], FY + 0.15, p[1], 0.7, 0.3, 0.7, C.base, '安放下層第 ' + (ci + 1) + ' 根柱礎');
      cyl(p[0], FY + 0.3 + COL_H / 2, p[1], 0.46, COL_H, C.red, '豎立下層第 ' + (ci + 1) + ' 根朱紅木柱');
    }
    var inner = [[UL / 2 - 0.5, UW / 2 - 0.5], [-(UL / 2 - 0.5), UW / 2 - 0.5], [-(UL / 2 - 0.5), -(UW / 2 - 0.5)], [UL / 2 - 0.5, -(UW / 2 - 0.5)]];
    for (var ii = 0; ii < inner.length; ii++) {
      var ip = inner[ii];
      var ih = UY - 0.3 - FY - 0.3;
      box(ip[0], FY + 0.15, ip[1], 0.8, 0.3, 0.8, C.base, '安放內柱第 ' + (ii + 1) + ' 座柱礎');
      cyl(ip[0], FY + 0.3 + ih / 2, ip[1], 0.5, ih, C.red, '豎立通柱第 ' + (ii + 1) + ' 根（承接上層樓身）');
    }

    // ==== 7. 下層樑枋斗栱 ==============================================
    phase = 6;
    function bracketSet(x, y, z, dirx, dirz, label) {
      var ux = dirx, uz = dirz;
      box(x, y + 0.15, z, 0.5, 0.3, 0.5, C.teal, label + '：安放大斗');
      bar([x - ux * 0.65, y + 0.45, z - uz * 0.65], [x + ux * 0.65, y + 0.45, z + uz * 0.65], 0.3, 0.24, C.blue, label + '：安裝第一層栱');
      box(x - ux * 0.55, y + 0.75, z - uz * 0.55, 0.3, 0.3, 0.3, C.teal, label + '：安放左升');
      box(x + ux * 0.55, y + 0.75, z + uz * 0.55, 0.3, 0.3, 0.3, C.teal, label + '：安放右升');
      bar([x - ux * 1.0, y + 1.05, z - uz * 1.0], [x + ux * 1.0, y + 1.05, z + uz * 1.0], 0.28, 0.24, C.blue, label + '：安裝第二層栱');
    }
    function frame(ringPts, topY, label) {
      var n = ringPts.length;
      for (var a = 0; a < n; a++) {
        var pa = ringPts[a], pb = ringPts[(a + 1) % n];
        var dx = pb[0] - pa[0], dz = pb[1] - pa[1], L = Math.hypot(dx, dz);
        var ux = dx / L, uz = dz / L;
        bar([pa[0] + ux * 0.23, topY - 0.8, pa[1] + uz * 0.23], [pb[0] - ux * 0.23, topY - 0.8, pb[1] - uz * 0.23], 0.3, 0.28, C.red, '架設' + label + '第 ' + (a + 1) + ' 跨額枋');
        bar([pa[0] + ux * 0.23, topY - 0.25, pa[1] + uz * 0.23], [pb[0] - ux * 0.23, topY - 0.25, pb[1] - uz * 0.23], 0.45, 0.32, C.blue, '架設' + label + '第 ' + (a + 1) + ' 跨藍彩樑枋');
      }
      for (var b = 0; b < n; b++) {
        var qa = ringPts[b], qb = ringPts[(b + 1) % n];
        var ddx = qb[0] - qa[0], ddz = qb[1] - qa[1], LL = Math.hypot(ddx, ddz);
        var vx = ddx / LL, vz = ddz / LL;
        bracketSet(qa[0], topY, qa[1], vx, vz, label + '第 ' + (b + 1) + ' 柱頭斗栱');
        bracketSet((qa[0] + qb[0]) / 2, topY, (qa[1] + qb[1]) / 2, vx, vz, label + '第 ' + (b + 1) + ' 跨補間斗栱');
      }
    }
    function lanterns(pts, hx, hz, topY, label) {
      for (var a = 0; a < pts.length; a++) {
        var px = pts[a][0], pz = pts[a][1];
        var ox = Math.abs(Math.abs(px) - hx) < 1e-6 ? Math.sign(px) * 0.55 : 0;
        var oz = Math.abs(Math.abs(pz) - hz) < 1e-6 ? Math.sign(pz) * 0.55 : 0;
        var lx = px + ox, lz = pz + oz, ly = topY - 1.0;
        box(lx, ly + 0.55, lz, 0.03, 0.5, 0.03, C.cap, '為' + label + '第 ' + (a + 1) + ' 盞燈籠繫吊繩');
        box(lx, ly + 0.33, lz, 0.32, 0.08, 0.32, C.cap, '安裝' + label + '第 ' + (a + 1) + ' 盞燈籠頂蓋');
        add(2, lx, ly, lz, 0.48, 0.62, 0.48, C.lantern, '掛上' + label + '第 ' + (a + 1) + ' 盞白燈籠');
      }
    }
    frame(ring, CT, '下層');
    lanterns(ring, CL / 2, CW / 2, CT, '下層');
    var upperRing0 = [[UL / 2, UW / 2], [UL / 2, -UW / 2], [-UL / 2, -UW / 2], [-UL / 2, UW / 2]];
    for (var ub = 0; ub < 4; ub++) {
      var ua = upperRing0[ub], ubp = upperRing0[(ub + 1) % 4];
      bar([ua[0], UY - 0.3, ua[1]], [ubp[0], UY - 0.3, ubp[1]], 0.4, 0.4, C.red, '架設上層樓板圍樑第 ' + (ub + 1) + ' 根');
    }

    // ==== 8. 下層欄杆 ==================================================
    phase = 7;
    for (var r8 = 0; r8 < ring.length; r8++) {
      var ra = ring[r8], rb = ring[(r8 + 1) % ring.length];
      var rdx = rb[0] - ra[0], rdz = rb[1] - ra[1], rL = Math.hypot(rdx, rdz), rux = rdx / rL, ruz = rdz / rL;
      bar([ra[0] + rux * 0.23, FY + 1.0, ra[1] + ruz * 0.23], [rb[0] - rux * 0.23, FY + 1.0, rb[1] - ruz * 0.23], 0.12, 0.12, C.rail, '安裝第 ' + (r8 + 1) + ' 跨欄杆上橫桿');
      bar([ra[0] + rux * 0.23, FY + 0.35, ra[1] + ruz * 0.23], [rb[0] - rux * 0.23, FY + 0.35, rb[1] - ruz * 0.23], 0.1, 0.1, C.rail, '安裝第 ' + (r8 + 1) + ' 跨欄杆下橫桿');
      var nb = 6;
      for (var bi = 0; bi < nb; bi++) {
        var t = (bi + 1) / (nb + 1);
        box(lerp(ra[0], rb[0], t), FY + 0.675, lerp(ra[1], rb[1], t), 0.08, 0.65, 0.08, C.rail, '安裝第 ' + (r8 + 1) + ' 跨欄杆第 ' + (bi + 1) + ' 支直櫺');
      }
    }

    // ==== 屋頂產生器 ====================================================
    function roof(o) {
      function fcurve(v) { return 0.45 * v + 0.55 * (1 - (1 - v) * (1 - v)); }
      var sides = [
        { yaw: 0, name: '正面', thw: o.topHX, td: o.topHZ, ehw: o.eaveHX, ed: o.eaveHZ },
        { yaw: Math.PI, name: '背面', thw: o.topHX, td: o.topHZ, ehw: o.eaveHX, ed: o.eaveHZ },
        { yaw: Math.PI / 2, name: '右側', thw: o.topHZ, td: o.topHX, ehw: o.eaveHZ, ed: o.eaveHX },
        { yaw: -Math.PI / 2, name: '左側', thw: o.topHZ, td: o.topHX, ehw: o.eaveHZ, ed: o.eaveHX }
      ];
      function mk(sd) {
        var cy = Math.cos(sd.yaw), sy = Math.sin(sd.yaw);
        return {
          surf: function (u, v) {
            var hw = lerp(sd.thw, sd.ehw, v), d = lerp(sd.td, sd.ed, v);
            var y = o.topY - o.drop * fcurve(v) + o.lift * Math.pow(Math.abs(u), 3) * v * v;
            return [u * hw, y, d];
          },
          world: function (p) { return [p[0] * cy + p[2] * sy, p[1], -p[0] * sy + p[2] * cy]; }
        };
      }
      var slopeLen = Math.hypot(o.eaveHZ - o.topHZ, o.drop);
      var nRows = Math.max(1, Math.round(slopeLen / o.rowStep));
      // 椽
      for (var s = 0; s < 4; s++) {
        var S = mk(sides[s]);
        var nR = Math.round(2 * sides[s].ehw / 0.45);
        for (var r = 0; r < nR; r++) {
          var u = ((r + 0.5) / nR) * 2 - 1;
          var A = S.surf(u, 1.05), B = S.surf(u, 0.55);
          A[1] -= 0.24; B[1] -= 0.24;
          bar(S.world(A), S.world(B), 0.13, 0.13, C.rafter, '釘設' + o.label + sides[s].name + '第 ' + (r + 1) + ' 根簷椽');
        }
      }
      // 封簷板
      for (var s2 = 0; s2 < 4; s2++) {
        var S2 = mk(sides[s2]);
        var nF = Math.max(1, Math.round(2 * sides[s2].ehw / 1.0));
        for (var q = 0; q < nF; q++) {
          var A2 = S2.surf((q / nF) * 2 - 1, 1.07), B2 = S2.surf(((q + 1) / nF) * 2 - 1, 1.07);
          A2[1] -= 0.1; B2[1] -= 0.1;
          bar(S2.world(A2), S2.world(B2), 0.42, 0.1, C.fascia, '安裝' + o.label + sides[s2].name + '第 ' + (q + 1) + ' 段藍色封簷板');
        }
      }
      // 瓦（由簷口往上）
      for (var row = nRows - 1; row >= 0; row--) {
        var v = (row + 0.5) / nRows;
        for (var s3 = 0; s3 < 4; s3++) {
          var sd3 = sides[s3], S3 = mk(sd3);
          var hw = lerp(sd3.thw, sd3.ehw, v);
          var n = Math.round(2 * hw / o.tileW);
          if (n < 1) continue;
          for (var j = 0; j < n; j++) {
            var uu = ((j + 0.5) / n) * 2 - 1;
            var P = S3.surf(uu, v), Pa = S3.surf(uu, v - 0.02), Pb = S3.surf(uu, v + 0.02);
            var pitch = Math.atan2(-(Pb[1] - Pa[1]), Pb[2] - Pa[2]);
            var round = j % 2 === 0;
            var W = S3.world(P);
            box(W[0], W[1] + (round ? 0.06 : 0.0), W[2], o.tileW * (round ? 0.62 : 0.96), round ? 0.16 : 0.07, o.rowStep * 1.06,
              jitter(round ? C.tileRound : C.tile, 0.07),
              '鋪設' + o.label + sd3.name + '自簷口起第 ' + (nRows - row) + ' 排第 ' + (j + 1) + ' 片' + (round ? '筒瓦' : '板瓦'),
              [pitch, sd3.yaw, 0]);
          }
        }
      }
      // 垂脊（四角）
      var cornerNames = ['右前', '左前', '右後', '左後'];
      var corners = [[0, 1], [0, -1], [1, 1], [1, -1]];
      for (var cI = 0; cI < 4; cI++) {
        var sdc = sides[corners[cI][0]], Sc = mk(sdc), uc = corners[cI][1];
        var nSeg = 9;
        for (var sgI = 0; sgI < nSeg; sgI++) {
          var va = sgI / nSeg, vb = (sgI + 1) / nSeg;
          var Pa2 = Sc.surf(uc, va), Pb2 = Sc.surf(uc, vb * 1.0);
          Pa2[1] += 0.18; Pb2[1] += 0.18;
          bar(Sc.world(Pa2), Sc.world(Pb2), 0.26, 0.26, C.hip, '安裝' + o.label + cornerNames[cI] + '垂脊第 ' + (sgI + 1) + ' 段');
        }
        var tip = Sc.surf(uc, 1.0); tip[1] += 0.35;
        var tw = Sc.world(tip);
        box(tw[0], tw[1] + 0.1, tw[2], 0.3, 0.6, 0.3, C.ridge, '安放' + o.label + cornerNames[cI] + '角脊翹飾');
      }
      if (o.topRing) {
        for (var s4 = 0; s4 < 4; s4++) {
          var S4 = mk(sides[s4]);
          var nT = Math.max(1, Math.round(2 * sides[s4].thw / 1.0));
          for (var q4 = 0; q4 < nT; q4++) {
            var A4 = S4.surf((q4 / nT) * 2 - 1, 0.0), B4 = S4.surf(((q4 + 1) / nT) * 2 - 1, 0.0);
            A4[1] += 0.12; B4[1] += 0.12; A4[2] += 0.1; B4[2] += 0.1;
            bar(S4.world(A4), S4.world(B4), 0.22, 0.3, C.hip, '安裝' + o.label + sides[s4].name + '腰簷上緣脊線第 ' + (q4 + 1) + ' 段');
          }
        }
      }
      if (o.ridge) {
        var half = o.topHX + 1.1, nM = 26;
        function ridgeY(x) { return o.topY + 0.3 + 0.75 * Math.pow(Math.min(1, Math.abs(x) / half), 5); }
        for (var m = 0; m < nM; m++) {
          var xa = -half + (2 * half) * m / nM, xb = -half + (2 * half) * (m + 1) / nM;
          bar([xa, ridgeY(xa), 0], [xb, ridgeY(xb), 0], 0.36, 0.3, C.ridge, '安裝' + o.label + '正脊第 ' + (m + 1) + ' 段');
        }
        box(-half, ridgeY(-half) + 0.3, 0, 0.45, 0.7, 0.3, C.ridge, '安放' + o.label + '左燕尾脊飾');
        box(half, ridgeY(half) + 0.3, 0, 0.45, 0.7, 0.3, C.ridge, '安放' + o.label + '右燕尾脊飾');
        sph(0, o.topY + 0.3 + 0.4, 0, 0.55, C.gold, '安放' + o.label + '正脊中央寶珠');
      }
    }

    // ==== 9. 下層屋頂 ==================================================
    phase = 8;
    roof({ label: '下層屋頂', topHX: UL / 2 + 0.1, topHZ: UW / 2 + 0.1, topY: EY + D1, eaveHX: 11.1, eaveHZ: 6.8,
      drop: D1, lift: 0.9, tileW: 0.3, rowStep: 0.35, topRing: true });

    // ==== 10. 上層樓身 =================================================
    phase = 9;
    var uring = [];
    for (var i9 = 0; i9 < 6; i9++) uring.push([-UL / 2 + i9 * UL / 5, UW / 2]);
    for (var j9 = 1; j9 <= 2; j9++) uring.push([UL / 2, UW / 2 - j9 * UW / 3]);
    for (var i10 = 5; i10 >= 0; i10--) uring.push([-UL / 2 + i10 * UL / 5, -UW / 2]);
    for (var j10 = 2; j10 >= 1; j10--) uring.push([-UL / 2, UW / 2 - j10 * UW / 3]);
    for (var uc = 0; uc < uring.length; uc++) {
      cyl(uring[uc][0], UY + UH / 2, uring[uc][1], 0.36, UH, C.red, '豎立上層第 ' + (uc + 1) + ' 根簷柱');
    }
    for (var ub2 = 0; ub2 < uring.length; ub2++) {
      var wa = uring[ub2], wb = uring[(ub2 + 1) % uring.length];
      var wdx = wb[0] - wa[0], wdz = wb[1] - wa[1], wL = Math.hypot(wdx, wdz), wux = wdx / wL, wuz = wdz / wL;
      var ia = [wa[0] + wux * 0.18, wa[1] + wuz * 0.18], ib = [wb[0] - wux * 0.18, wb[1] - wuz * 0.18];
      var mid = [(wa[0] + wb[0]) / 2, (wa[1] + wb[1]) / 2];
      bar([ia[0], UY + 0.175, ia[1]], [ib[0], UY + 0.175, ib[1]], 0.35, 0.22, C.plaster, '砌築上層第 ' + (ub2 + 1) + ' 間下段白牆');
      bar([ia[0], UY + 0.55, ia[1]], [ib[0], UY + 0.55, ib[1]], 0.4, 0.18, C.plaster, '砌築上層第 ' + (ub2 + 1) + ' 間窗台白牆');
      if (ub2 === 2) {
        add(3, mid[0], UY + 0.95, mid[1] + 0.32, 1.9, 0.75, 0.12, C.window, '懸掛「迎曦門」匾額');
      } else {
        box(mid[0], UY + 0.55, mid[1], wux ? wL * 0.32 : 0.24, 0.34, wuz ? wL * 0.32 : 0.24, C.window, '安裝上層第 ' + (ub2 + 1) + ' 間小方窗');
        for (var lb = -1; lb <= 1; lb++) {
          var lo = lb * wL * 0.08;
          box(mid[0] + wux * lo, UY + 0.55, mid[1] + wuz * lo, 0.05, 0.34, 0.05, C.red, '安裝上層第 ' + (ub2 + 1) + ' 間窗櫺第 ' + (lb + 2) + ' 支');
        }
      }
      bar([ia[0], UY + 1.225, ia[1]], [ib[0], UY + 1.225, ib[1]], 0.95, 0.22, C.plaster, '砌築上層第 ' + (ub2 + 1) + ' 間上段白牆');
    }
    frame(uring, UCT, '上層');
    lanterns(uring, UL / 2, UW / 2, UCT, '上層');

    // ==== 11. 上層屋頂 =================================================
    phase = 10;
    var RL2 = UL + 2 * 2.3, RW2 = UW + 2 * 2.3;
    roof({ label: '上層屋頂', topHX: (RL2 - RW2) / 2, topHZ: 0, topY: UEY + D2, eaveHX: RL2 / 2, eaveHZ: RW2 / 2,
      drop: D2, lift: 1.0, tileW: 0.3, rowStep: 0.35, ridge: true });

    // ==== 12. 廣場設施 =================================================
    phase = 11;
    var bolls = [];
    perimeter(PL / 2 + 4.5, PW / 2 + 4.5, 3.0, function (ax, az, bx, bz, nm, q, n) { bolls.push([ax, az]); });
    for (var bI = 0; bI < bolls.length; bI++) {
      var bp = bolls[bI];
      cyl(bp[0], 0.45, bp[1], 0.4, 0.9, C.bollard, '安置廣場第 ' + (bI + 1) + ' 根石柱');
    }
    for (var bI2 = 0; bI2 < bolls.length; bI2++) {
      var pa5 = bolls[bI2], pb5 = bolls[(bI2 + 1) % bolls.length];
      var nL = 10;
      for (var lI = 0; lI < nL; lI++) {
        var t0 = lI / nL, t1 = (lI + 1) / nL;
        var sag = function (t) { return 0.78 - 0.22 * Math.sin(Math.PI * t); };
        bar([lerp(pa5[0], pb5[0], t0), sag(t0), lerp(pa5[1], pb5[1], t0)], [lerp(pa5[0], pb5[0], t1), sag(t1), lerp(pa5[1], pb5[1], t1)],
          0.07, 0.07, C.chain, '掛設第 ' + (bI2 + 1) + ' 跨鏈條第 ' + (lI + 1) + ' 節');
      }
    }
    var benches = [[-7, PW / 2 + 7.2], [-2.5, PW / 2 + 7.2], [2.5, PW / 2 + 7.2], [7, PW / 2 + 7.2]];
    for (var bn = 0; bn < benches.length; bn++) {
      var bb = benches[bn];
      box(bb[0] - 0.7, 0.2, bb[1], 0.3, 0.4, 0.45, C.bench, '安置第 ' + (bn + 1) + ' 張長椅左腳');
      box(bb[0] + 0.7, 0.2, bb[1], 0.3, 0.4, 0.45, C.bench, '安置第 ' + (bn + 1) + ' 張長椅右腳');
      box(bb[0], 0.45, bb[1], 1.9, 0.1, 0.5, C.bench, '安置第 ' + (bn + 1) + ' 張長椅座板');
    }
    var palms = [[-25, 13], [25, 13], [-29, -2], [29, -2], [-23, -14], [23, -14]];
    for (var pI = 0; pI < palms.length; pI++) {
      var pp = palms[pI], th = 7 + (pI % 3) * 0.8;
      var tilt = 0.06 * (pI % 2 === 0 ? 1 : -1);
      cyl(pp[0] + Math.sin(tilt) * th / 2, th / 2, pp[1], 0.42, th, C.trunk, '栽植第 ' + (pI + 1) + ' 棵棕櫚樹幹', [0, 0, -tilt]);
      var topx = pp[0] + Math.sin(tilt) * th, topy = th;
      sph(topx, topy, pp[1], 0.9, C.trunk, '第 ' + (pI + 1) + ' 棵棕櫚樹冠基部');
      var nFr = 9;
      for (var fr = 0; fr < nFr; fr++) {
        var yaw = fr / nFr * Math.PI * 2 + pI, droop = 0.35 + 0.1 * (fr % 2);
        var L = 3.2;
        var dx = Math.cos(droop) * Math.cos(yaw), dy = -Math.sin(droop), dz = -Math.cos(droop) * Math.sin(yaw);
        box(topx + dx * L / 2, topy + 0.1 + dy * L / 2, pp[1] + dz * L / 2, L, 0.1, 0.55, jitter(C.frond, 0.12),
          '第 ' + (pI + 1) + ' 棵棕櫚第 ' + (fr + 1) + ' 片葉', [0, yaw, -droop]);
      }
    }

    // ==== 13. 廣場鋪面（補足至 10,000）================================
    phase = 12;
    var before = els.length;
    if (before > TOTAL) throw new Error('構件數超過 10,000：' + before);
    var cell = 1.6, nx0 = Math.ceil(PL / 2 / cell), nz0 = Math.ceil(PW / 2 / cell);
    var ringNo = 1, placed = 0;
    while (els.length < TOTAL) {
      var ix = nx0 + ringNo - 1, iz = nz0 + ringNo - 1;
      var cells = [];
      for (var i = -ix; i <= ix; i++) { cells.push([i, iz]); }
      for (var jz = iz - 1; jz >= -iz; jz--) { cells.push([ix, jz]); }
      for (var i2b = ix - 1; i2b >= -ix; i2b--) { cells.push([i2b, -iz]); }
      for (var jz2 = -iz + 1; jz2 <= iz - 1; jz2++) { cells.push([-ix, jz2]); }
      for (var cc = 0; cc < cells.length && els.length < TOTAL; cc++) {
        var gx = cells[cc][0], gz = cells[cc][1];
        var px = (gx + 0.5) * cell, pz = (gz + 0.5) * cell;
        if (Math.abs(gx) < nx0 && Math.abs(gz) < nz0) continue;
        placed++;
        box(px, 0.04, pz, cell - 0.06, 0.08, cell - 0.06, jitter((gx + gz) % 2 === 0 ? C.paveA : C.paveB, 0.04),
          '鋪設廣場第 ' + ringNo + ' 圈石板第 ' + placed + ' 塊');
      }
      ringNo++;
      if (ringNo > 60) throw new Error('鋪面迴圈異常');
    }

    // 標上步驟編號與階段範圍
    var ranges = PHASES.map(function (p, i) { return { index: i, name: p.name, en: p.en, note: p.note, from: 0, to: 0, count: 0 }; });
    for (var e = 0; e < els.length; e++) {
      els[e].n = e + 1;
      var rg = ranges[els[e].ph];
      if (!rg.count) rg.from = e + 1;
      rg.to = e + 1; rg.count++;
    }
    return { steps: els, phases: ranges, total: els.length, dims: { PL: PL, PW: PW, PH: PH, EY: EY, UEY: UEY, top: UEY + D2 + 1.7 } };
  }

  return { build: build, PHASES: PHASES, TOTAL: TOTAL };
});
