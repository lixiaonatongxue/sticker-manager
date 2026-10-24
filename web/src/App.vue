<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from './api.js'
import AllStickers from './components/AllStickers.vue'
import Duplicates from './components/Duplicates.vue'
import TagsView from './components/TagsView.vue'

const tab = ref('all')
const status = reactive({ loaded: false, data: null })
const scanning = ref(false)
const scanProgress = reactive({ done: 0, total: 0, note: null, error: null })
const toast = reactive({ show: false, msg: '', err: false })
const tagFilter = ref('')

let pollTimer = null

function notify(msg, err = false) {
  toast.msg = msg
  toast.err = err
  toast.show = true
  setTimeout(() => (toast.show = false), err ? 6000 : 3500)
}

async function refreshStatus() {
  try {
    status.data = await api.status()
    status.loaded = true
  } catch (e) {
    notify('无法连接本地服务：' + e.message, true)
  }
}

async function startScan() {
  try {
    await api.startScan()
    scanning.value = true
    scanProgress.error = null
    pollTimer = setInterval(async () => {
      const st = await api.scanStatus()
      scanProgress.done = st.done
      scanProgress.total = st.total
      scanProgress.note = st.note
      if (!st.running) {
        clearInterval(pollTimer)
        scanning.value = false
        if (st.last_error) {
          scanProgress.error = st.last_error
          notify('扫描失败：' + st.last_error, true)
        } else {
          const s = st.last_stats
          const where = s.dirs > 1 ? `（自动扫描 ${s.dirs} 个微信目录）` : ''
          notify(`扫描完成${where}：新增 ${s.added}，未变 ${s.skipped}`)
        }
        refreshStatus()
      }
    }, 800)
  } catch (e) {
    notify(e.message, true)
  }
}

function gotoTag(tag) {
  tagFilter.value = tag
  tab.value = 'all'
}

onMounted(refreshStatus)
defineExpose({ refreshStatus })
</script>

<template>
  <header class="header">
    <h1>😹 表情包管家</h1>
    <span class="ver" v-if="status.data">v{{ status.data.version }} · 纯本地 · 只读 · 不联网</span>
    <div class="chips" v-if="status.data">
      <span class="chip">已索引 <b>{{ status.data.summary.total }}</b></span>
      <span class="chip">格式 <b>{{ Object.keys(status.data.summary.by_format).length }}</b> 种</span>
      <span class="chip" v-if="status.data.detected_dirs.length">
        已探测：{{ status.data.detected_dirs[0].label }}
      </span>
    </div>
    <div style="flex: 1"></div>
    <div class="progress-wrap" v-if="scanning">
      <div class="progress"><div :style="{ width: (scanProgress.total ? (scanProgress.done * 100 / scanProgress.total) : 5) + '%' }"></div></div>
      <span style="font-size: 11px; color: var(--muted)">
        {{ scanProgress.note || `索引中 ${scanProgress.done}/${scanProgress.total}` }}
      </span>
    </div>
    <button class="primary" :disabled="scanning" @click="startScan">
      {{ scanning ? '扫描中…' : '⟳ 扫描（增量）' }}
    </button>
  </header>

  <nav class="tabs">
    <button :class="{ active: tab === 'all' }" @click="tab = 'all'">全部表情</button>
    <button :class="{ active: tab === 'dups' }" @click="tab = 'dups'">重复组</button>
    <button :class="{ active: tab === 'tags' }" @click="tab = 'tags'">标签</button>
  </nav>

  <AllStickers v-if="tab === 'all'" :tag-filter="tagFilter" @refresh="refreshStatus" @notify="notify" />
  <Duplicates v-if="tab === 'dups'" @notify="notify" />
  <TagsView v-if="tab === 'tags'" @pick="gotoTag" />

  <div class="toast" v-if="toast.show" :class="{ err: toast.err }">{{ toast.msg }}</div>
</template>
