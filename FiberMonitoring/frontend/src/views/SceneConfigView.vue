<template>
  <div class="scene-config-view">
    <div class="view-header">
      <h2 class="view-title">场景配置</h2>
      <div class="view-actions">
        <button class="btn btn-primary" @click="saveConfig">
          保存配置
        </button>
        <button class="btn" @click="resetConfig">
          重置
        </button>
      </div>
    </div>

    <div class="content-area">
      <!-- 左侧配置树 -->
      <aside class="config-sidebar">
        <div class="config-tree">
          <div
            v-for="category in configCategories"
            :key="category.key"
            class="tree-item"
            :class="{ active: activeCategory === category.key }"
            @click="selectCategory(category.key)"
          >
            <span class="tree-icon">{{ category.icon }}</span>
            <span class="tree-label">{{ category.label }}</span>
          </div>
        </div>
      </aside>

      <!-- 右侧配置面板 -->
      <main class="config-main">
        <!-- 光纤配置 -->
        <div v-if="activeCategory === 'fiber'" class="config-panel">
          <h3 class="panel-title">光纤监测配置</h3>

          <div class="config-section">
            <h4>基本参数</h4>
            <div class="form-group">
              <label class="form-label">采样率 (Hz)</label>
              <input v-model.number="fiberConfig.samplingRate" type="number" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">空间间隔 (m)</label>
              <input v-model.number="fiberConfig.spatialInterval" type="number" step="0.1" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">通道数</label>
              <input v-model.number="fiberConfig.channelCount" type="number" class="form-input" />
            </div>
          </div>

          <div class="config-section">
            <h4>监测范围</h4>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">起始桩号 (m)</label>
                <input v-model.number="fiberConfig.startChainage" type="number" class="form-input" />
              </div>
              <div class="form-group">
                <label class="form-label">结束桩号 (m)</label>
                <input v-model.number="fiberConfig.endChainage" type="number" class="form-input" />
              </div>
            </div>
          </div>

          <div class="config-section">
            <h4>数据处理</h4>
            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="fiberConfig.autoFilter" type="checkbox" />
                <span>启用自动滤波</span>
              </label>
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="fiberConfig.realTimeAnalysis" type="checkbox" />
                <span>启用实时分析</span>
              </label>
            </div>
          </div>
        </div>

        <!-- 设备配置 -->
        <div v-else-if="activeCategory === 'device'" class="config-panel">
          <h3 class="panel-title">设备管理配置</h3>

          <div class="config-section">
            <h4>设备列表</h4>
            <div class="device-list">
              <div v-for="device in deviceConfig.devices" :key="device.id" class="device-item">
                <div class="device-info">
                  <div class="device-name">{{ device.name }}</div>
                  <div class="device-status" :class="`status-${device.status}`">
                    {{ device.status }}
                  </div>
                </div>
                <div class="device-actions">
                  <button class="btn-icon" @click="editDevice(device)">✏️</button>
                  <button class="btn-icon" @click="deleteDevice(device.id)">🗑️</button>
                </div>
              </div>
            </div>
            <button class="btn btn-primary" @click="addDevice">添加设备</button>
          </div>

          <div class="config-section">
            <h4>连接设置</h4>
            <div class="form-group">
              <label class="form-label">连接超时 (秒)</label>
              <input v-model.number="deviceConfig.connectionTimeout" type="number" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">心跳间隔 (秒)</label>
              <input v-model.number="deviceConfig.heartbeatInterval" type="number" class="form-input" />
            </div>
          </div>
        </div>

        <!-- 告警配置 -->
        <div v-else-if="activeCategory === 'alert'" class="config-panel">
          <h3 class="panel-title">告警规则配置</h3>

          <div class="config-section">
            <h4>阈值设置</h4>
            <div class="form-group">
              <label class="form-label">振幅阈值 (mV)</label>
              <input v-model.number="alertConfig.amplitudeThreshold" type="number" step="0.1" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">频率阈值 (Hz)</label>
              <input v-model.number="alertConfig.frequencyThreshold" type="number" step="0.1" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">持续时间阈值 (秒)</label>
              <input v-model.number="alertConfig.durationThreshold" type="number" step="0.1" class="form-input" />
            </div>
          </div>

          <div class="config-section">
            <h4>通知设置</h4>
            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="alertConfig.emailNotification" type="checkbox" />
                <span>邮件通知</span>
              </label>
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="alertConfig.smsNotification" type="checkbox" />
                <span>短信通知</span>
              </label>
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="alertConfig.soundAlert" type="checkbox" />
                <span>声音告警</span>
              </label>
            </div>
          </div>
        </div>

        <!-- 显示配置 -->
        <div v-else-if="activeCategory === 'display'" class="config-panel">
          <h3 class="panel-title">显示配置</h3>

          <div class="config-section">
            <h4>界面主题</h4>
            <div class="form-group">
              <label class="form-label">主题颜色</label>
              <select v-model="displayConfig.theme" class="form-select">
                <option value="dark">深色主题</option>
                <option value="light">浅色主题</option>
                <option value="auto">自动</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">强调色</label>
              <input v-model="displayConfig.accentColor" type="color" class="form-input-color" />
            </div>
          </div>

          <div class="config-section">
            <h4>图表设置</h4>
            <div class="form-group">
              <label class="form-label">默认刷新率 (ms)</label>
              <input v-model.number="displayConfig.refreshRate" type="number" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">显示数据点数</label>
              <input v-model.number="displayConfig.dataPoints" type="number" class="form-input" />
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="displayConfig.smoothing" type="checkbox" />
                <span>启用平滑处理</span>
              </label>
            </div>
          </div>
        </div>

        <!-- 系统配置 -->
        <div v-else-if="activeCategory === 'system'" class="config-panel">
          <h3 class="panel-title">系统配置</h3>

          <div class="config-section">
            <h4>存储设置</h4>
            <div class="form-group">
              <label class="form-label">数据保留天数</label>
              <input v-model.number="systemConfig.dataRetentionDays" type="number" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">存储路径</label>
              <input v-model="systemConfig.storagePath" type="text" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">最大存储空间 (GB)</label>
              <input v-model.number="systemConfig.maxStorageSize" type="number" class="form-input" />
            </div>
          </div>

          <div class="config-section">
            <h4>性能优化</h4>
            <div class="form-group">
              <label class="form-label">并发处理线程数</label>
              <input v-model.number="systemConfig.workerThreads" type="number" class="form-input" />
            </div>
            <div class="form-group">
              <label class="form-label">内存缓存大小 (MB)</label>
              <input v-model.number="systemConfig.cacheSize" type="number" class="form-input" />
            </div>
          </div>

          <div class="config-section">
            <h4>日志设置</h4>
            <div class="form-group">
              <label class="form-label">日志级别</label>
              <select v-model="systemConfig.logLevel" class="form-select">
                <option value="debug">DEBUG</option>
                <option value="info">INFO</option>
                <option value="warning">WARNING</option>
                <option value="error">ERROR</option>
              </select>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const activeCategory = ref('fiber')

