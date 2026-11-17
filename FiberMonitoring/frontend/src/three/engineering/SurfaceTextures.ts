import * as THREE from "three";

/** Deterministic procedural texture; no remote assets or image baked into the 3D viewport. */
export function createSurfaceTexture(
  kind: "soil" | "asphalt" | "windows",
  seed = 1,
): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const context = canvas.getContext("2d")!;
  let value = seed;
  const random = () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
  context.fillStyle =
    kind === "windows" ? "#7291a8" : kind === "soil" ? "#c2b09a" : "#858d94";
  context.fillRect(0, 0, 256, 256);
  if (kind === "windows") {
    const reflection = context.createLinearGradient(0, 0, 256, 256);
    reflection.addColorStop(0, '#a6d7ec'); reflection.addColorStop(.4, '#4f8eb5'); reflection.addColorStop(1, '#224b73');
    context.fillStyle = reflection; context.fillRect(0, 0, 256, 256);
    for (let y = 0; y < 256; y += 32)
      for (let x = 0; x < 256; x += 43) {
        context.fillStyle = random() > .15 ? 'rgba(205,235,247,.10)' : 'rgba(28,56,80,.14)';
        context.fillRect(x + 2, y + 2, 40, 29);
      }
  } else {
    for (let i = 0; i < 8000; i++) {
      const light = Math.floor(55 + random() * 160);
      context.fillStyle = `rgba(${light},${light},${light},${kind === "soil" ? 0.45 : 0.25})`;
      const radius = kind === "soil" ? random() * 4 : random() * 1.5;
      context.beginPath();
      context.ellipse(
        random() * 256,
        random() * 256,
        radius * 1.8,
        radius,
        random() * Math.PI,
        0,
        Math.PI * 2,
      );
      context.fill();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.repeat.set(kind === "windows" ? 1 : 12, kind === "windows" ? 1 : kind === "soil" ? 2 : 8);
  return texture;
}
