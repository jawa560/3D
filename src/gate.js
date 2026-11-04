// =====================================================================
//  新竹東門城（迎曦門）程式化 3D 建模
//  ---------------------------------------------------------------
//  單位：公尺。座標：X = 左右、Y = 向上、Z = 前後（+Z 為照片拍攝的正面）。
//  每一個建模步驟都以「目的」註解開頭，說明為什麼這樣做。
// =====================================================================
(function (global) {
  'use strict';
  const THREE = global.THREE;

  // ---------------------------------------------------------------
  // 參數表：所有比例集中在這裡，之後要微調只改數字
  // ---------------------------------------------------------------
  const P = {
    base:  { w: 24, d: 15, h: 9, taper: 0.05, plinth: 0.5 }, // 城台
    arch:  { w: 5.6, spring: 4.2 },                           // 拱門：寬、起拱高（半圓拱）
    plat:  { h: 1.6, cap: 0.18 },                             // 白色女牆帶、壓頂
    lower: { xs: [-7.5, -4.5, -1.5, 1.5, 4.5, 7.5], zs: [-4, 0, 4],
             colH: 4.6, colR: 0.24, beamH: 0.4, bandH: 0.3,
             overhang: 2.8, roofRise: 2.3 },                  // 下層柱廊 + 腰簷
    upper: { w: 11, d: 6, colH: 3.4, colR: 0.2, beamH: 0.35, bandH: 0.28,
             overhang: 2.0, roofRise: 3.6, ridgeLen: 6, gableCut: 0.55,
             balconyOut: 1.0 },                               // 上層樓閣 + 歇山頂
    roof:  { p: 1.45, lift: 0.9, liftPow: 5, thick: 0.28 },  // 屋面曲線：凹弧指數、翹角高度
  };

  // ---------------------------------------------------------------
  // 材質：用 canvas 畫程序紋理，不依賴外部圖片
  // ---------------------------------------------------------------
  function makeStoneTexture() {
    // 目的：模擬照片中砂岩錯縫砌法（running bond），讓城台有石塊感
    const c = document.createElement('canvas'); c.width = 512; c.height = 384;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#8a775a'; ctx.fillRect(0, 0, 512, 384);          // 灰縫
    const rows = 8, cols = 4, bw = 512 / cols, bh = 384 / rows;
    for (let r = 0; r < rows; r++) {
      const off = (r % 2) ? bw / 2 : 0;
      for (let k = -1; k <= cols; k++) {
        const x = k * bw + off, y = r * bh;
        const hue = 36 + Math.random() * 8, sat = 26 + Math.random() * 10, lig = 60 + Math.random() * 10;
        ctx.fillStyle = `hsl(${hue},${sat}%,${lig}%)`;
        ctx.fillRect(x + 2, y + 2, bw - 4, bh - 4);
      }
    }
    for (let i = 0; i < 5000; i++) {                                 // 細小斑點
      ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.08})`;
      ctx.fillRect(Math.random() * 512, Math.random() * 384, 2, 2);
    }
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
    t.repeat.set(1 / 5.2, 1 / 3.6);   // 一張貼圖 = 4 塊 1.3 m 寬 × 8 皮 0.45 m 高
    return t;
  }

  function makeTileTexture() {
    // 目的：用左右漸層模擬筒瓦的圓弧起伏，橫線模擬瓦壟分段
    const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const ctx = c.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 64, 0);
    g.addColorStop(0, '#7e2d14'); g.addColorStop(0.18, '#b9471f'); g.addColorStop(0.45, '#d9754a');
    g.addColorStop(0.8, '#c4502a'); g.addColorStop(1, '#7e2d14');
    ctx.fillStyle = g; ctx.fillRect(0, 0, 64, 64);
    ctx.fillStyle = 'rgba(0,0,0,0.13)';
    for (let y = 0; y < 64; y += 16) ctx.fillRect(0, y, 64, 2);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }

  function makeLatticeTexture() {
    // 目的：上層窗戶的木格子窗櫺
    const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#3a2016'; ctx.fillRect(0, 0, 64, 64);
    ctx.fillStyle = '#c9a26a';
    for (let i = 0; i < 64; i += 16) { ctx.fillRect(i, 0, 3, 64); ctx.fillRect(0, i, 64, 3); }
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
    t.repeat.set(3, 3);
    return t;
  }

  const M = {};
  function initMaterials() {
    const std = (o) => new THREE.MeshStandardMaterial(o);
    M.stone   = std({ map: makeStoneTexture(), roughness: 0.95, metalness: 0 });
    M.plinth  = std({ color: 0x9c8b6b, roughness: 0.95 });
    M.white   = std({ color: 0xf3f0e7, roughness: 0.9 });
    M.cap     = std({ color: 0xcfcac0, roughness: 0.9 });
    M.red     = std({ color: 0xa3271b, roughness: 0.6 });
    M.darkRed = std({ color: 0x6e1a12, roughness: 0.7 });
    M.wood    = std({ color: 0x3a2418, roughness: 0.8 });
    M.blue    = std({ color: 0x2b4c9b, roughness: 0.55 });
    M.cream   = std({ color: 0xefe3c8, roughness: 0.9 });
    M.tile    = std({ map: makeTileTexture(), roughness: 0.7, side: THREE.DoubleSide });
    M.under   = std({ color: 0x7a1d14, roughness: 0.8, side: THREE.DoubleSide });
    M.gable   = std({ color: 0xf1e8d2, roughness: 0.9, side: THREE.DoubleSide });
    M.lattice = std({ map: makeLatticeTexture(), roughness: 0.8 });
    M.stoneLt = std({ color: 0xcbb58e, roughness: 0.95 });
    M.chain   = std({ color: 0x3b3b3b, roughness: 0.5, metalness: 0.6 });
    M.ground  = std({ color: 0xcfc9bd, roughness: 1 });
    M.road    = std({ color: 0x5b5b5e, roughness: 1 });
    M.line    = std({ color: 0xf0f0f0, roughness: 1 });
  }

  // ---------------------------------------------------------------
  // 小工具
  // ---------------------------------------------------------------
  function mesh(geo, mat, parent) {
    const m = new THREE.Mesh(geo, mat);
    m.castShadow = true; m.receiveShadow = true;
    if (parent) parent.add(m);
    return m;
  }
  // 以「底部」為基準放置方盒
  function box(parent, w, h, d, mat, x, yBottom, z) {
    const m = mesh(new THREE.BoxGeometry(w, h, d), mat, parent);
    m.position.set(x, yBottom + h / 2, z);
    return m;
  }
  function cyl(parent, rTop, rBot, h, mat, x, yBottom, z, seg = 20) {
    const m = mesh(new THREE.CylinderGeometry(rTop, rBot, h, seg), mat, parent);
    m.position.set(x, yBottom + h / 2, z);
    return m;
  }
  // 四邊圍成的方框（額枋、眉板、壓頂等）
  function ring(parent, w, d, h, thick, yBottom, mat) {
    box(parent, w + thick, h, thick, mat, 0, yBottom,  d / 2);
    box(parent, w + thick, h, thick, mat, 0, yBottom, -d / 2);
    box(parent, thick, h, d - thick, mat,  w / 2, yBottom, 0);
    box(parent, thick, h, d - thick, mat, -w / 2, yBottom, 0);
  }
  function tube(parent, points, radius, mat, closed = false, segs = 120) {
    const curve = new THREE.CatmullRomCurve3(points, closed, 'centripetal');
    return mesh(new THREE.TubeGeometry(curve, segs, radius, 8, closed), mat, parent);
  }
  function lineTube(parent, a, b, radius, mat) {
    const curve = new THREE.LineCurve3(a, b);
    return mesh(new THREE.TubeGeometry(curve, 2, radius, 8, false), mat, parent);
  }

  // ---------------------------------------------------------------
  // 步驟 1：城台
  // 目的：用「矩形剖面減去拱形洞」擠出，一次得到正面、背面、拱洞內壁；
  //       再把頂點依高度向內縮，做出城牆的收分（下寬上窄）。
  // ---------------------------------------------------------------
  function buildBase(g) {
    const { w, d, h, taper, plinth } = P.base;
    const r = P.arch.w / 2;
    const shape = new THREE.Shape();
    shape.moveTo(-w / 2, 0); shape.lineTo(w / 2, 0); shape.lineTo(w / 2, h); shape.lineTo(-w / 2, h); shape.closePath();
    const hole = new THREE.Path();
    hole.moveTo(-r, 0); hole.lineTo(-r, P.arch.spring);
    hole.absarc(0, P.arch.spring, r, Math.PI, 0, true);
    hole.lineTo(r, 0); hole.closePath();
    shape.holes.push(hole);

    const geo = new THREE.ExtrudeGeometry(shape, { depth: d, bevelEnabled: false, curveSegments: 36 });
    geo.translate(0, 0, -d / 2);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const s = 1 - taper * (pos.getY(i) / h);
      pos.setX(i, pos.getX(i) * s); pos.setZ(i, pos.getZ(i) * s);
    }
    geo.computeVertexNormals();
    // 依面的朝向重設 UV：正背面 (x,y)、側面 (z,y)、拱頂 (z,x)，
    // 否則 ExtrudeGeometry 預設會把側牆的石塊轉 90 度。
    const nrm = geo.attributes.normal, uv = geo.attributes.uv;
    for (let i = 0; i < pos.count; i += 3) {
      const nx = Math.abs(nrm.getX(i)), ny = Math.abs(nrm.getY(i)), nz = Math.abs(nrm.getZ(i));
      for (let k = i; k < i + 3; k++) {
        const x = pos.getX(k), y = pos.getY(k), z = pos.getZ(k);
        if (nz >= nx && nz >= ny) uv.setXY(k, x, y);
        else if (nx >= ny)        uv.setXY(k, z, y);
        else                      uv.setXY(k, z, x);
      }
    }
    uv.needsUpdate = true;
    mesh(geo, M.stone, g);

    // 基座勒腳：讓城台和地面有個過渡
    box(g, w + 0.8, plinth, d + 0.8, M.plinth, 0, 0, 0);
    return h;
  }

  // ---------------------------------------------------------------
  // 步驟 2：白色女牆帶 + 壓頂
  // 目的：對應照片中石台上方那圈白色粉刷帶，並作為城樓的地坪。
  // ---------------------------------------------------------------
  function buildPlatform(g, yTop) {
    const s = 1 - P.base.taper;
    const wt = P.base.w * s, dt = P.base.d * s;
    box(g, wt, P.plat.h, dt, M.white, 0, yTop, 0);
    box(g, wt + 0.3, P.plat.cap, dt + 0.3, M.cap, 0, yTop + P.plat.h, 0);
    return yTop + P.plat.h + P.plat.cap;   // 城樓地坪高度
  }

  // ---------------------------------------------------------------
  // 欄杆：下層用實心木板，上層用直櫺
  // ---------------------------------------------------------------
  function railing(parent, a, b, yBase, h, style) {
    const dx = b[0] - a[0], dz = b[1] - a[1];
    const len = Math.hypot(dx, dz);
    const grp = new THREE.Group();
    grp.position.set((a[0] + b[0]) / 2, yBase, (a[1] + b[1]) / 2);
    grp.rotation.y = Math.atan2(dx, dz);
    box(grp, 0.12, 0.12, len, M.red, 0, h - 0.12, 0);     // 扶手
    box(grp, 0.10, 0.10, len, M.red, 0, 0.12, 0);         // 底枋
    if (style === 'panel') {
      box(grp, 0.05, h - 0.4, len, M.wood, 0, 0.22, 0);   // 木板
    } else {
      const n = Math.max(1, Math.round(len / 0.45));
      for (let i = 0; i <= n; i++) {
        const z = -len / 2 + (len * i) / n;
        box(grp, 0.06, h - 0.34, 0.06, M.red, 0, 0.22, z);
      }
    }
    parent.add(grp);
  }

  // ---------------------------------------------------------------
  // 步驟 3：下層柱廊
  // 目的：照片下層是開放式紅柱廊，正面六柱五間；柱間設欄杆，
  //       正中一間留作出入口；柱頂放額枋與藍色眉板承接屋簷。
  // ---------------------------------------------------------------
  function buildLowerTier(g, yF) {
    const L = P.lower;
    const w = L.xs[L.xs.length - 1] - L.xs[0];
    const d = L.zs[L.zs.length - 1] - L.zs[0];

    // 柱子只放在外圈
    const perim = [];
    for (const x of L.xs) for (const z of L.zs) {
      const edge = x === L.xs[0] || x === L.xs[L.xs.length - 1] || z === L.zs[0] || z === L.zs[L.zs.length - 1];
      if (edge) perim.push([x, z]);
    }
    for (const [x, z] of perim) {
      cyl(g, L.colR + 0.12, L.colR + 0.16, 0.25, M.plinth, x, yF, z);          // 石柱礎
      cyl(g, L.colR, L.colR * 1.06, L.colH, M.red, x, yF + 0.25, z);           // 紅柱
    }

    // 欄杆：沿外圈逐間放置，正面中央一間留門
    const walk = (pts) => { for (let i = 0; i < pts.length - 1; i++) railing(g, pts[i], pts[i + 1], yF + 0.25, 1.0, 'panel'); };
    const front = L.xs.map((x) => [x, L.zs[L.zs.length - 1]]);
    const back  = L.xs.map((x) => [x, L.zs[0]]);
    const mid = Math.floor(front.length / 2);
    walk(front.slice(0, mid)); walk(front.slice(mid));        // 跳過中央一間 → 出入口
    walk(back);
    walk(L.zs.map((z) => [L.xs[0], z]));
    walk(L.zs.map((z) => [L.xs[L.xs.length - 1], z]));

    // 內室：讓柱廊後方不是空的
    box(g, w - 4.5, L.colH, d - 2.5, M.cream, 0, yF + 0.25, 0);
    box(g, 1.8, 2.6, 0.2, M.wood, 0, yF + 0.25, (d - 2.5) / 2);               // 門
    box(g, 1.8, 2.6, 0.2, M.wood, 0, yF + 0.25, -(d - 2.5) / 2);

    // 額枋（紅）與眉板（藍）
    const yBeam = yF + 0.25 + L.colH;
    ring(g, w, d, L.beamH, 0.36, yBeam, M.red);
    ring(g, w + 0.3, d + 0.3, L.bandH, 0.22, yBeam + L.beamH, M.blue);
    const yBandTop = yBeam + L.beamH + L.bandH;
    ring(g, w + 0.2, d + 0.2, 0.6, 0.5, yBandTop, M.darkRed);                  // 簷下填充（椽子區）

    return { yEave: yBandTop - 0.3, w, d };
  }

  // ---------------------------------------------------------------
  // 屋面曲面：這是整個模型的核心
  // 目的：中式屋頂不是平面。用 (u, v) 參數曲面：
  //   - v 方向高度用 v^p（p>1）→ 近簷平緩、近脊陡峭，形成凹弧「反宇」；
  //   - 簷口用 |2u-1|^k 讓兩端翹起、中段平直，形成閩南式燕尾翹角，
  //     並以 (1-v)^2 讓翹起只影響簷口附近。
  // ---------------------------------------------------------------
  function roofPoint(S, u, v) {
    const ex = S.E0[0] + (S.E1[0] - S.E0[0]) * u, ez = S.E0[1] + (S.E1[1] - S.E0[1]) * u;
    const tx = S.T0[0] + (S.T1[0] - S.T0[0]) * u, tz = S.T0[1] + (S.T1[1] - S.T0[1]) * u;
    const x = ex + (tx - ex) * v, z = ez + (tz - ez) * v;
    const R = P.roof;
    const lift = R.lift * Math.pow(Math.abs(2 * u - 1), R.liftPow) * Math.pow(Math.max(0, 1 - v), 2);
    const y = S.yE + (S.yT - S.yE) * Math.pow(Math.max(0, v), R.p) + lift;
    return new THREE.Vector3(x, y, z);
  }

  function patchGeometry(S, vMax, nu, nv, uvU, uvV) {
    const pos = [], uv = [], idx = [];
    for (let j = 0; j <= nv; j++) {
      const v = (vMax * j) / nv;
      for (let i = 0; i <= nu; i++) {
        const u = i / nu;
        const p = roofPoint(S, u, v);
        pos.push(p.x, p.y, p.z); uv.push(u * uvU, v * uvV);
      }
    }
    for (let j = 0; j < nv; j++) for (let i = 0; i < nu; i++) {
      const a = j * (nu + 1) + i, b = a + 1, c = a + nu + 1, e = c + 1;
      idx.push(a, c, b, b, c, e);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    geo.setIndex(idx); geo.computeVertexNormals();
    return geo;
  }

  // 一片屋坡 = 瓦面（上）+ 簷底（下，深紅）
  function addSlope(g, S, vMax) {
    const width = Math.hypot(S.E1[0] - S.E0[0], S.E1[1] - S.E0[1]);
    const run = Math.hypot(S.T0[0] - S.E0[0], S.T0[1] - S.E0[1]);
    const geo = patchGeometry(S, vMax, 48, 18, width / 0.4, run / 0.6);
    mesh(geo, M.tile, g);
    const under = geo.clone(); under.translate(0, -P.roof.thick, 0);
    mesh(under, M.under, g);
  }

  // 垂脊：沿屋坡的 u=0 邊，往簷外延伸一點做翹起的脊尾
  function addHipRidge(g, S, vMax) {
    const pts = [];
    for (let k = 0; k <= 24; k++) {
      const v = -0.12 + (vMax + 0.12) * (k / 24);
      const p = roofPoint(S, 0, v); p.y += 0.12;
      if (v < 0) p.y += (-v / 0.12) * 0.35;      // 脊尾額外上翹
      pts.push(p);
    }
    tube(g, pts, 0.15, M.blue, false, 60);
    tube(g, pts.map((p) => p.clone().setY(p.y + 0.09)), 0.07, M.white, false, 60);
  }

  // 簷口封板：四坡簷線串成一圈
  function addEaveTrim(g, sides) {
    const pts = [];
    for (const S of sides) for (let i = 0; i < 40; i++) pts.push(roofPoint(S, i / 40, 0).setY(roofPoint(S, i / 40, 0).y - P.roof.thick / 2));
    tube(g, pts, 0.17, M.blue, true, 240);
    tube(g, pts.map((p) => p.clone().setY(p.y - 0.17)), 0.06, M.white, true, 240);
  }

  // ---------------------------------------------------------------
  // 步驟 4：下層腰簷（重簷的下簷）
  // 目的：下簷沒有正脊，是一圈環繞上層的裙狀屋面；簷口外緣接近城台邊，
  //       上緣收到上層迴廊的地板下。
  // ---------------------------------------------------------------
  function buildLowerRoof(g, yE, w, d) {
    const L = P.lower, U = P.upper;
    const W = w + 2 * L.overhang, D = d + 2 * L.overhang;
    const Wt = U.w + 2 * U.balconyOut + 0.4, Dt = U.d + 2 * U.balconyOut + 0.4;
    const yT = yE + L.roofRise;
    const sides = [
      { E0: [-W / 2,  D / 2], E1: [ W / 2,  D / 2], T0: [-Wt / 2,  Dt / 2], T1: [ Wt / 2,  Dt / 2], yE, yT },
      { E0: [ W / 2,  D / 2], E1: [ W / 2, -D / 2], T0: [ Wt / 2,  Dt / 2], T1: [ Wt / 2, -Dt / 2], yE, yT },
      { E0: [ W / 2, -D / 2], E1: [-W / 2, -D / 2], T0: [ Wt / 2, -Dt / 2], T1: [-Wt / 2, -Dt / 2], yE, yT },
      { E0: [-W / 2, -D / 2], E1: [-W / 2,  D / 2], T0: [-Wt / 2, -Dt / 2], T1: [-Wt / 2,  Dt / 2], yE, yT },
    ];
    for (const S of sides) { addSlope(g, S, 1); addHipRidge(g, S, 1); }
    addEaveTrim(g, sides);
    return yT;
  }

  // ---------------------------------------------------------------
  // 步驟 5：上層樓閣
  // 目的：上層是封閉樓閣：米白牆面、格子窗、紅柱貼牆，外圈有一圈紅色迴廊欄杆。
  // ---------------------------------------------------------------
  function buildUpperTier(g, yT) {
    const U = P.upper;
    const bw = U.w + 2 * U.balconyOut, bd = U.d + 2 * U.balconyOut;
    box(g, bw + 0.2, 0.3, bd + 0.2, M.wood, 0, yT - 0.2, 0);        // 迴廊地板
    const yF2 = yT + 0.1;

    // 迴廊欄杆（直櫺）
    const c = [[-bw / 2 + 0.15, bd / 2 - 0.15], [bw / 2 - 0.15, bd / 2 - 0.15], [bw / 2 - 0.15, -bd / 2 + 0.15], [-bw / 2 + 0.15, -bd / 2 + 0.15]];
    for (let i = 0; i < 4; i++) railing(g, c[i], c[(i + 1) % 4], yF2, 0.95, 'baluster');

    // 牆體
    box(g, U.w, U.colH, U.d, M.cream, 0, yF2, 0);

    // 貼牆紅柱 + 窗
    const xs = [-U.w / 2, -U.w / 4, 0, U.w / 4, U.w / 2];
    const zs = [-U.d / 2, 0, U.d / 2];
    for (const x of xs) for (const z of [-U.d / 2, U.d / 2]) cyl(g, U.colR, U.colR, U.colH, M.red, x, yF2, z);
    for (const z of zs) for (const x of [-U.w / 2, U.w / 2]) cyl(g, U.colR, U.colR, U.colH, M.red, x, yF2, z);
    for (let i = 0; i < xs.length - 1; i++) {
      const x = (xs[i] + xs[i + 1]) / 2;
      box(g, 1.9, 1.7, 0.1, M.lattice, x, yF2 + 0.9,  U.d / 2 + 0.03);
      box(g, 1.9, 1.7, 0.1, M.lattice, x, yF2 + 0.9, -U.d / 2 - 0.03);
    }
    for (let i = 0; i < zs.length - 1; i++) {
      const z = (zs[i] + zs[i + 1]) / 2;
      box(g, 0.1, 1.7, 1.7, M.lattice,  U.w / 2 + 0.03, yF2 + 0.9, z);
      box(g, 0.1, 1.7, 1.7, M.lattice, -U.w / 2 - 0.03, yF2 + 0.9, z);
    }

    // 額枋、眉板、簷下填充
    const yBeam = yF2 + U.colH;
    ring(g, U.w, U.d, U.beamH, 0.36, yBeam, M.red);
    ring(g, U.w + 0.3, U.d + 0.3, U.bandH, 0.22, yBeam + U.beamH, M.blue);
    const yBandTop = yBeam + U.beamH + U.bandH;
    ring(g, U.w + 0.2, U.d + 0.2, 0.6, 0.5, yBandTop, M.darkRed);
    return yBandTop - 0.3;
  }

  // ---------------------------------------------------------------
  // 步驟 6：上層歇山頂（燕尾脊）
  // 目的：歇山 = 前後坡到正脊、左右坡只到一半、上方補垂直山花。
  //       做法：左右坡的 v 只取到 gableCut，再用三角形補山花；
  //       正脊用管狀曲線，兩端以 |t|^4 上翹成燕尾。
  // ---------------------------------------------------------------
  function buildUpperRoof(g, yE) {
    const U = P.upper;
    const W = U.w + 2 * U.overhang, D = U.d + 2 * U.overhang;
    const yT = yE + U.roofRise, R = U.ridgeLen, vg = U.gableCut;
    const sides = [
      { E0: [-W / 2,  D / 2], E1: [ W / 2,  D / 2], T0: [-R / 2, 0], T1: [ R / 2, 0], yE, yT, vMax: 1  },
      { E0: [ W / 2,  D / 2], E1: [ W / 2, -D / 2], T0: [ R / 2, 0], T1: [ R / 2, 0], yE, yT, vMax: vg },
      { E0: [ W / 2, -D / 2], E1: [-W / 2, -D / 2], T0: [ R / 2, 0], T1: [-R / 2, 0], yE, yT, vMax: 1  },
      { E0: [-W / 2, -D / 2], E1: [-W / 2,  D / 2], T0: [-R / 2, 0], T1: [-R / 2, 0], yE, yT, vMax: vg },
    ];
    for (const S of sides) { addSlope(g, S, S.vMax); addHipRidge(g, S, S.vMax); }
    addEaveTrim(g, sides);

    // 山花 + 戧脊
    for (const S of [sides[1], sides[3]]) {
      const A = roofPoint(S, 0, vg), B = roofPoint(S, 1, vg);
      const C = new THREE.Vector3(S.T0[0], yT, 0);
      const geo = new THREE.BufferGeometry().setFromPoints([A, B, C]);
      geo.computeVertexNormals();
      mesh(geo, M.gable, g);
      lineTube(g, A.clone().setY(A.y + 0.1), C.clone().setY(C.y + 0.12), 0.14, M.blue);
      lineTube(g, B.clone().setY(B.y + 0.1), C.clone().setY(C.y + 0.12), 0.14, M.blue);
      lineTube(g, A.clone().setY(A.y + 0.1), B.clone().setY(B.y + 0.1), 0.14, M.blue);
    }

    // 正脊（燕尾）
    const pts = [];
    for (let k = 0; k <= 40; k++) {
      const t = -1 + (2 * k) / 40;
      pts.push(new THREE.Vector3(t * (R / 2 + 0.7), yT + 0.14 + 1.5 * Math.pow(Math.abs(t), 4), 0));
    }
    tube(g, pts, 0.2, M.blue, false, 80);
    tube(g, pts.map((p) => p.clone().setY(p.y + 0.12)), 0.08, M.white, false, 80);
    return yT;
  }

  // ---------------------------------------------------------------
  // 步驟 7：周邊環境
  // 目的：給模型尺度感──地坪、石台基座、石樁鐵鏈、前方馬路。
  // ---------------------------------------------------------------
  function buildSurroundings(g) {
    const ground = mesh(new THREE.PlaneGeometry(160, 160), M.ground, g);
    ground.rotation.x = -Math.PI / 2; ground.castShadow = false;
    box(g, 32, 0.35, 22, M.stoneLt, 0, 0, 0);                       // 石台基座

    // 石樁 + 鐵鏈
    const rx = 15, rz = 10, posts = [];
    const along = (n, f) => { for (let i = 0; i < n; i++) posts.push(f(i / n)); };
    along(12, (t) => [-rx + 2 * rx * t,  rz]);
    along(8,  (t) => [ rx, rz - 2 * rz * t]);
    along(12, (t) => [ rx - 2 * rx * t, -rz]);
    along(8,  (t) => [-rx, -rz + 2 * rz * t]);
    for (const [x, z] of posts) cyl(g, 0.18, 0.21, 0.75, M.stoneLt, x, 0.35, z, 12);
    for (let i = 0; i < posts.length; i++) {
      const a = posts[i], b = posts[(i + 1) % posts.length];
      const pa = new THREE.Vector3(a[0], 1.05, a[1]), pb = new THREE.Vector3(b[0], 1.05, b[1]);
      const mid = pa.clone().lerp(pb, 0.5); mid.y -= 0.25;
      tube(g, [pa, mid, pb], 0.03, M.chain, false, 16);
    }

    // 前方馬路
    box(g, 160, 0.02, 10, M.road, 0, 0.005, 19);
    for (let x = -80; x < 80; x += 6) box(g, 3, 0.03, 0.2, M.line, x, 0.01, 19);
  }

  // ---------------------------------------------------------------
  // 總裝：依步驟由下往上組裝
  // ---------------------------------------------------------------
  function buildGate() {
    initMaterials();
    const g = new THREE.Group(); g.name = 'EastGate';
    const yStoneTop = buildBase(g);                       // 1 城台
    const yFloor    = buildPlatform(g, yStoneTop);        // 2 女牆帶 → 地坪
    const lower     = buildLowerTier(g, yFloor);          // 3 下層柱廊
    const yLowerTop = buildLowerRoof(g, lower.yEave, lower.w, lower.d); // 4 腰簷
    const yUpperEave = buildUpperTier(g, yLowerTop);      // 5 上層樓閣
    const yRidge    = buildUpperRoof(g, yUpperEave);      // 6 歇山頂
    const env = new THREE.Group(); env.name = 'Environment';
    buildSurroundings(env);                               // 7 周邊
    return { gate: g, env, height: yRidge };
  }

  global.buildGate = buildGate;
  global.GATE_PARAMS = P;
})(window);
