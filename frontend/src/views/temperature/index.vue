<template>
  <section class="page" data-module="temperature">
    <header class="page-head">
      <div>
        <h2>温控监控管理</h2>
        <p class="page-desc">维护温控记录，围绕记录编号、关联运单、测点编号、实时温度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记温控记录</button>
        <button class="btn" type="button" @click="exportRows">导出温控监控清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">今日采集测点</span>
        <strong class="stat-value">{{ store.todayCount }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">超限测点</span>
        <strong class="stat-value">{{ store.excursionCount }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">离线测点</span>
        <strong class="stat-value">{{ store.offlineCount }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in store.items" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(row, column) }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <RouterLink class="link" :to="`/temperature/${row.id}`">查看详情</RouterLink>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!store.items.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无温控监控数据，可先登记温控记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ store.total }} 条温控监控记录<span v-if="feedbackMessage">，{{ feedbackMessage }}</span></span>
      <span v-if="store.errorMessage" class="error-text">{{ store.errorMessage }}，当前展示上一次成功结果</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useTemperatureStore, type TemperatureEntry } from '@/stores/temperature'

const ENDPOINT = '/api/temperature'
const columns = ["记录编号", "关联运单", "测点编号", "实时温度", "温度上限", "温度下限", "采集时间"]
const actions = ["确认记录", "标记超限", "重新采集"]
const statuses = ["正常", "偏高", "偏低", "已离线"]

const store = useTemperatureStore()
const keyword = ref('')
const status = ref('')
const feedbackMessage = ref('')

function formatCell(row: TemperatureEntry, column: string) {
  const value = row[column as keyof TemperatureEntry]
  if (column === '实时温度' && typeof value === 'number') {
    return `${value.toFixed(1)} ℃`
  }
  if ((column === '温度上限' || column === '温度下限') && typeof value === 'number') {
    return `${value.toFixed(1)} ℃`
  }
  return value ?? '—'
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  store.errorMessage = '温控记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: TemperatureEntry) {
  try {
    feedbackMessage.value = await store.runAction(row.id, action)
  } catch (error) {
    store.errorMessage = error instanceof Error ? error.message : '温控监控操作失败'
  }
}

async function reload() {
  feedbackMessage.value = ''
  await store.fetchList({ keyword: keyword.value.trim(), status: status.value })
}

onMounted(reload)
</script>
