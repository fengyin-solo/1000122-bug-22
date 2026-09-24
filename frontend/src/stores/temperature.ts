import { defineStore } from 'pinia'

import { request } from '@/api/client'

export interface TemperatureEntry {
  id: number
  记录编号: string
  关联运单: string
  测点编号: string
  实时温度: number | null
  温度上限: number
  温度下限: number
  采集时间: string | null
  在线状态: boolean
  status: string
}

interface ListResponse {
  items: TemperatureEntry[]
  total: number
  page: number
  size: number
}

interface ActionResponse {
  ok: boolean
  message: string
  entry: TemperatureEntry | null
}

export interface TemperatureQuery {
  keyword?: string
  status?: string
}

const ENTRY_CACHE_KEY = 'temperature:last-successful-entries'

function upsert(items: TemperatureEntry[], entry: TemperatureEntry | null): TemperatureEntry[] {
  if (!entry) {
    return items
  }
  const index = items.findIndex((item) => item.id === entry.id)
  if (index === -1) {
    return [entry, ...items]
  }
  const next = [...items]
  next.splice(index, 1, entry)
  return next
}

function readEntryCache(): Map<number, TemperatureEntry> {
  try {
    const raw = window.localStorage.getItem(ENTRY_CACHE_KEY)
    const entries = raw ? (JSON.parse(raw) as TemperatureEntry[]) : []
    return new Map(entries.map((entry) => [entry.id, entry]))
  } catch {
    return new Map()
  }
}

function writeEntryCache(cache: Map<number, TemperatureEntry>) {
  window.localStorage.setItem(ENTRY_CACHE_KEY, JSON.stringify([...cache.values()]))
}

export const useTemperatureStore = defineStore('temperature', {
  state: () => {
    const entryCache = readEntryCache()
    const cachedItems = [...entryCache.values()]
    return {
      items: cachedItems,
      total: cachedItems.length,
      entryCache,
      loaded: cachedItems.length > 0,
      loading: false,
      errorMessage: '',
      lastUpdatedAt: '',
    }
  },
  getters: {
    todayCount: (state) => state.items.filter((item) => item.采集时间).length,
    excursionCount: (state) => state.items.filter((item) => item.status === '偏高' || item.status === '偏低').length,
    offlineCount: (state) => state.items.filter((item) => item.status === '已离线').length,
  },
  actions: {
    findEntry(id: number): TemperatureEntry | undefined {
      return this.items.find((item) => item.id === id) ?? this.entryCache.get(id)
    },

    cacheEntries(entries: TemperatureEntry[]) {
      entries.forEach((entry) => this.entryCache.set(entry.id, entry))
      writeEntryCache(this.entryCache)
    },

    async fetchList(query: TemperatureQuery = {}): Promise<void> {
      this.loading = true
      const previousItems = this.items
      const previousTotal = this.total
      try {
        const params = new URLSearchParams()
        if (query.keyword) {
          params.set('keyword', query.keyword)
        }
        if (query.status) {
          params.set('status', query.status)
        }
        const suffix = params.toString() ? `?${params.toString()}` : ''
        const response = await request(`/api/temperature${suffix}`)
        if (!response.ok) {
          throw new Error('温控记录列表读取失败')
        }
        const payload = (await response.json()) as ListResponse
        this.items = payload.items ?? []
        this.total = payload.total ?? this.items.length
        this.cacheEntries(this.items)
        this.loaded = true
        this.errorMessage = ''
        this.lastUpdatedAt = new Date().toISOString()
      } catch (error) {
        // 读取失败时继续展示上一次成功的列表，硬刷新后也能回退到本地最近一次成功结果。
        const fallbackItems = previousItems.length ? previousItems : [...this.entryCache.values()]
        this.items = fallbackItems
        this.total = previousItems.length ? previousTotal : fallbackItems.length
        this.errorMessage = error instanceof Error ? error.message : '温控记录列表读取失败'
      } finally {
        this.loading = false
      }
    },

    async fetchEntry(id: number): Promise<TemperatureEntry | null> {
      const cached = this.findEntry(id)
      try {
        const response = await request(`/api/temperature/${id}`)
        if (!response.ok) {
          throw new Error('温控记录详情读取失败')
        }
        const entry = (await response.json()) as TemperatureEntry
        this.items = upsert(this.items, entry)
        this.cacheEntries([entry])
        this.loaded = true
        this.errorMessage = ''
        return entry
      } catch (error) {
        this.errorMessage = error instanceof Error ? error.message : '温控记录详情读取失败'
        if (cached) {
          this.items = upsert(this.items, cached)
        }
        return cached ?? null
      }
    },

    async runAction(id: number, action: string): Promise<string> {
      const response = await request(`/api/temperature/${id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values: { action } }),
      })
      if (!response.ok) {
        throw new Error('温控监控动作未生效，请稍后重试')
      }
      const payload = (await response.json()) as ActionResponse
      if (!payload.ok || !payload.entry) {
        throw new Error(payload.message || '温控监控动作未生效，请稍后重试')
      }
      this.items = upsert(this.items, payload.entry)
      this.total = Math.max(this.total, this.items.length)
      this.cacheEntries([payload.entry])
      this.errorMessage = ''
      return payload.message
    },
  },
})
