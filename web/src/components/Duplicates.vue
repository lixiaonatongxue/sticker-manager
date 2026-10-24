<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api.js'
import StickerCard from './StickerCard.vue'
import ExportDialog from './ExportDialog.vue'

const emit = defineEmits(['notify'])

const summary = ref(null)
const groups = ref([])
const loading = ref(false)
const computing = ref(false)
const threshold = ref(8)
const selected = reactive(new Set())
const showExport = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.duplicates()
    summary.value = r.summary
    groups.value = r.groups
  } catch (e) {
    emit('notify', e.message, true)
  } finally {
    loading.value = false
  }
}

async function recompute() {
  computing.value = true
  try {
    const s = await api.computeDuplicates(threshold.value)
    emit('notify', `已重算：${s.n_groups} 组重复，可精简 ${s.dup_files} 个文件`)
    await load()
  } catch (e) {
    emit('notify', e.message, true)
  } finally {
    computing.value = false
  }
}

function toggle(id) {
  selected.has(id) ? selected.delete(id) : selected.add(id)
}
function selectKeepers() {
  groups.value.forEach(g => selected.add(g.keeper_id))
}
/** 选中"可精简"的重复项（每组除 keeper 外全部）——导出它们做归档后即可自行清理 */
function selectExtras() {
  groups.value.forEach(g => g.members.forEach(m => {
    if (m.id !== g.keeper_id) selected.add(m.id)
  }))
}
function selectGroup(g) {
  g.members.forEach(m => selected.add(m.id))
}

function onExportDone(r) {
  showExport.value = false
  selected.clear()
  emit('notify', `导出完成：成功 ${r.summary.exported}，跳过 ${r.summary.skipped}，失败 ${r.summary.errors}`)
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <template v-if="summary">
        <span>重复组 <b>{{ summary.n_groups }}</b>（精确 {{ summary.n_exact }} / 近似 {{ summary.n_near }}）</span>
        <span>可精简文件 <b>{{ summary.dup_files }}</b> 个</span>
      </template>
      <span style="color: var(--muted)" v-else>尚未计算重复组</span>
      <div style="flex: 1"></div>
      <label style="color: var(--muted); font-size: 12px">
        阈值
        <input type="text" v-model="threshold" style="width: 40px; text-align: center" />
      </label>
      <button :disabled="computing" @click="recompute">{{ computing ? '计算中…' : '⟳ 重算重复组' }}</button>
      <button v-if="summary && summary.n_groups" @click="selectKeepers">选全部最优</button>
      <button v-if="summary && summary.n_groups" @click="selectExtras">选全部可精简项</button>
    </div>

    <div class="loader" v-if="loading">加载中…</div>
    <div class="empty" v-else-if="!groups.length">
      没有重复组 🎉（先扫描并点击「重算重复组」）
    </div>

    <div class="group" v-for="g in groups" :key="g.group_id">
      <div class="ghead">
        <span class="kind" :class="g.kind">{{ g.kind === 'exact' ? '完全相同' : '视觉近似' }}</span>
        <span style="color: var(--muted)">{{ g.members.length }} 个文件</span>
        <div style="flex: 1"></div>
        <button style="font-size: 12px" @click="selectGroup(g)">全选本组</button>
      </div>
      <div class="members">
        <StickerCard
          v-for="m in g.members" :key="m.id"
          :sticker="m"
          :selected="selected.has(m.id)"
          :is-keeper="m.id === g.keeper_id"
          @toggle="toggle"
        />
      </div>
    </div>

    <div class="footer-bar" v-if="selected.size">
      <span>已选 <b>{{ selected.size }}</b> 个</span>
      <div style="flex: 1"></div>
      <button class="primary" @click="showExport = true">⬇ 导出选中</button>
    </div>

    <ExportDialog v-if="showExport" :ids="[...selected]" @close="showExport = false" @done="onExportDone" />
  </div>
</template>
