import * as THREE from "three";
import { HERO } from "./config";

/** 按工程 X 范围裁剪真实折线；分离不连续段，避免把区段外路径连成假直线。 */
export function clipFiberSection(
  points: ReadonlyArray<{ x: number; y: number; z: number }>,
): THREE.Vector3[][] {
  const min = HERO.sourceCenterX - HERO.length / 2,
    max = HERO.sourceCenterX + HERO.length / 2;
  const sections: THREE.Vector3[][] = [];
  let section: THREE.Vector3[] = [];
  for (let index = 1; index < points.length; index++) {
    const sourceA = points[index - 1],
      sourceB = points[index];
    const a = new THREE.Vector3(sourceA.x, sourceA.y, sourceA.z),
      b = new THREE.Vector3(sourceB.x, sourceB.y, sourceB.z);
    const dx = b.x - a.x;
    let start = 0,
      end = 1;
    if (Math.abs(dx) < 1e-9) {
      if (a.x < min || a.x > max) {
        section = [];
        continue;
      }
    } else {
      const t1 = (min - a.x) / dx,
        t2 = (max - a.x) / dx;
      start = Math.max(0, Math.min(t1, t2));
      end = Math.min(1, Math.max(t1, t2));
      if (start > end) {
        section = [];
        continue;
      }
    }
    const entry = a.clone().lerp(b, start),
      exit = a.clone().lerp(b, end);
    if (entry.distanceToSquared(exit) < 1e-12) continue;
    if (
      !section.length ||
      section[section.length - 1].distanceToSquared(entry) > 1e-8
    ) {
      section = [entry];
      sections.push(section);
    }
    section.push(exit);
    if (end < 1) section = [];
  }
  return sections;
}
