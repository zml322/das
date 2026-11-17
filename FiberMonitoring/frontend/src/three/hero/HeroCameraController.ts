import * as THREE from "three";
import { gsap } from "gsap";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export type HeroView =
  | "overview"
  | "top"
  | "underground"
  | "cross"
  | "longitudinal";
export const HERO_VIEWS: Record<
  HeroView,
  { position: [number, number, number]; target: [number, number, number] }
> = {
  overview: { position: [-42, 12, 60], target: [0, -6, 10] },
  top: { position: [0, 85, 0.1], target: [0, 0, 0] },
  underground: { position: [-32, 6, 60], target: [0, -7, 18] },
  cross: { position: [-75, 3, 32], target: [-18, -8, 18] },
  longitudinal: { position: [0, 8, 80], target: [0, -5, 13] },
};

/** 用一个暂停的 GSAP timeline，由场景时钟推进，避免新增 RAF。 */
export class HeroCameraController {
  private transition: gsap.core.Timeline | null = null;
  private elapsed = 0;
  private view: HeroView = "overview";
  private cancelOnInput = () => this.cancel();
  constructor(
    private camera: THREE.PerspectiveCamera,
    private controls: OrbitControls,
    private reducedMotion = false,
  ) {
    controls.addEventListener("start", this.cancelOnInput);
  }
  get currentView(): HeroView {
    return this.view;
  }
  get transitioning(): boolean {
    return this.transition !== null;
  }
  setView(view: HeroView, animate = true): void {
    this.view = view;
    const preset = HERO_VIEWS[view],
      position = new THREE.Vector3().fromArray(preset.position),
      target = new THREE.Vector3().fromArray(preset.target);
    const scale = Math.max(1, 1.65 / Math.max(this.camera.aspect, 0.65));
    position.sub(target).multiplyScalar(scale).add(target);
    this.moveTo(position, target, animate);
  }
  focus(object: THREE.Object3D, distance = 45): void {
    const target = new THREE.Box3()
      .setFromObject(object)
      .getCenter(new THREE.Vector3());
    const position = target
      .clone()
      .add(new THREE.Vector3(-distance * 0.6, distance * 0.5, distance));
    this.moveTo(position, target, true);
  }
  update(delta: number): void {
    if (!this.transition) return;
    const timeline = this.transition;
    this.elapsed += Math.min(delta, 0.1);
    timeline.render(Math.min(this.elapsed, timeline.duration()), false, true);
    if (this.elapsed >= timeline.duration()) this.finish();
  }
  cancel(): void {
    this.transition?.kill();
    this.transition = null;
    this.controls.enableDamping = true;
  }
  dispose(): void {
    this.cancel();
    this.controls.removeEventListener("start", this.cancelOnInput);
  }
  private finish(): void {
    this.transition?.kill();
    this.transition = null;
    this.controls.enableDamping = true;
    this.controls.update();
  }
  private moveTo(
    position: THREE.Vector3,
    target: THREE.Vector3,
    animate: boolean,
  ): void {
    this.cancel();
    // 清掉 OrbitControls 剩余阻尼，确保连续点按视角时不会漂移。
    this.controls.enableDamping = false;
    this.controls.update();
    if (!animate || this.reducedMotion) {
      this.camera.position.copy(position);
      this.controls.target.copy(target);
      this.finish();
      return;
    }
    this.elapsed = 0;
    this.transition = gsap
      .timeline({
        paused: true,
        defaults: { duration: 1.15, ease: "power2.inOut" },
      })
      .to(
        this.camera.position,
        { x: position.x, y: position.y, z: position.z },
        0,
      )
      .to(this.controls.target, { x: target.x, y: target.y, z: target.z }, 0);
  }
}
