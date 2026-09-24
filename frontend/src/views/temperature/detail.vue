<template>
  <section class="page" data-module="temperature-detail">
    <header class="page-head">
      <div>
        <h2>温控测点详情</h2>
        <p class="page-desc">详情页与列表使用同一个接口口径展示温度、上下限、采集时间与在线状态。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <article v-if="entry" class="detail-card">
      <div v-for="field in detailFields" :key="field" class="detail-row">
        <span>{{ field }}</span>
        <strong>{{ formatCell(field) }}</strong>
      </div>

      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          :class="{ primary: action === '重新采集' }"
          type="button"
          :disabled="loading"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>
    </article>

    <div v-else class="detail-card empty-state">正在读取温控记录...</div>

    <footer class="page-foot">
      <span v-if="entry">记录编号：{{ entry.记录编号 }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/temperature'
const actions = ['确认记录', '标记超限', '重新采集']
const detailFields = [
  '记录编号',
  '关联运单',
  '测点编号',
  '状态',
  '连接状态',
  '实时温度',
  '温度上限',
  '温度下限',
  '采集时间',
  '上次成功采集时间',
]

const route = useRoute()
const router = useRouter()
const entry = ref<Row | null>(null)
const errorMessage = ref('')
const loading = ref(false)

function formatCell(field: string) {
  if (!entry.value) return '—'
  if (field === '连接状态') return entry.value.在线 === true ? '在线' : '离线'
  if (['实时温度', '温度上限', '温度下限'].includes(field)) {
    return typeof entry.value[field] === 'number' ? `${entry.value[field]}℃` : '—'
  }
  return entry.value[field] ?? '—'
}

function goBack() {
  void router.push({ name: 'temperature' })
}

async function loadEntry() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    if (!response.ok) {
      throw new Error('温控记录详情读取失败，当前显示上一次成功结果')
    }
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温控记录详情读取失败，当前显示上一次成功结果'
  }
}

async function runAction(action: string) {
  errorMessage.value = ''
  loading.value = true
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean, preserved?: boolean, message?: string, entry?: Row } | null
    if (!response.ok || !payload || (payload.ok === false && !payload.preserved)) {
      throw new Error(payload?.message || '温控监控动作未生效，请稍后重试')
    }
    if (payload.entry) {
      entry.value = payload.entry
    }
    errorMessage.value = payload.preserved ? payload.message || '采集失败，已保留上一次成功结果' : ''
    if (!payload.preserved) {
      await loadEntry()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温控监控操作失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadEntry)
</script>

<style scoped>
.detail-card {
  max-width: 720px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.detail-row {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid #edf1f5;
  font-size: 14px;
}

.detail-row span {
  color: var(--muted);
}

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.btn:disabled {
  cursor: wait;
  opacity: 0.6;
}
</style>
