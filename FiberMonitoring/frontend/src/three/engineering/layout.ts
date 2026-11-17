import * as THREE from "three";
import { HERO } from "../hero/config";

/** Real engineering dimensions and presentation exaggeration are deliberately separate. */
export const ENGINEERING = {
  length: 910,
  width: 40,
  sidewalk: 4,
  carriageway: 12,
  median: 8,
};
export const DISPLAY = {
  longitudinal: 0.6,
  depth: 1.8,
  fiberRadius: 0.14,
  pipeCrossSection: 1.35,
  cutZ: 16.1,
  roadMedian: 3,
};
export const displayLength = HERO.length * DISPLAY.longitudinal;
export function toDisplay(point: {
  x: number;
  y: number;
  z: number;
}): THREE.Vector3 {
  return new THREE.Vector3(
    (point.x - HERO.sourceCenterX) * DISPLAY.longitudinal,
    point.y < 0 ? point.y * DISPLAY.depth : point.y,
    point.z,
  );
}
export function chainagePoint(
  chainage: number,
  depth = 0,
  z = 18.4,
): THREE.Vector3 {
  return toDisplay({ x: chainage - ENGINEERING.length / 2, y: -depth, z });
}
export const GEOLOGY = [
  { name: "路面结构层", depth: 0, thickness: 0.6, color: 0x626c78 },
  { name: "路基层 · 三合土", depth: 0.6, thickness: 0.9, color: 0xc19258 },
  { name: "杂填土层", depth: 1.5, thickness: 2.4, color: 0x976b42 },
  { name: "粉质黏土层", depth: 3.9, thickness: 3.8, color: 0x6b442c },
  { name: "粉砂层", depth: 7.7, thickness: 2.3, color: 0x41433c },
];
