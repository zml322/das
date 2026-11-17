// 将数据状态同步到已有模型，按业务 ID 复用标记。
import * as THREE from "three";
import type { Fiber, Device, MonitoringEvent } from "@/types/monitoring";
import { FiberBuilder, FiberStatus } from "../models/FiberBuilder";
import { disposeObject, createMarker, emphasizeMarker } from "../effects/PathEffects";
import { toDisplay } from "../engineering/layout";
import type { SceneAnnotations } from "../engineering/SceneAnnotations";
import { insideHero } from "../hero/config";
interface SceneGroups {
  fiberGroup: THREE.Group;
  markerGroup: THREE.Group;
}
function nearestOnCurve(
  curve: THREE.Curve<THREE.Vector3>,
  target: THREE.Vector3,
): THREE.Vector3 {
  let nearest = new THREE.Vector3(),
    distance = Infinity;
  for (let index = 0; index <= 1000; index++) {
    const point = curve.getPointAt(index / 1000),
      candidate = point.distanceToSquared(target);
    if (candidate < distance) {
      distance = candidate;
      nearest = point;
    }
  }
  return nearest;
}
function syncFibers(groups: SceneGroups, fibers: Fiber[]): void {
  for (const fiber of fibers) {
    const models = groups.fiberGroup.children.filter(
      (child) => child.userData.fiberId === fiber.fiberId,
    ) as THREE.Group[];
    const status =
      fiber.status === "offline"
        ? FiberStatus.OFFLINE
        : fiber.status === "error"
          ? FiberStatus.ALERT
          : fiber.status === "warning"
            ? FiberStatus.WARNING
            : FiberStatus.NORMAL;
    models.forEach((model) => {
      if (model.userData.fiberInfo.status !== status)
        FiberBuilder.updateStatus(model, status);
    });
  }
}
function syncDevices(groups: SceneGroups, devices: Device[]): void {
  for (const device of devices) {
    const marker = groups.markerGroup.getObjectByName(device.deviceId);
    if (!marker) continue;
    marker.userData.inHero = Boolean(
      device.position && insideHero(device.position),
    );
    marker.userData.active = device.online;
    if (device.position) marker.position.copy(toDisplay(device.position));
    marker.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        const mat = child.material as THREE.MeshStandardMaterial;
        mat.color.setHex(device.online ? 0x44dbaa : 0x666666);
        if (mat.emissive) mat.emissive.copy(mat.color);
      }
    });
  }
}
function syncEvents(
  groups: SceneGroups,
  annotations: SceneAnnotations,
  events: MonitoringEvent[],
): void {
  // Remove resolved/expired markers; reconcile by ID to avoid per-update allocation.
  const active = events.filter(
    (event) =>
      event.status !== "resolved" &&
      event.severity !== "info" &&
      insideHero(event.position),
  );
  const labelledEvents = new Set(
    [...active]
      .sort((a, b) => {
        const levels = ["critical", "high", "medium", "low"];
        return levels.indexOf(a.severity) - levels.indexOf(b.severity);
      })
      .slice(0, 3)
      .map((event) => event.eventId),
  );
  for (const marker of [...groups.markerGroup.children]) {
    if (
      marker.userData.eventId &&
      !active.some((event) => event.eventId === marker.userData.eventId)
    )
      disposeObject(marker);
  }
  for (const event of active) {
    const models = groups.fiberGroup.children.filter(
      (child) => child.userData.fiberId === event.fiberId,
    );
    if (!models.length) continue;
    const target = toDisplay(event.position);
    const candidates = models.map((model) =>
      nearestOnCurve(
        model.userData.curve as THREE.Curve<THREE.Vector3>,
        target,
      ),
    );
    const nearest = candidates.reduce((a, b) =>
      a.distanceToSquared(target) < b.distanceToSquared(target) ? a : b,
    );
    let marker = groups.markerGroup.children.find(
      (child) => child.userData.eventId === event.eventId,
    );
    const color = ["high", "critical"].includes(event.severity)
      ? 0xff536a
      : 0xffba52;
    if (!marker) {
      marker = createMarker(nearest, color);
      marker.name = event.eventName;
      marker.userData = {
        ...marker.userData,
        eventId: event.eventId,
        fiberId: event.fiberId,
        clickable: true,
      };
      groups.markerGroup.add(marker);
    }
    marker.position.copy(nearest);
    if (!marker.userData.labelled && labelledEvents.has(event.eventId)) {
      emphasizeMarker(marker,color);
      annotations.add(event.eventName, marker.position, marker, "red", -42);
      marker.userData.labelled = true;
    }
    marker.userData.labelVisible = labelledEvents.has(event.eventId);
    marker.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        const mat = child.material as THREE.MeshStandardMaterial;
        mat.color.setHex(color);
        if (mat.emissive) mat.emissive.setHex(color);
      }
    });
  }
}
export function syncSceneMonitoring(
  groups: SceneGroups,
  annotations: SceneAnnotations,
  fibers: Fiber[],
  devices: Device[],
  events: MonitoringEvent[],
): void {
  syncFibers(groups, fibers);
  syncDevices(groups, devices);
  syncEvents(groups, annotations, events);
}
