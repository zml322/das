import * as THREE from "three";
import type { Fiber } from "@/types/monitoring";
import { FiberBuilder, FiberStatus } from "../models/FiberBuilder";
import { clipFiberSection } from "./FiberSection";
import { toDisplay, DISPLAY } from "../engineering/layout";
import type { SceneManager } from "../core/SceneManager";

export const HERO_FIBER_COLORS: Record<string, string> = {
  DAS: "#ff393d",
  DSS: "#00baff",
  COMM: "#16ed72",
  BURIED: "#55d9a0",
};
export function addHeroFibers(manager: SceneManager, fibers: Fiber[]): void {
  fibers.forEach((fiber) =>
    clipFiberSection(fiber.path3D).forEach((section, index) => {
      const status =
        fiber.status === "offline"
          ? FiberStatus.OFFLINE
          : fiber.status === "warning"
            ? FiberStatus.WARNING
            : fiber.status === "error"
              ? FiberStatus.ALERT
              : FiberStatus.NORMAL;
      const color = HERO_FIBER_COLORS[fiber.fiberType];
      const model = FiberBuilder.build({
        id: fiber.fiberId,
        name: fiber.fiberName,
        pathPoints: section.map(toDisplay),
        radius: fiber.fiberType === 'BURIED' ? DISPLAY.fiberRadius*.5 : DISPLAY.fiberRadius,
        status,
        glowIntensity: fiber.fiberType === 'BURIED' ? .6 : 1.5,
        tubularSegments: 240,
      });
      Object.assign(model.userData, {
        fiberId: fiber.fiberId,
        fiberType: fiber.fiberType,
        baseColor: color,
        sectionIndex: index,
      });
      // Metadata remains in source metres even when the visual longitudinal axis is compressed.
      model.userData.fiberInfo.length = section.slice(1).reduce((length, point, i) => length + point.distanceTo(section[i]), 0);
      if (status === FiberStatus.NORMAL) {
        const core = model.getObjectByName("fiberCore") as THREE.Mesh<
          THREE.BufferGeometry,
          THREE.MeshStandardMaterial
        >;
        core.material.color.set(color).multiplyScalar(.2);
        core.material.emissive.set(color);
        core.material.emissiveIntensity = 1.5;
        core.material.metalness = 0;
        core.material.toneMapped = false;
        (
          model.getObjectByName("pathEffects") as THREE.Mesh<
            THREE.BufferGeometry,
            THREE.ShaderMaterial
          >
        ).material.uniforms.uColor.value.set(color);
        (model.getObjectByName('pathEffects') as THREE.Mesh<THREE.BufferGeometry, THREE.ShaderMaterial>).material.toneMapped = false;
      }
      manager.fiberGroup.add(model);
      if (index === 0 && fiber.fiberType !== "BURIED") {
        const curve = model.userData.curve as THREE.Curve<THREE.Vector3>;
        manager.annotations.add(
          fiber.fiberType === "DAS"
            ? "DAS 声学监测光纤"
            : fiber.fiberType === "DSS"
              ? "DSS 应变监测光纤"
              : "通信光缆",
          curve.getPointAt(0.88),
          model,
          fiber.fiberType === "DAS"
            ? "red"
            : fiber.fiberType === "DSS"
              ? "cyan"
              : "green",
          fiber.fiberType === "DAS"
            ? -58
            : fiber.fiberType === "DSS"
              ? -17
              : 24,
          22,
          { dock: 'right', rank: fiber.fiberType === 'DAS' ? 0 : fiber.fiberType === 'DSS' ? 1 : 2 },
        );
      }
    }),
  );
}
