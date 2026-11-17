import * as THREE from 'three';

export function setupEngineeringLighting(scene: THREE.Scene): void {
  const canvas = document.createElement('canvas');
  canvas.width = 1024; canvas.height = 512;
  const ctx = canvas.getContext('2d')!;
  const sky = ctx.createLinearGradient(0, 0, 0, 512);
  sky.addColorStop(0, '#237cce'); sky.addColorStop(.45, '#72bdeb');
  sky.addColorStop(.78, '#bfdeec'); sky.addColorStop(1, '#e8eee6');
  ctx.fillStyle = sky; ctx.fillRect(0, 0, 1024, 512);
  if (ctx.createRadialGradient) {
    for (let group = 0; group < 9; group++) {
      const x = (group * 173 + 50) % 1100, y = 40 + (group * 67) % 120;
      for (let part = 0; part < 7; part++) {
        const cx = x + part * 24, cy = y + Math.sin(part * 2.4) * 12;
        const cloud = ctx.createRadialGradient(cx, cy, 2, cx, cy, 54);
        cloud.addColorStop(0, 'rgba(255,255,255,.48)');
        cloud.addColorStop(.5, 'rgba(255,255,255,.29)');
        cloud.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = cloud; ctx.fillRect(cx - 54, cy - 54, 108, 108);
      }
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  scene.background = texture;
  scene.fog = new THREE.Fog(0xb8d7e4, 190, 600);
  scene.add(new THREE.HemisphereLight(0xd4edff, 0xaa8354, .95));
  const sun = new THREE.DirectionalLight(0xfff1da, 2.8);
  sun.position.set(-65, 100, 60);
  sun.castShadow = true;
  Object.assign(sun.shadow.camera, { left: -110, right: 110, top: 90, bottom: -90, near: 1, far: 350 });
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.normalBias = .035; sun.shadow.bias = -.00015;
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xd2eaff, 1.1);
  fill.position.set(15, 12, 90);
  scene.add(fill);
}
