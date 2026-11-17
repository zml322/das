import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { buildSewer } from "../engineering/SewerBuilder";
import { HERO } from "./config";
import { DISPLAY, displayLength } from '../engineering/layout';
import { createMetalRoughness } from '../engineering/MetalSurface';

/** 三段实体管壁，中段开启观察窗；水面、内壁与管接头仍是真实几何。 */
function inspectionWall(radius: number, length: number): THREE.BufferGeometry {
  const windowLength = 72 * DISPLAY.longitudinal,
    sideLength = (length - windowLength) / 2;
  const parts = [
    [-(length + windowLength) / 4, sideLength, 0, Math.PI * 2],
    [0, windowLength, Math.PI * 1.5, Math.PI * 1.5],
    [(length + windowLength) / 4, sideLength, 0, Math.PI * 2],
  ].map(([center, height, start, angle]) => {
    const geometry = new THREE.CylinderGeometry(
      radius,
      radius,
      height,
      64,
      1,
      true,
      start,
      angle,
    );
    geometry.rotateX(Math.PI / 2);
    geometry.translate(0, 0, center);
    return geometry;
  });
  const geometry = mergeGeometries(parts)!;
  parts.forEach((part) => part.dispose());
  return geometry;
}
export function buildHeroSewer(): THREE.Group {
  const pipe = buildSewer(
    { x: HERO.sourceCenterX - 50, y: -6.4, z: 19.6 },
    { x: HERO.sourceCenterX + 50, y: -6.4, z: 19.6 },
    "PIPE-001",
  );
  const core = pipe.getObjectByName("pipeCylinder") as THREE.Mesh<
    THREE.BufferGeometry,
    THREE.MeshStandardMaterial
  >;
  const old = core.geometry;
  core.geometry = inspectionWall(2.25, displayLength);
  old.dispose();
  core.material.color.setHex(0x8196a3);
  core.material.roughness = 0.6;
  core.material.roughnessMap = createMetalRoughness();
  core.material.metalness = 0.85;
  pipe.children.forEach((child) => {
    if (
      child instanceof THREE.Mesh &&
      child.material instanceof THREE.MeshStandardMaterial &&
      child.material.side === THREE.BackSide
    ) {
      child.geometry.dispose();
      child.geometry = inspectionWall(2.03, displayLength);
    }
  });
  const scan = pipe.getObjectByName("pathEffects") as THREE.Mesh<
    THREE.BufferGeometry,
    THREE.ShaderMaterial
  >;
  scan.geometry.dispose();
  scan.geometry = inspectionWall(2.28, displayLength);
  scan.material.vertexShader = scan.material.vertexShader.replace(
    "vUv=uv;",
    `vUv=vec2((position.z+${displayLength / 2}.0)/${displayLength}.0,uv.x);`,
  );
  scan.material.needsUpdate = true;
  pipe.userData.inspectionWindow = { start: -36 * DISPLAY.longitudinal, end: 36 * DISPLAY.longitudinal };
  pipe.userData.sourceRange = [HERO.startChainage, HERO.endChainage];
  pipe.userData.pipeInfo.length = HERO.length;
  pipe.scale.set(DISPLAY.pipeCrossSection, DISPLAY.pipeCrossSection, 1);
  pipe.userData.presentationCrossSectionScale = DISPLAY.pipeCrossSection;
  return pipe;
}
