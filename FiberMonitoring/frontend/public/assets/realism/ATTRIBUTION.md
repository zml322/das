# Local scene assets

Providers: Poly Haven and Innerscene. All listed source assets are CC0.
Poly Haven license: https://polyhaven.com/license

- Asphalt: https://polyhaven.com/a/asphalt_02
- Soil: https://polyhaven.com/a/brown_mud_02
- Gravel/clay: https://polyhaven.com/a/brown_mud_rocks_01
- Sand: https://polyhaven.com/a/gravelly_sand
- Roadside tree geometry/textures: https://polyhaven.com/a/tree_small_02
- Legacy foliage asset: https://polyhaven.com/a/shrub_03 (not loaded by the current scene)
- Daylight HDR: https://polyhaven.com/a/kloppenheim_06_puresky

Downloaded at 1k on 2026-11-16/17. `manifest.json` and `terrain-sources.json` record original download URLs
and upstream MD5 checksums, checked after download. `tree/SOURCE.json` records the
tree's original files and checksums, plus the optimized GLB's SHA-256. The tree was
welded, simplified with glTF Transform / meshoptimizer, deduplicated and pruned:
2,062,487 original triangles became 51,272 triangles for the near tree and 6,315
for the far tree. Both LOD scenes share embedded textures in one 8,750,000-byte GLB.
Trees are spatially clustered, frustum culled and switched by distance at runtime.

Vehicle source models by Innerscene, released under CC0-1.0:

- Sedan: https://www.innerscene.com/tools/library/3d-parts/graphite-four-door-sedan-eed96d12
- Truck: https://www.innerscene.com/tools/library/3d-parts/7-5-t-class-box-truck-with-roll-up-door-12baea66
- Bus: https://www.innerscene.com/tools/library/3d-parts/midi-bus-10-5-m-b18bf6f2
- Terms: https://www.innerscene.com/tools/library/terms
- CC0 dedication: https://creativecommons.org/publicdomain/zero/1.0/

`vehicles/SOURCE.json` records each original download URL/hash and the bundled
derivative hash/size. Meshes were flattened and joined by material; the sedan and
truck were simplified with a geometric error limit of 0.0015. The sedan has 56,964
triangles, the truck 68,832 and the bus 6,720. Runtime recolors paint, normalizes
ground contact and corrects the different source forward axes. The code-built
vehicles remain as complete loading-failure fallbacks.

Additional broadleaf cards, sky, metal roughness, buildings, strata clods and
scene geometry are generated in project code. These files are served from
the bundled app; normal runtime does not request the provider's servers.
