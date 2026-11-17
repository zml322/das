/** 首页只呈现 100m 精细区段，业务里程仍保留完整工程范围。 */
export const HERO = {
  startChainage: 300,
  endChainage: 400,
  length: 100,
  width: 40,
  sourceCenterX: -105, // K0+350 在原工程坐标中为 350 - 455。
  excavationZ: 16.1,
  trenchFrontZ: 23,
  baseY: -18.4,
} as const;

export function insideHero(position: { x: number }): boolean {
  return (
    position.x >= HERO.sourceCenterX - HERO.length / 2 &&
    position.x <= HERO.sourceCenterX + HERO.length / 2
  );
}
