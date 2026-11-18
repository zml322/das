<template>
  <div id="app">
    <div v-if="route.path !== '/'" class="monitoring-dashboard business-shell">
      <PlatformHeader :alarms="store.overview?.activeAlarms ?? 0" />
      <div class="business-content"><RouterView /></div>
    </div>
    <RouterView v-else />
  </div>
</template>

<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import PlatformHeader from '@/components/dashboard/PlatformHeader.vue'
import { useMonitoringStore } from '@/stores/monitoring'
import '@/assets/styles/dashboard.css'
const route = useRoute()
const store = useMonitoringStore()
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  font-family: 'Microsoft YaHei', Arial, sans-serif;
  color: #e0e0e0;
}
</style>

<style>
.monitoring-dashboard.business-shell { grid-template-rows: calc(88 * var(--ui-unit)) minmax(0, 1fr); gap: 0; padding-bottom: 0; }
.business-content { min-height: 0; overflow: auto; }
.business-content > div { min-height: 100%; height: auto; }
</style>
