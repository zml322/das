<template>
  <div class="monitoring-chart">
    <h3>{{ title }}<small>{{ subtitle }}</small></h3>
    <svg v-if="kind !== 'risk'" viewBox="0 0 460 140" preserveAspectRatio="none" role="img" :aria-label="chartLabel">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop stop-color="#04c7f5" stop-opacity=".5" /><stop offset="1" stop-color="#04c7f5" stop-opacity=".02" />
        </linearGradient>
        <linearGradient :id="gradientId + '-bar'" x1="0" y1="0" x2="0" y2="1">
          <stop stop-color="#22d7ff" /><stop offset="1" stop-color="#008bd1" />
        </linearGradient>
      </defs>
      <path d="M40 10H452M40 60H452M40 110H452M40 10V110" stroke="#22506e" stroke-width=".8" fill="none" />
      <template v-if="kind === 'line'">
        <path :d="area" :fill="'url(#' + gradientId + ')'" />
        <path :d="line" fill="none" stroke="#08dcff" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
      </template>
      <g v-else>
        <rect v-for="(value, index) in values" :key="index"
          :x="44 + index * 404 / Math.max(1, values.length)"
          :y="110 - Math.max(0, value) / maximum * 100"
          :width="Math.max(1, 244 / Math.max(1, values.length))"
          :height="Math.max(0, value) / maximum * 100"
          :fill="'url(#' + gradientId + '-bar)'">
          <title>{{ index }}:00，{{ value }} 次事件</title>
        </rect>
      </g>
      <g fill="#bdcfe2" font-size="15" font-family="Microsoft YaHei, sans-serif">
        <text x="33" y="15" text-anchor="end">{{ tick(maximum) }}</text>
        <text x="33" y="65" text-anchor="end">{{ kind === 'line' ? '0' : tick(maximum / 2) }}</text>
        <text x="33" y="115" text-anchor="end">{{ kind === 'line' ? '−' + tick(maximum) : '0' }}</text>
        <template v-if="kind === 'line'">
          <text v-for="index in 4" :key="index" :x="40 + (index - 1) * 412 / 3" y="135"
            :text-anchor="index === 1 ? 'start' : index === 4 ? 'end' : 'middle'">{{ (wave.duration * (index - 1) / 3).toFixed(1) }} s</text>
        </template>
        <template v-else>
          <text v-for="(hour, index) in [0, 4, 8, 12, 16, 20]" :key="hour"
            :x="43 + index * 404 / 6" y="135" :text-anchor="index === 0 ? 'start' : 'middle'">{{ String(hour).padStart(2, '0') }}:00</text>
        </template>
      </g>
    </svg>
    <div v-else class="risk-chart" role="img" :aria-label="'各区段风险等级：' + values.join('、')">
      <div class="risk-segments">
        <span v-for="(value, index) in values" :key="index" :style="{ background: riskColors[value] ?? riskColors[0] }"
          :title="'区段 ' + (index + 1) + '，风险等级 ' + value" />
        <svg v-if="highestRisk > 0" class="risk-location" viewBox="0 0 24 30" :style="{ left: (riskIndex + .5) / values.length * 100 + '%' }" aria-hidden="true">
          <path d="M12 29S2 16 2 11a10 10 0 1 1 20 0c0 5-10 18-10 18Z" fill="#e6f2ff" /><circle cx="12" cy="11" r="4" fill="#26405f" />
        </svg>
      </div>
      <div class="risk-axis"><span>K0+000</span><span>K0+300</span><span>K0+600</span><span>K0+910</span></div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, useId } from 'vue';
import { waveformWindow, chartMaximum } from '@/utils/chartSeries';
const props = withDefaults(defineProps<{ title: string; subtitle?: string; kind: 'line' | 'bar' | 'risk'; values: number[]; samplingRate?: number }>(), { samplingRate: 1000 });
const gradientId = 'telemetry-' + useId();
const wave = computed(() => waveformWindow(props.values, props.samplingRate));
const maximum = computed(() => chartMaximum(props.kind === 'line' ? wave.value.points.map(p => p.value) : props.values));
const projected = computed(() => wave.value.points.map(p => ({
  x: 40 + p.index / Math.max(1, wave.value.count - 1) * 412,
  y: 60 - p.value / maximum.value * 50,
})));
const line = computed(() => projected.value.map((p, i) => (i ? 'L' : 'M') + p.x.toFixed(2) + ',' + p.y.toFixed(2)).join(' ') || 'M40 60L452 60');
const area = computed(() => {
  const points = projected.value;
  return line.value + ' L' + (points[points.length - 1]?.x ?? 452) + ' 60 L' + (points[0]?.x ?? 40) + ' 60 Z';
});
const tick = (value: number) => value >= 10 ? value.toFixed(0) : value.toFixed(1);
const riskColors = ['#2eeb87', '#a4df53', '#f1ce4b', '#f39340', '#f74b59'];
const highestRisk = computed(() => Math.max(0, ...props.values));
const riskIndex = computed(() => props.values.indexOf(highestRisk.value));
const chartLabel = computed(() => props.kind === 'line' ? props.title + '，最近' + wave.value.duration.toFixed(1) + '秒，纵轴单位 mV' : props.title + '，按小时统计最近事件');
</script>
