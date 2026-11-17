<template>
  <section class="instrument-panel resource-panel">
    <h2><AppIcon name="layers" />场景资源<button class="resource-detail-toggle" aria-label="查看光纤明细" :aria-expanded="fibersExpanded" aria-controls="fiber-resources" @click="fibersExpanded = !fibersExpanded"><AppIcon name="fiber" /></button></h2>
    <div class="resource-content">
    <button
      class="tree-root"
      @click="expanded = !expanded"
      :aria-expanded="expanded"
    >
      <span>{{ expanded ? "▾" : "▸" }}</span
      ><AppIcon name="file" /><span class="tree-root-name">工程场景</span>
    </button>
    <div v-if="expanded" class="resource-tree">
      <button
        v-for="item in resources"
        :key="item.key"
        @click="emit('focus', item.key)"
      >
        <AppIcon :name="item.icon" />{{ item.label }}<i class="online-dot" />
      </button>
      <div v-if="fibersExpanded" id="fiber-resources" class="fiber-resources">
        <button
          v-for="fiber in fibers"
          :key="fiber.fiberId"
          @click="emit('fiber', fiber.fiberId)"
        >
          <i :style="{ background: fiber.color }" />{{ fiber.fiberName }}
        </button>
      </div>
    </div>
    </div>
  </section>
</template>
<script setup lang="ts">
import { ref } from "vue";
import type { Fiber } from "@/types/monitoring";
import AppIcon from "./AppIcon.vue";
defineProps<{ fibers: Fiber[] }>();
const emit = defineEmits<{ focus: [key: string]; fiber: [id: string] }>();
const expanded = ref(true);
const fibersExpanded = ref(false);
const resources = [
  { key: "road", label: "道路场景", icon: "road" },
  { key: "underground", label: "地下土层", icon: "layers" },
  { key: "pipe", label: "排污管道", icon: "pipe" },
  { key: "fiber", label: "光纤网络", icon: "fiber" },
];
</script>
