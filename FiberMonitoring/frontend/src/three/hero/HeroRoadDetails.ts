import * as THREE from "three";
import { displayLength } from '../engineering/layout';

function barrier(x: number, z: number): THREE.Group {
  const group = new THREE.Group(),
    white = new THREE.MeshStandardMaterial({
      color: 0xf1ede1,
      roughness: 0.65,
    }),
    red = new THREE.MeshStandardMaterial({ color: 0xd94e39, roughness: 0.55 });
  for (const side of [-1, 1]) {
    const post = new THREE.Mesh(
      new THREE.CylinderGeometry(0.055, 0.055, 1.15, 8),
      white,
    );
    post.position.set(side * 1.5, 0.57, 0);
    group.add(post);
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.07, 0.5), red);
    foot.position.set(side * 1.5, 0.04, 0);
    group.add(foot);
  }
  const board = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.38, 0.12), white);
  board.position.y = 0.9;
  group.add(board);
  for (let index = 0; index < 7; index++) {
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.4, 0.125), red);
    stripe.rotation.z = -0.45;
    stripe.position.set(index * 0.45 - 1.35, 0.9, 0.01);
    group.add(stripe);
  }
  group.position.set(x, 0, z);
  return group;
}
export function buildHeroRoadDetails(): THREE.Group {
  const group = new THREE.Group();
  group.name = "heroRoadDetails";
  for (let x = -displayLength / 2 + 4; x < displayLength / 2; x += 12)
    group.add(barrier(x, 19.5));
  const tile = new THREE.MeshStandardMaterial({
    color: 0x737e82,
    roughness: 0.9,
  });
  for (const z of [-18, 18])
    for (let x = -displayLength/2+1; x < displayLength/2; x += 2) {
      const seam = new THREE.Mesh(
        new THREE.BoxGeometry(0.025, 0.012, 3.7),
        tile,
      );
      seam.position.set(x, 0.512, z);
      group.add(seam);
    }
  const arrow = new THREE.Shape();
  arrow.moveTo(-0.13, -2);
  arrow.lineTo(0.13, -2);
  arrow.lineTo(0.13, 0.6);
  arrow.lineTo(0.75, 0.1);
  arrow.lineTo(0, 1.5);
  arrow.lineTo(-0.75, 0.1);
  arrow.lineTo(-0.13, 0.6);
  arrow.closePath();
  const geometry = new THREE.ShapeGeometry(arrow),
    paint = new THREE.MeshBasicMaterial({
      color: 0xecebe1,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
  for (const x of [-32, 6, 36])
    for (const z of [-10, 10]) {
      const mesh = new THREE.Mesh(geometry, paint);
      mesh.rotation.set(-Math.PI / 2, 0, z > 0 ? -Math.PI / 2 : Math.PI / 2);
      mesh.position.set(x, 0.07, z);
      group.add(mesh);
    }
  return group;
}
