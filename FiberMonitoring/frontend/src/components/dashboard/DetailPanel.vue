<template>
  <div class="detail-panel">
    <div v-if="fiber" class="fiber-details">
      <div class="detail-row">
        <span class="label">光纤编号:</span>
        <span class="value">{{ fiber.fiberId }}</span>
      </div>
      <div class="detail-row">
        <span class="label">光纤类型:</span>
        <span class="value">{{ fiber.fiberType }}</span>
      </div>
      <div class="detail-row">
        <span class="label">通道数量:</span>
        <span class="value">{{ fiber.channelCount }}</span>
      </div>
      <div class="detail-row">
        <span class="label">采样率:</span>
        <span class="value">{{ fiber.samplingRate }} Hz</span>
      </div>
      <div class="detail-row">
        <span class="label">空间间隔:</span>
        <span class="value">{{ fiber.spatialInterval }} m</span>
      </div>
      <div class="detail-row">
        <span class="label">监测里程:</span>
        <span class="value">{{ fiber.startChainage }} - {{ fiber.endChainage }} m</span>
      </div>
      <div class="detail-row">
        <span class="label">状态:</span>
        <span :class="['status-badge', `status-${fiber.status}`]">
          {{ fiber.status }}
        </span>
      </div>
    </div>

    <div v-else-if="selectedObject" class="object-details">
      <div class="detail-row">
        <span class="label">对象类型:</span>
        <span class="value">{{ selectedObject.type || '未知' }}</span>
      </div>
      <div class="detail-row">
        <span class="label">对象名称:</span>
        <span class="value">{{ selectedObject.label || selectedObject.name || '未命名' }}</span>
      </div>
    </div>

    <div v-else class="overview">
      <div class="info-text">
        点击场景中的对象查看详细信息
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Fiber } from '@/types/monitoring'

defineProps<{
  selectedObject: any
  fiber: Fiber | null
}>()
</script>

<style scoped>
.detail-panel {
  font-size: 14px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-row:last-child {
  border-bottom: none;
}

.label {
  color: var(--color-text-secondary);
}

.value {
  color: var(--color-text-primary);
  font-weight: 500;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.status-badge.status-online {
  background: var(--color-success);
  color: #000;
}

.status-badge.status-warning {
  background: var(--color-warning);
  color: #000;
}

.status-badge.status-offline {
  background: #666;
  color: #fff;
}

.overview,
.info-text {
  padding: 20px;
  text-align: center;
  color: var(--color-text-secondary);
}
</style>
