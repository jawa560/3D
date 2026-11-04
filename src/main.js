// 場景、燈光、控制與匯出
(function () {
  'use strict';
  const THREE = window.THREE;

  const canvas = document.getElementById('view');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xbfd7ee);
  scene.fog = new THREE.Fog(0xbfd7ee, 90, 220);

  const camera = new THREE.PerspectiveCamera(42, 1, 0.5, 600);
  camera.position.set(38, 15, 46);

  // 燈光：半球光給天空/地面環境色，方向光當太陽並投陰影
  scene.add(new THREE.HemisphereLight(0xd6e6ff, 0x8a7a60, 0.95));
  const sun = new THREE.DirectionalLight(0xfff1dc, 1.7);
  sun.position.set(35, 60, 30);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const sc = sun.shadow.camera;
  sc.left = -45; sc.right = 45; sc.top = 45; sc.bottom = -45; sc.near = 10; sc.far = 160;
  sun.shadow.bias = -0.0005;
  scene.add(sun);

  // 建模
  const { gate, env, height } = window.buildGate();
  scene.add(gate, env);

  const controls = new window.OrbitControls(camera, canvas);
  controls.target.set(0, height * 0.45, 0);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI / 2 - 0.01;
  controls.minDistance = 8;
  controls.maxDistance = 180;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 0.8;
  controls.update();

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);
  resize();

  // UI
  document.getElementById('rotate').addEventListener('change', (e) => { controls.autoRotate = e.target.checked; });
  document.getElementById('env').addEventListener('change', (e) => { env.visible = e.target.checked; });
  document.getElementById('wire').addEventListener('change', (e) => {
    gate.traverse((o) => { if (o.isMesh) o.material.wireframe = e.target.checked; });
  });
  document.getElementById('export').addEventListener('click', () => {
    const exporter = new window.GLTFExporter();
    exporter.parse(gate, (buf) => {
      const blob = new Blob([buf], { type: 'model/gltf-binary' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'hsinchu-east-gate.glb';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    }, (err) => { console.error(err); alert('匯出失敗：' + err); }, { binary: true });
  });
  document.getElementById('toggle-steps').addEventListener('click', () => {
    document.getElementById('panel').classList.toggle('collapsed');
  });

  // 幾個預設視角
  const views = {
    front: [0, 12, 60], corner: [38, 15, 46], side: [60, 12, 0], top: [0.1, 70, 0.1], under: [6, 1.6, 30],
  };
  document.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => {
    const v = views[b.dataset.view];
    camera.position.set(v[0], v[1], v[2]);
    controls.target.set(0, b.dataset.view === 'under' ? 5 : height * 0.45, 0);
    controls.update();
  }));

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
  window.__scene = { scene, camera, controls, renderer, gate, env };
})();
