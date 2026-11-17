<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.layers" />
  </svg>
</template>
<script setup lang="ts">
defineProps<{ name: string }>();
const paths: Record<string, string> = {
  home: "M3 11 12 3l9 8M5 10v11h5v-7h4v7h5V10",
  cube: "m12 2 9 5v10l-9 5-9-5V7l9-5Zm0 10 9-5M12 12 3 7m9 5v10",
  layers: "m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5",
  wave: "M2 12h4l2-8 4 16 3-12 2 4h5",
  fiber:
    "M21 5H9a5 5 0 0 0 0 10h9M21 9H9a1 1 0 0 0 0 2h9M7 18h14M19 3v4m0 10v4",
  pin: "M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 1 1 14 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  chart: "M3 3v18h18M7 16l4-6 4 3 6-9",
  car: "m4 9 2-5h12l2 5M3 10h18v8H3v-8ZM5 18v3m14-3v3M6 14h2m8 0h2",
  alert: "m12 3 10 18H2L12 3Zm0 6v5m0 3v1",
  device: "M8 3h8v13H8V3Zm4 13v6M4 7H2m20 0h-2M4 11H2m20 0h-2",
  file: "M4 2h11l5 5v15H4V2Zm10 0v6h6M8 12h8m-8 4h8",
  settings:
    "m9 3-1 3-3 1-2 4 2 2v4l4 2 3-1 3 1 4-2v-4l2-2-2-4-3-1-1-3H9Zm7 9a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  bell: "M4 17h16l-2-3V9a6 6 0 0 0-12 0v5l-2 3Zm5 3h6",
  road: "m8 2-5 20m13-20 5 20M12 3v4m0 4v3m0 4v4",
  pipe: "M7 3h14v16H7M7 3a4 8 0 1 0 0 16 4 8 0 1 0 0-16Z",
  expand: "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5",
  play: "m8 4 12 8-12 8V4Z",
  pause: "M8 4v16M16 4v16",
  close: "m5 5 14 14M19 5 5 19",
  sun: "M12 3V1m0 22v-2M3 12H1m22 0h-2M5 5 3 3m18 18-2-2M5 19l-2 2M21 3l-2 2M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0Z",
};
</script>
<style scoped>
svg {
  width: 1.35em;
  height: 1.35em;
  flex-shrink: 0;
  vertical-align: middle;
}
</style>
