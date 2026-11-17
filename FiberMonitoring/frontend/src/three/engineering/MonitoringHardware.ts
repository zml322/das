import * as THREE from "three";
import { DISPLAY, displayLength } from "./layout";

function cylinder(
  radius: number,
  height: number,
  material: THREE.Material,
): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, height, 12),
    material,
  );
  mesh.castShadow = true;
  return mesh;
}

export function buildMonitoringHardware(): THREE.Group {
  const group = new THREE.Group();
  group.name = "monitoringHardware";
  const metal = new THREE.MeshStandardMaterial({
    color: 0xafc2ce,
    roughness: 0.35,
    metalness: 0.75,
  });
  for (let x = -displayLength / 2 + 15; x < displayLength / 2; x += 32) {
    const support = cylinder(0.13, 9, metal);
    support.position.set(x, -5, 18.4);
    group.add(support);
    for (const depth of [1.1, 2, 2.9]) {
      const clip = new THREE.Mesh(
        new THREE.TorusGeometry(0.32, 0.09, 6, 12),
        metal,
      );
      clip.rotation.y = Math.PI / 2;
      clip.position.set(x, -depth * DISPLAY.depth, 18.4);
      group.add(clip);
    }
  }
  for (const x of [-displayLength * 0.48, displayLength * 0.54]) {
    const pole = cylinder(0.16, 7.5, metal);
    pole.position.set(x, 3.75, 19);
    group.add(pole);
    const cabinet = new THREE.Mesh(
      new THREE.BoxGeometry(1.7, 2.7, 0.8),
      new THREE.MeshStandardMaterial({
        color: 0xdce4e6,
        metalness: 0.3,
        roughness: 0.5,
      }),
    );
    cabinet.position.set(x, 3.9, 19);
    cabinet.castShadow = true;
    group.add(cabinet);
    const screen = new THREE.Mesh(
      new THREE.BoxGeometry(0.75, 0.45, 0.04),
      new THREE.MeshStandardMaterial({
        color: 0x183b47,
        emissive: 0x146b80,
        emissiveIntensity: 0.3,
      }),
    );
    screen.position.set(x, 4.45, 19.43);
    group.add(screen);
    const warning = new THREE.Mesh(
      new THREE.ConeGeometry(0.25, 0.45, 3),
      new THREE.MeshBasicMaterial({ color: 0xe4bd43 }),
    );
    warning.rotation.z = Math.PI;
    warning.position.set(x, 3.6, 19.45);
    group.add(warning);
  }
  return group;
}
