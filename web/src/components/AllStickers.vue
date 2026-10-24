<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api.js'
import StickerCard from './StickerCard.vue'
import ExportDialog from './ExportDialog.vue'

const props = defineProps({ tagFilter: { type: String, default: '' } })
const emit = defineEmits(['notify'])

const items = ref([])
const total = ref(0)
const page = ref(1)
const perPage = 60
const loading = ref(false)
const fmt = ref('')
const tag = ref(props.tagFilter)
const q = ref('')
const selected = reactive(new Set())
const showExport = ref(false)

const formats = ['gif', 'png', 'jpg', 'webp', 'bmp', 'mp4', 'unknown']
const tags = ref([])

const pages = computed(() => Math.max(1, Math.ceil(total.value / perPage)))

async function load() {
  loading.value = true
  try {
    const r = await api.stickers({
      page: page.value, per_page: perPage,
      format: fmt.value || undefined,
      tag: tag.value || undefined,
      q: q.value || undefined,
    })
    items.value = r.items
    total.value = r.total
  } catch (e) {
    emit('notify', e.message, true)
  } finally {
    loading.value = false
  }
}

async function loadTags() {
  try { tags.value = await api.allTags() } catch { /* ignore */ }
}

function toggle(id) {
  selected.has(id) ? selected.delete(id) : selected.add(id)
}
function selectAll() {
  items.value.forEach(i => selected.add(i.id))
}
function clearSel() {
  selected.clear()
}

watch([page, fmt], load)
watch(() => props.tagFilter, v => { tag.value = v; page.value = 1; load() })
watch(tag, () => { page.value = 1; load() })

let qTimer = null
watch(q, () => {
  clearTimeout(qTimer)
  qTimer = setTimeout(() => { page.value = 1; load() }, 400)
})

function onExportDone(r) {
  showExport.value = false
  selected.clear()
  emit('notify', `导出完成：成功 ${r.summary.exported}，跳过 ${r.summary.skipped}，失败 ${r.summary.errors}`)
}

onMounted(() => { load(); loadTags() })
</script>

<template>
  <div>
    <div class="toolbar">
      <select v-model="fmt">
        <option value="">全部格式</option>
        <option v-for="f in formats" :key="f" :value="f">{{ f }}</option>
      </select>
      <select v-model="tag">
        <option value="">全部标签</option>
        <option v-for="t in tags" :key="t.tag" :value="t.tag">{{ t.tag }}（{{ t.count }}）</option>
      </select>
      <input type="text" v-model="q" placeholder="搜索文件路径…" style="width: 200px" />
      <span style="color: var(--muted)">共 {{ total }} 个</span>
      <div style="flex: 1"></div>
      <button @click="selectAll">全选本页</button>
      <button @click="clearSel" :disabled="!selected.size">清空选择</button>
    </div>

    <div class="loader" v-if="loading">加载中…</div>
    <div class="empty" v-else-if="!items.length">
      还没有表情。点击右上角「⟳ 扫描（增量）」，或先用命令行
      <code>sticker-manager scan --path 目录</code> 建立索引。
    </div>
    <div class="grid" v-else>
      <StickerCard
        v-for="s in items" :key="s.id"
        :sticker="s"
        :selected="selected.has(s.id)"
        @toggle="toggle"
      />
    </div>

    <div class="pager" v-if="pages > 1">
      <button :disabled="page <= 1" @click="page--">‹ 上一页</button>
      <span style="align-self: center; color: var(--muted)">{{ page }} / {{ pages }}</span>
      <button :disabled="page >= pages" @click="page++">下一页 ›</button>
    </div>

    <div class="footer-bar" v-if="selected.size">
      <span>已选 <b>{{ selected.size }}</b> 个</span>
      <div style="flex: 1"></div>
      <button class="primary" @click="showExport = true">⬇ 导出选中</button>
    </div>

    <ExportDialog v-if="showExport" :ids="[...selected]" @close="showExport = false" @done="onExportDone" />
  </div>
</template>
