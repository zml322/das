<template>
  <svg class="metric-icon" viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <defs>
      <linearGradient :id="id + '-metal'" x1="12" y1="8" x2="48" y2="58" gradientUnits="userSpaceOnUse">
        <stop stop-color="#f2f4ff" /><stop offset=".48" stop-color="#b7b9df" /><stop offset="1" stop-color="#646eaa" />
      </linearGradient>
      <linearGradient :id="id + '-red'" x1="20" y1="8" x2="42" y2="47" gradientUnits="userSpaceOnUse">
        <stop stop-color="#ff92b8" /><stop offset=".45" stop-color="#f93e6d" /><stop offset="1" stop-color="#aa1e42" />
      </linearGradient>
      <linearGradient :id="id + '-gold'" x1="18" y1="8" x2="43" y2="57" gradientUnits="userSpaceOnUse">
        <stop stop-color="#fff3a3" /><stop offset=".55" stop-color="#ffd362" /><stop offset="1" stop-color="#db8b28" />
      </linearGradient>
      <linearGradient :id="id + '-blue'" x1="18" y1="8" x2="42" y2="53" gradientUnits="userSpaceOnUse">
        <stop stop-color="#d8f6ff" /><stop offset="1" stop-color="#509bd4" />
      </linearGradient>
    </defs>
    <g v-if="name === 'device'" stroke-linecap="round" stroke-linejoin="round">
      <path d="m27 40-9 16h31L37 41" :fill="metal" stroke="#d0d7f6" stroke-width="1.4" />
      <path d="M14 17c-8 18 11 36 27 25L14 17Z" :fill="metal" stroke="#d8e4ff" stroke-width="2" />
      <path d="m19 23 23-9M32 30l10-16" stroke="#e3eaff" stroke-width="3" />
      <circle cx="43" cy="13" r="4" fill="#8bd7ff" />
      <path d="M46 7c8 1 13 8 11 15M47 1c13 2 21 13 17 24" stroke="#54bdec" stroke-width="2.5" />
      <path d="M20 57h29" stroke="#ebefff" stroke-width="3" />
    </g>
    <g v-else-if="name === 'fiber'" stroke-linejoin="round">
      <path d="M23 5v12m17-12v12" stroke="#f9dc98" stroke-width="5" />
      <path d="M18 17h28v17l-7 8H25l-7-8V17Z" :fill="metal" stroke="#a5b7f0" stroke-width="2" />
      <path d="M27 42h10v12H27z" fill="#8382bd" />
      <path d="M32 53v9" stroke="#a4a7d4" stroke-width="6" />
      <path d="M25 23v8m8-8v8m7-8v8" stroke="#655e96" stroke-width="2" />
      <path d="M20 19h24" stroke="#ded7ff" stroke-width="2" />
    </g>
    <g v-else-if="name === 'pin'">
      <path d="M31 36v24" stroke="#cfb7c6" stroke-width="5" /><path d="M30 39v21" stroke="#fff1f5" stroke-width="1.5" />
      <ellipse cx="32" cy="22" rx="18" ry="21" :fill="red" stroke="#ff638d" stroke-width="1.2" />
      <ellipse cx="26" cy="14" rx="5" ry="6" fill="#ffe4ec" opacity=".9" />
    </g>
    <g v-else-if="name === 'chart'">
      <rect x="7" y="7" width="50" height="51" rx="8" :fill="metal" stroke="#c1dcf2" stroke-width="2" />
      <rect x="12" y="29" width="11" height="25" rx="2" fill="#71d58d" />
      <rect x="26" y="18" width="11" height="36" rx="2" fill="#64c4ec" />
      <rect x="40" y="10" width="11" height="44" rx="2" fill="#8b9ae6" />
      <path d="M11 11h8v10" stroke="#eef8ff" stroke-width="2" opacity=".7" />
    </g>
    <g v-else-if="name === 'car'" stroke-linejoin="round">
      <circle cx="17" cy="49" r="8" fill="#172a43" stroke="#8dabc5" stroke-width="2" />
      <circle cx="49" cy="49" r="8" fill="#172a43" stroke="#8dabc5" stroke-width="2" />
      <path d="m9 31 8-17h26l11 17 6 4v13H5V35l4-4Z" :fill="red" stroke="#f57c90" stroke-width="2" />
      <path d="m19 18-6 14h17V18H19Zm15 0v14h15l-9-14h-6Z" :fill="blue" stroke="#294e73" stroke-width="1.5" />
      <path d="M7 38h8m36 0h7" stroke="#ffe9a6" stroke-width="4" />
      <path d="M19 48h25" stroke="#a8264e" stroke-width="2" />
    </g>
    <g v-else>
      <path d="M28 8c2-4 6-4 8 0l25 44c2 4 0 7-5 7H8c-5 0-7-3-5-7L28 8Z" :fill="gold" stroke="#fff0a5" stroke-width="2" />
      <path d="M32 23v16" stroke="#68451d" stroke-width="6" stroke-linecap="round" />
      <circle cx="32" cy="49" r="3.5" fill="#68451d" />
    </g>
  </svg>
</template>
<script setup lang="ts">
import { useId } from 'vue';
defineProps<{ name: string }>();
const id = 'metric-' + useId();
const metal = `url(#${id}-metal)`, red = `url(#${id}-red)`, gold = `url(#${id}-gold)`, blue = `url(#${id}-blue)`;
</script>
