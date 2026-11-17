import * as THREE from "three";

export const HERO_GROUP_NAMES = [
  "envGroup",
  "heroRoadGroup",
  "geologyGroup",
  "sewerGroup",
  "fiberGroup",
  "vehicleGroup",
  "markerGroup",
  "effectGroup",
] as const;
export type HeroGroupName = (typeof HERO_GROUP_NAMES)[number];
export type HeroGroups = Record<HeroGroupName, THREE.Group>;

export function createHeroGroups(scene: THREE.Scene): HeroGroups {
  const groups = {} as HeroGroups;
  HERO_GROUP_NAMES.forEach((name) => {
    const group = new THREE.Group();
    group.name = name;
    groups[name] = group;
    scene.add(group);
  });
  return groups;
}
