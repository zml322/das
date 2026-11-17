<template>
  <div class="event-view">
    <div class="view-header">
      <h2 class="view-title">事件管理</h2>
      <div class="view-actions">
        <button class="btn btn-primary" @click="createEvent">
          新建事件
        </button>
        <button class="btn" @click="refreshEvents">
          刷新
        </button>
      </div>
    </div>

    <div class="filter-bar">
      <div class="filter-group">
        <label class="filter-label">状态:</label>
        <select v-model="statusFilter" class="select-input">
          <option value="all">全部</option>
          <option value="active">活动中</option>
          <option value="processing">处理中</option>
          <option value="resolved">已解决</option>
          <option value="closed">已关闭</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">严重等级:</label>
        <select v-model="severityFilter" class="select-input">
          <option value="all">全部</option>
          <option value="critical">严重</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
          <option value="info">信息</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">事件类型:</label>
        <select v-model="typeFilter" class="select-input">
          <option value="all">全部</option>
          <option value="vehicle_pass">车辆经过</option>
          <option value="vehicle_anomaly">车辆异常</option>
          <option value="construction">施工扰动</option>
          <option value="pipe_vibration">管道振动</option>
          <option value="fiber_offline">光纤离线</option>
        </select>
      </div>

      <div class="search-group">
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索事件ID、描述..."
          class="search-input"
        />
      </div>

      <button class="btn btn-primary" @click="applyFilter">
        应用筛选
      </button>
    </div>

    <div class="content-area">
      <div class="events-grid">
        <div
          v-for="event in filteredEvents"
          :key="event.id"
          class="event-card"
          :class="`severity-${event.severity}`"
          @click="selectEvent(event)"
        >
          <div class="event-header">
            <div class="event-id">{{ event.eventId }}</div>
            <div class="event-status" :class="`status-${event.status}`">
              {{ getStatusLabel(event.status) }}
            </div>
          </div>

          <div class="event-title">{{ event.eventName }}</div>

          <div class="event-meta">
            <div class="meta-item">
              <span class="meta-icon">📍</span>
              <span class="meta-text">{{ event.location }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-icon">🕐</span>
              <span class="meta-text">{{ formatTime(event.startTime) }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-icon">⚡</span>
              <span class="meta-text">{{ event.eventType }}</span>
            </div>
          </div>

          <div class="event-footer">
            <span class="severity-badge" :class="`badge-${event.severity}`">
              {{ getSeverityLabel(event.severity) }}
            </span>
            <span class="confidence">置信度: {{ (event.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>

      <div v-if="selectedEvent" class="event-detail-panel">
        <div class="detail-header">
          <h3>事件详情</h3>
          <button class="btn-close" @click="selectedEvent = null">✕</button>
        </div>

        <div class="detail-content">
          <div class="detail-section">
            <h4>基本信息</h4>
            <div class="detail-row">
              <span class="label">事件ID:</span>
              <span class="value">{{ selectedEvent.eventId }}</span>
            </div>
            <div class="detail-row">
              <span class="label">事件名称:</span>
              <span class="value">{{ selectedEvent.eventName }}</span>
            </div>
            <div class="detail-row">
              <span class="label">事件类型:</span>
              <span class="value">{{ selectedEvent.eventType }}</span>
            </div>
            <div class="detail-row">
              <span class="label">严重等级:</span>
              <span class="value badge" :class="`badge-${selectedEvent.severity}`">
                {{ getSeverityLabel(selectedEvent.severity) }}
              </span>
            </div>
          </div>

          <div class="detail-section">
            <h4>时间信息</h4>
            <div class="detail-row">
              <span class="label">开始时间:</span>
              <span class="value">{{ formatDateTime(selectedEvent.startTime) }}</span>
            </div>
            <div class="detail-row">
              <span class="label">持续时间:</span>
              <span class="value">{{ selectedEvent.duration }} 秒</span>
            </div>
          </div>

          <div class="detail-section">
            <h4>位置信息</h4>
            <div class="detail-row">
              <span class="label">位置:</span>
              <span class="value">{{ selectedEvent.location }}</span>
            </div>
            <div class="detail-row">
              <span class="label">通道范围:</span>
              <span class="value">{{ selectedEvent.startChannel }} - {{ selectedEvent.endChannel }}</span>
            </div>
          </div>

          <div class="detail-actions">
            <button class="btn btn-primary" @click="processEvent">处理事件</button>
            <button class="btn" @click="exportEvent">导出数据</button>
            <button class="btn btn-danger" @click="deleteEvent">删除事件</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'




const statusFilter = ref('all')
const severityFilter = ref('all')
const typeFilter = ref('all')
const searchKeyword = ref('')
const selectedEvent = ref<any>(null)

// 模拟事件数据
const events = ref([
  { id: 1, eventId: 'EVT-2024-001', eventName: '车辆经过事件', eventType: '车辆经过', severity: 'low', status: 'resolved', location: '通道 120-150', startTime: new Date(), duration: 5.2, startChannel: 120, endChannel: 150, confidence: 0.95 },
  { id: 2, eventId: 'EVT-2024-002', eventName: '异常振动检测', eventType: '振动异常', severity: 'high', status: 'active', location: '通道 80-95', startTime: new Date(Date.now() - 3600000), duration: 12.5, startChannel: 80, endChannel: 95, confidence: 0.88 },
  { id: 3, eventId: 'EVT-2024-003', eventName: '施工扰动警报', eventType: '施工扰动', severity: 'critical', status: 'processing', location: '通道 200-250', startTime: new Date(Date.now() - 7200000), duration: 45.8, startChannel: 200, endChannel: 250, confidence: 0.92 },
  { id: 4, eventId: 'EVT-2024-004', eventName: '车辆经过事件', eventType: '车辆经过', severity: 'low', status: 'resolved', location: '通道 300-320', startTime: new Date(Date.now() - 10800000), duration: 4.1, startChannel: 300, endChannel: 320, confidence: 0.97 },
  { id: 5, eventId: 'EVT-2024-005', eventName: '管道振动异常', eventType: '管道振动', severity: 'medium', status: 'processing', location: '通道 450-480', startTime: new Date(Date.now() - 14400000), duration: 18.3, startChannel: 450, endChannel: 480, confidence: 0.85 },
  { id: 6, eventId: 'EVT-2024-006', eventName: '光纤设备离线', eventType: '设备离线', severity: 'critical', status: 'resolved', location: '设备 #3', startTime: new Date(Date.now() - 18000000), duration: 120, startChannel: 0, endChannel: 0, confidence: 1.0 }
])

const filteredEvents = computed(() => {
  return events.value.filter(event => {
    if (statusFilter.value !== 'all' && event.status !== statusFilter.value) return false
    if (severityFilter.value !== 'all' && event.severity !== severityFilter.value) return false
    if (searchKeyword.value && !event.eventName.includes(searchKeyword.value) && !event.eventId.includes(searchKeyword.value)) return false
    return true
  })
})

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: '活动中',
    processing: '处理中',
    resolved: '已解决',
    closed: '已关闭'
  }
  return labels[status] || status
}

function getSeverityLabel(severity: string): string {
  const labels: Record<string, string> = {
    critical: '严重',
    high: '高',
    medium: '中',
    low: '低',
    info: '信息'
  }
  return labels[severity] || severity
}

function formatTime(date: Date): string {
  return new Date(date).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatDateTime(date: Date): string {
  return new Date(date).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function applyFilter() {
  console.log('应用筛选')
}

function refreshEvents() {
  console.log('刷新事件')
}

function createEvent() {
  console.log('新建事件')
}

function selectEvent(event: any) {
  selectedEvent.value = event
}

function processEvent() {
  console.log('处理事件:', selectedEvent.value?.eventId)
}

function exportEvent() {
  console.log('导出事件:', selectedEvent.value?.eventId)
}

function deleteEvent() {
  console.log('删除事件:', selectedEvent.value?.eventId)
}
</script>

<style scoped>
.event-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
  background: var(--color-bg-primary);
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.view-title {
  margin: 0;
  font-size: 24px;
  color: var(--color-text-primary);
}

.view-actions {
  display: flex;
  gap: 10px;
}

.btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.btn-primary {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #000;
}

.btn-primary:hover {
  background: var(--color-accent-hover);
}

.btn-danger {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: #fff;
}

.filter-bar {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 16px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  margin-bottom: 20px;
}

.filter-group, .search-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.select-input, .search-input {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
}

.search-input {
  min-width: 200px;
}

.content-area {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 350px;
  gap: 20px;
  overflow: hidden;
}

.events-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  align-content: start;
  overflow-y: auto;
  padding-right: 8px;
}

.event-card {
  padding: 16px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-left: 4px solid;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.event-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.event-card.severity-critical { border-left-color: var(--color-danger); }
.event-card.severity-high { border-left-color: var(--color-warning); }
.event-card.severity-medium { border-left-color: var(--color-info); }
.event-card.severity-low { border-left-color: var(--color-success); }
.event-card.severity-info { border-left-color: #888; }

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.event-id {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent);
}

.event-status {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: bold;
}

.event-status.status-active { background: rgba(255, 0, 0, 0.2); color: var(--color-danger); }
.event-status.status-processing { background: rgba(255, 184, 0, 0.2); color: var(--color-warning); }
.event-status.status-resolved { background: rgba(0, 255, 0, 0.2); color: var(--color-success); }
.event-status.status-closed { background: rgba(100, 100, 100, 0.2); color: #888; }

.event-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 10px;
}

.event-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.meta-icon {
  font-size: 14px;
}

.event-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.severity-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: bold;
}

.badge-critical { background: var(--color-danger); color: #fff; }
.badge-high { background: var(--color-warning); color: #000; }
.badge-medium { background: var(--color-info); color: #fff; }
.badge-low { background: var(--color-success); color: #000; }
.badge-info { background: #888; color: #fff; }

.confidence {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.event-detail-panel {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
}

.detail-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--color-text-primary);
}

.btn-close {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 20px;
  cursor: pointer;
}

.btn-close:hover {
  color: var(--color-text-primary);
}

.detail-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: var(--color-accent);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 13px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-row .label {
  color: var(--color-text-secondary);
}

.detail-row .value {
  color: var(--color-text-primary);
  font-weight: 500;
}

.detail-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 20px;
}

.detail-actions .btn {
  width: 100%;
}
</style>
