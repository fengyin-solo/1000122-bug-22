<template>
  <section class="page" data-module="temperature">
    <header class="page-head">
      <div>
        <h2>温控监控管理</h2>
        <p class="page-desc">统一写回并读取采集温度、上下限、采集时间与在线状态；采集失败时保留上一次成功结果。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记温控记录</button>
        <button class="btn" type="button" @click="exportRows">导出温控监控清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
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
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无温控监控数据，可先登记温控记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条温控记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/temperature'
const columns = ["记录编号", "关联运单", "测点编号", "状态", "连接状态", "实时温度", "温度上限", "温度下限", "采集时间"]
const actions = ["确认记录", "标记超限", "重新采集"]
const statuses = ["正常", "偏高", "偏低", "已离线"]
const filterFields = ["记录编号", "关联运单", "测点编号"]

const router = useRouter()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')

const stats = computed(() => [
  { label: '在线测点', value: rows.value.filter((row) => row.在线 === true).length },
  { label: '超限测点', value: rows.value.filter((row) => row.status === '偏高' || row.status === '偏低').length },
  { label: '离线测点', value: rows.value.filter((row) => row.status === '已离线').length },
])

function formatCell(row: Row, column: string) {
  if (column === '连接状态') return row.在线 === true ? '在线' : '离线'
  if (column === '实时温度') return typeof row[column] === 'number' ? `${row[column]}℃` : '—'
  if (column === '温度上限' || column === '温度下限') return typeof row[column] === 'number' ? `${row[column]}℃` : '—'
  return row[column] ?? '—'
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '温控记录登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  void router.push({ name: 'temperature-detail', params: { id: String(row.id) } })
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean, preserved?: boolean, message?: string, entry?: Row } | null
    if (!response.ok || !payload || (payload.ok === false && !payload.preserved)) {
      throw new Error(payload?.message || '温控监控动作未生效，请稍后重试')
    }
    if (payload.entry) {
      rows.value = rows.value.map((item) => item.id === payload.entry?.id ? payload.entry as Row : item)
    }
    errorMessage.value = payload.preserved ? payload.message || '采集失败，已保留上一次成功结果' : ''
    if (!payload.preserved) {
      await reload()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温控监控操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams({
    ...filters.value,
    ...(statusFilter.value ? { status: statusFilter.value } : {}),
  }).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('温控记录列表读取失败，当前显示上一次成功结果')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温控监控列表读取失败，当前显示上一次成功结果'
  }
}

onMounted(reload)
</script>
