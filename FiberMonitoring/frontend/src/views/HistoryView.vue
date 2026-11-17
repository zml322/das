<template>
  <div class="history-view">
    <div class="view-header">
      <h2 class="view-title">历史数据</h2>
      <div class="view-actions">
        <button class="btn btn-primary" @click="exportData">
          导出数据
        </button>
        <button class="btn" @click="refreshData">
          刷新
        </button>
      </div>
    </div>

    <div class="filter-bar">
      <div class="filter-group">
        <label class="filter-label">时间范围:</label>
        <select v-model="timeRange" class="select-input">
          <option value="today">今天</option>
          <option value="yesterday">昨天</option>
          <option value="week">最近7天</option>
          <option value="month">最近30天</option>
          <option value="custom">自定义</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">事件类型:</label>
        <select v-model="eventType" class="select-input">
          <option value="all">全部</option>
          <option value="vehicle">车辆事件</option>
          <option value="vibration">振动异常</option>
          <option value="construction">施工扰动</option>
          <option value="device">设备事件</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">严重等级:</label>
        <select v-model="severity" class="select-input">
          <option value="all">全部</option>
          <option value="info">信息</option>
          <option value="low">低</option>
          <option value="medium">中</option>
          <option value="high">高</option>
          <option value="critical">严重</option>
        </select>
      </div>

      <button class="btn btn-primary" @click="applyFilter">
        应用筛选
      </button>
    </div>

    <div class="content-area">
      <div class="statistics-section">
        <div class="stat-card">
          <div class="stat-icon">📊</div>
          <div class="stat-content">
            <div class="stat-label">总事件数</div>
            <div class="stat-value">{{ statistics.totalEvents }}</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">⚠️</div>
          <div class="stat-content">
            <div class="stat-label">异常事件</div>
            <div class="stat-value">{{ statistics.abnormalEvents }}</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">✅</div>
          <div class="stat-content">
            <div class="stat-label">已处理</div>
            <div class="stat-value">{{ statistics.resolvedEvents }}</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">⏳</div>
          <div class="stat-content">
            <div class="stat-label">处理中</div>
            <div class="stat-value">{{ statistics.processingEvents }}</div>
          </div>
        </div>
      </div>

      <div class="table-section">
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>事件类型</th>
              <th>位置</th>
              <th>严重等级</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in historyRecords" :key="record.id">
              <td>{{ formatDateTime(record.time) }}</td>
              <td>{{ record.eventType }}</td>
              <td>{{ record.location }}</td>
              <td>
                <span class="badge" :class="`badge-${record.severity}`">
                  {{ record.severity }}
                </span>
              </td>
              <td>
                <span class="status-badge" :class="`status-${record.status}`">
                  {{ record.status }}
                </span>
              </td>
              <td>
                <button class="btn-link" @click="viewDetail(record.id)">
                  查看详情
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <div class="pagination">
          <button class="btn" :disabled="currentPage === 1" @click="prevPage">
            上一页
          </button>
          <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
          <button class="btn" :disabled="currentPage === totalPages" @click="nextPage">
            下一页
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'




const timeRange = ref('today')
const eventType = ref('all')
const severity = ref('all')
const currentPage = ref(1)
const totalPages = ref(10)

const statistics = ref({
  totalEvents: 264,
  abnormalEvents: 17,
  resolvedEvents: 245,
  processingEvents: 2
})

// 模拟历史记录数据
const historyRecords = ref([
  { id: 1, time: new Date(), eventType: '车辆经过', location: '通道 120-150', severity: 'low', status: 'resolved' },
  { id: 2, time: new Date(Date.now() - 3600000), eventType: '振动异常', location: '通道 80-95', severity: 'medium', status: 'processing' },
  { id: 3, time: new Date(Date.now() - 7200000), eventType: '施工扰动', location: '通道 200-250', severity: 'high', status: 'resolved' },
  { id: 4, time: new Date(Date.now() - 10800000), eventType: '车辆经过', location: '通道 300-320', severity: 'low', status: 'resolved' },
  { id: 5, time: new Date(Date.now() - 14400000), eventType: '设备离线', location: '设备 #3', severity: 'critical', status: 'resolved' }
])

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
  console.log('应用筛选:', { timeRange: timeRange.value, eventType: eventType.value, severity: severity.value })
}

function refreshData() {
  console.log('刷新数据')
}

function exportData() {
  console.log('导出数据')
}

function viewDetail(id: number) {
  console.log('查看详情:', id)
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
  }
}
</script>

<style scoped>
.history-view {
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

.btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #000;
}

.btn-primary:hover {
  background: var(--color-accent-hover);
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

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.select-input {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
}

.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow: hidden;
}

.statistics-section {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.stat-icon {
  font-size: 32px;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--color-accent);
}

.table-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  overflow: hidden;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table thead {
  background: rgba(255, 255, 255, 0.05);
}

.data-table th {
  padding: 12px;
  text-align: left;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.data-table td {
  padding: 12px;
  font-size: 13px;
  color: var(--color-text-primary);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.data-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: bold;
}

.badge-low { background: var(--color-success); color: #000; }
.badge-medium { background: var(--color-info); color: #fff; }
.badge-high { background: var(--color-warning); color: #000; }
.badge-critical { background: var(--color-danger); color: #fff; }

.status-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
}

.status-resolved { background: rgba(0, 255, 0, 0.2); color: var(--color-success); }
.status-processing { background: rgba(255, 184, 0, 0.2); color: var(--color-warning); }

.btn-link {
  background: none;
  border: none;
  color: var(--color-accent);
  cursor: pointer;
  font-size: 13px;
}

.btn-link:hover {
  text-decoration: underline;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border-top: 1px solid var(--color-border);
}

.page-info {
  font-size: 13px;
  color: var(--color-text-secondary);
}
</style>
