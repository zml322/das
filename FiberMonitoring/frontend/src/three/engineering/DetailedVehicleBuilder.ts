import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { VehicleType } from "@/types/monitoring";

function rounded(
  size: number[],
  position: number[],
  material: THREE.Material,
  radius = 0.12,
): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new RoundedBoxGeometry(size[0], size[1], size[2], 3, radius),
    material,
  );
  mesh.position.fromArray(position);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}
function wheel(radius: number, x: number, z: number): THREE.Group {
  const group = new THREE.Group(),
    side = Math.sign(x);
  const tire = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, 0.28, 32),
    new THREE.MeshStandardMaterial({ color: 0x202328, roughness: 0.93 }),
  );
  tire.rotation.z = Math.PI / 2;
  group.add(tire);
  const rim = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.65, radius * 0.65, 0.3, 24),
    new THREE.MeshStandardMaterial({
      color: 0xabb9c5,
      metalness: 0.9,
      roughness: 0.22,
    }),
  );
  rim.rotation.z = Math.PI / 2;
  group.add(rim);
  const hub = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.22, radius * 0.22, 0.34, 12),
    new THREE.MeshStandardMaterial({
      color: 0x384652,
      metalness: 0.8,
      roughness: 0.3,
    }),
  );
  hub.rotation.z = Math.PI / 2;
  group.add(hub);
  for (let index = 0; index < 5; index++) {
    const spoke = new THREE.Mesh(
      new THREE.BoxGeometry(0.03, radius * 1.1, 0.065),
      new THREE.MeshStandardMaterial({
        color: 0x3f4c58,
        metalness: 0.85,
        roughness: 0.3,
      }),
    );
    spoke.position.x = side * 0.16;
    spoke.rotation.x = (index * Math.PI) / 5;
    group.add(spoke);
  }
  group.position.set(x, radius, z);
  return group;
}
function addWheels(
  group: THREE.Group,
  width: number,
  radius: number,
  axles: number[],
): void {
  axles.forEach((z) =>
    group.add(wheel(radius, width / 2, z), wheel(radius, -width / 2, z)),
  );
}
function addLights(
  group: THREE.Group,
  width: number,
  front: number,
  rear: number,
  height: number,
): void {
  const white = new THREE.MeshStandardMaterial({
    color: 0xf2f5eb,
    emissive: 0xf2e4b8,
    emissiveIntensity: 0.18,
    roughness: 0.2,
  });
  const red = new THREE.MeshStandardMaterial({
    color: 0xa81721,
    emissive: 0x710715,
    emissiveIntensity: 0.2,
    roughness: 0.2,
  });
  for (const x of [-width * 0.36, width * 0.36])
    group.add(
      rounded([width * 0.2, 0.16, 0.08], [x, height, front], white, 0.035),
      rounded([width * 0.2, 0.18, 0.08], [x, height, rear], red, 0.035),
    );
}
function addSedan(
  group: THREE.Group,
  paint: THREE.Material,
  glass: THREE.Material,
): void {
  group.add(rounded([1.9, 0.65, 4.8], [0, 0.75, 0], paint, 0.22));
  const cabin = rounded([1.62, 0.7, 2.35], [0, 1.31, 0.1], glass, 0.12);
  const cabinVertices = cabin.geometry.attributes.position;
  for (let i = 0; i < cabinVertices.count; i++) {
    const roof = THREE.MathUtils.clamp(cabinVertices.getY(i) / .7 + .5, 0, 1);
    cabinVertices.setZ(i, cabinVertices.getZ(i) * (1 - roof * .38));
    cabinVertices.setX(i, cabinVertices.getX(i) * (1 - roof * .12));
  }
  cabin.geometry.computeVertexNormals();
  group.add(cabin);
  group.add(rounded([1.45, 0.12, 1.56], [0, 1.68, 0.18], paint, 0.1));
  const trim = new THREE.MeshStandardMaterial({
    color: 0x43494c,
    metalness: 0.7,
    roughness: 0.25,
  });
  for (const x of [-0.82, 0.82]) {
    group.add(rounded([0.055, 0.65, 0.085], [x, 1.35, 0.25], paint, 0.02));
    group.add(rounded([0.16, 0.09, 0.18], [x * 1.12, 1.1, -0.62], trim, 0.03));
    for (const z of [-0.5, 0.75])
      group.add(rounded([0.035, 0.035, 0.22], [x * 1.16, 1.01, z], trim, 0.01));
  }
  group.add(
    rounded([1.75, 0.18, 0.15], [0, 0.42, -2.36], trim, 0.04),
    rounded([1.78, 0.15, 0.15], [0, 0.42, 2.36], trim, 0.04),
  );
  for (let index = 0; index < 6; index++)
    group.add(
      rounded(
        [0.95, 0.022, 0.025],
        [0, 0.55 + index * 0.04, -2.41],
        trim,
        0.008,
      ),
    );
  addWheels(group, 1.85, 0.36, [-1.52, 1.52]);
  addLights(group, 1.8, -2.42, 2.42, 0.83);
}
function addTruck(
  group: THREE.Group,
  paint: THREE.Material,
  glass: THREE.Material,
): void {
  const steel = new THREE.MeshStandardMaterial({
    color: 0x66727d,
    metalness: 0.75,
    roughness: 0.4,
  });
  group.add(rounded([2.25, 0.35, 10], [0, 0.7, 0], steel));
  group.add(rounded([2.45, 2.3, 2.65], [0, 1.65, -3.7], paint, 0.2));
  group.add(rounded([2.1, 0.8, 0.06], [0, 2.13, -5.04], glass, 0.06));
  for (const x of [-1.23, 1.23])
    group.add(rounded([0.04, 0.75, 1.5], [x, 2.1, -3.83], glass, 0.04));
  group.add(rounded([2.45, 2.7, 6.8], [0, 2.02, 1.0], paint, 0.05));
  for (let z = -2.25; z < 4.4; z += 0.25)
    for (const x of [-1.24, 1.24])
      group.add(rounded([0.04, 2.55, 0.045], [x, 2.02, z], paint, 0.015));
  group.add(rounded([2.45, 0.2, 0.15], [0, 0.7, -5.05], steel, 0.03));
  addWheels(group, 2.3, 0.49, [-3.8, 2.5, 3.8]);
  addLights(group, 2.3, -5.07, 4.5, 1);
}
function addBus(
  group: THREE.Group,
  paint: THREE.Material,
  glass: THREE.Material,
): void {
  group.add(rounded([2.5, 2.55, 10], [0, 1.73, 0], paint, 0.28));
  group.add(rounded([2.3, 1.2, 0.06], [0, 2.1, -5], glass, 0.1));
  for (const x of [-1.26, 1.26])
    for (let z = -3.7; z < 4.1; z += 1.15)
      group.add(rounded([0.035, 0.95, 1.02], [x, 2.21, z], glass, 0.055));
  const trim = new THREE.MeshStandardMaterial({
    color: 0x267293,
    metalness: 0.25,
    roughness: 0.5,
  });
  for (const x of [-1.26, 1.26])
    group.add(rounded([0.04, 0.18, 9.1], [x, 1.35, 0], trim, 0.02));
  addWheels(group, 2.45, 0.48, [-3.25, 3.25]);
  addLights(group, 2.4, -5.02, 5.02, 1);
}
export function buildDetailedVehicle(config: {
  vehicleType: VehicleType;
  color: number;
  position: THREE.Vector3;
  rotation: number;
  scale: number;
}): THREE.Group {
  const group = new THREE.Group();
  const paint = new THREE.MeshPhysicalMaterial({
    color: config.color,
    metalness: 0.48,
    roughness: 0.28,
    clearcoat: 1,
    clearcoatRoughness: 0.18,
  });
  const glass = new THREE.MeshPhysicalMaterial({
    color: 0x1e394a,
    metalness: 0.25,
    roughness: 0.12,
    clearcoat: 1,
  });
  if (config.vehicleType === VehicleType.TRUCK) addTruck(group, paint, glass);
  else if (config.vehicleType === VehicleType.BUS) addBus(group, paint, glass);
  else addSedan(group, paint, glass);
  group.position.copy(config.position);
  group.rotation.y = config.rotation;
  group.scale.setScalar(config.scale);
  group.name = `vehicle_${config.vehicleType}`;
  group.userData = {
    clickable: true,
    vehicleInfo: { type: config.vehicleType, color: config.color },
  };
  return group;
}
