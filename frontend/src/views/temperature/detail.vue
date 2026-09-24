<template>
  <section class="page" data-module="temperature-detail">
    <header class="page-head">
      <div>
        <h2>温控记录详情</h2>
        <p class="page-desc">详情、列表与动作回写共用同一份接口数据，刷新或返回后数值保持一致。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/temperature">返回列表</RouterLink>
      </div>
    </header>

    <article v-if="entry" class="detail-card">
      <div class="detail-head">
        <div>
          <h3>{{ entry.记录编号 }} / {{ entry.测点编号 }}</h3>
          <p>{{ entry.关联运单 }}</p>
        </div>
        <span class="status-badge" :class="`status-${entry.status}`">{{ entry.status }}</span>
      </div>

      <dl class="detail-grid">
        <div v-for="item in fields" :key="item.label">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>

      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          :class="{ primary: action === '重新采集' }"
          type="button"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>
    </article>

    <div v-else class="detail-card empty-state">未找到温控记录，可返回列表重新选择。</div>

    <footer class="page-foot">
      <span v-if="feedbackMessage">{{ feedbackMessage }}</span>
      <span v-if="store.errorMessage" class="error-text">{{ store.errorMessage }}，当前展示上一次成功结果</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { useTemperatureStore } from '@/stores/temperature'

const actions = ["确认记录", "标记超限", "重新采集"]

const route = useRoute()
const store = useTemperatureStore()
const feedbackMessage = ref('')
const entryId = Number(route.params.id)

const entry = computed(() => store.findEntry(entryId))
const fields = computed(() => {
  if (!entry.value) {
    return []
  }
  const current = entry.value
  return [
    { label: '记录编号', value: current.记录编号 },
    { label: '关联运单', value: current.关联运单 },
    { label: '测点编号', value: current.测点编号 },
    { label: '实时温度', value: formatTemperature(current.实时温度) },
    { label: '温度上限', value: formatTemperature(current.温度上限) },
    { label: '温度下限', value: formatTemperature(current.温度下限) },
    { label: '采集时间', value: current.采集时间 || '—' },
    { label: '在线状态', value: current.在线状态 ? '在线' : '离线' },
  ]
})

function formatTemperature(value: number | null) {
  return value === null ? '—' : `${value.toFixed(1)} ℃`
}

async function runAction(action: string) {
  try {
    feedbackMessage.value = await store.runAction(entryId, action)
  } catch (error) {
    store.errorMessage = error instanceof Error ? error.message : '温控监控操作失败'
  }
}

onMounted(async () => {
  await store.fetchEntry(entryId)
})
</script>

<style scoped>
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
}
.detail-head h3 {
  margin: 0;
}
.detail-head p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.status-badge {
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
}
.status-正常 { background: #ecfdf3; color: #027a48; }
.status-偏高,
.status-偏低 { background: #fffaeb; color: #b54708; }
.status-已离线 { background: #f2f4f7; color: #475467; }
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 16px 0;
}
.detail-grid dt {
  color: var(--muted);
  font-size: 12px;
}
.detail-grid dd {
  margin: 4px 0 0;
  font-weight: 600;
}
.detail-actions {
  display: flex;
  gap: 8px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}
</style>
