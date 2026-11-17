import * as THREE from "three";
import { GEOLOGY, DISPLAY, displayLength } from "./layout";
import { createSurfaceTexture } from "./SurfaceTextures";
import { createStrataDetails } from './StrataDetails';

export function buildGeology(): THREE.Group {
  const group = new THREE.Group();
  group.name = "underground";
  const width = DISPLAY.cutZ + 20;
  GEOLOGY.forEach((layer, index) => {
    const height = layer.thickness * DISPLAY.depth;
    const material = new THREE.MeshStandardMaterial({
      color: layer.color,
      map: createSurfaceTexture("soil", index + 17),
      roughness: 1,
      transparent: false,
      opacity: 1,
    });
    const geometry = new THREE.BoxGeometry(
      displayLength + 500, // 土层连续到精细监测区之外，避免剖面边缘露出天空。
      height,
      width,
      290,
      10,
      1,
    );
    const positions = geometry.attributes.position;
    for (let vertex = 0; vertex < positions.count; vertex++) {
      if (positions.getZ(vertex) < width / 2 - 0.001) continue;
      const x = positions.getX(vertex),
        y = positions.getY(vertex);
      const edge = Math.sin(Math.PI * (y / height + 0.5));
      positions.setZ(
        vertex,
        width / 2 - edge * (.22+.12*Math.sin(x*3.7+y*7.1)+.04*Math.sin(x*13.1-y*5.3)),
      );
    }
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(
      0,
      -(layer.depth + layer.thickness / 2) * DISPLAY.depth,
      (DISPLAY.cutZ - 20) / 2,
    );
    mesh.name = layer.name;
    mesh.userData = { clickable: true, layerInfo: layer };
    mesh.receiveShadow = true;
    mesh.add(createStrataDetails(height,width,index));
    group.add(mesh);
  });
  return group;
}