const configCategories = [
  { key: 'fiber', icon: '🔌', label: '光纤配置' },
  { key: 'device', icon: '📡', label: '设备管理' },
  { key: 'alert', icon: '⚠️', label: '告警规则' },
  { key: 'display', icon: '🎨', label: '显示配置' },
  { key: 'system', icon: '⚙️', label: '系统配置' }
]

// 配置数据
const fiberConfig = ref({
  samplingRate: 1000,
  spatialInterval: 4.0,
  channelCount: 512,
  startChainage: 0,
  endChainage: 2048,
  autoFilter: true,
  realTimeAnalysis: true
})

const deviceConfig = ref({
  devices: [
    { id: 1, name: 'DAS设备-1', status: 'online' },
    { id: 2, name: 'DAS设备-2', status: 'online' },
    { id: 3, name: 'DAS设备-3', status: 'offline' }
  ],
  connectionTimeout: 30,
  heartbeatInterval: 10
})

const alertConfig = ref({
  amplitudeThreshold: 5.0,
  frequencyThreshold: 50.0,
  durationThreshold: 2.0,
  emailNotification: true,
  smsNotification: false,
  soundAlert: true
})

const displayConfig = ref({
  theme: 'dark',
  accentColor: '#00D9FF',
  refreshRate: 1000,
  dataPoints: 1000,
  smoothing: true
})

const systemConfig = ref({
  dataRetentionDays: 30,
  storagePath: '/data/das',
  maxStorageSize: 500,
  workerThreads: 4,
  cacheSize: 512,
  logLevel: 'info'
})

function selectCategory(key: string) {
  activeCategory.value = key
}

function saveConfig() {
  console.log('保存配置')
}

function resetConfig() {
  console.log('重置配置')
}

function addDevice() {
  console.log('添加设备')
}

function editDevice(device: any) {
  console.log('编辑设备:', device)
}

function deleteDevice(id: number) {
  console.log('删除设备:', id)
}
</script>

<style scoped>
.scene-config-view {
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

.content-area {
  flex: 1;
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 20px;
  overflow: hidden;
}

.config-sidebar {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 10px;
}

.config-tree {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.tree-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.tree-item.active {
  background: var(--color-accent);
  color: #000;
}

.tree-icon {
  font-size: 18px;
}

.tree-label {
  font-size: 13px;
  font-weight: 500;
}

.config-main {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 20px;
  overflow-y: auto;
}

.config-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.panel-title {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--color-accent);
  padding-bottom: 10px;
  border-bottom: 2px solid var(--color-accent);
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-section h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: var(--color-text-primary);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.form-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.form-input, .form-select {
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 13px;
}

.form-input:focus, .form-select:focus {
  outline: none;
  border-color: var(--color-accent);
}

.form-input-color {
  width: 60px;
  height: 36px;
  padding: 2px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  cursor: pointer;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-primary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.device-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.device-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.device-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.device-name {
  font-size: 13px;
  color: var(--color-text-primary);
  font-weight: 500;
}

.device-status {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: bold;
}

.device-status.status-online {
  background: rgba(0, 255, 0, 0.2);
  color: var(--color-success);
}

.device-status.status-offline {
  background: rgba(100, 100, 100, 0.2);
  color: #888;
}

.device-actions {
  display: flex;
  gap: 8px;
}

.btn-icon {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.btn-icon:hover {
  opacity: 1;
}
</style>
