<script setup>
import { computed, ref } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  ids: { type: Array, default: () => [] },
  allMode: { type: Boolean, default: false }, // 备份模式：导出索引内全部
})
const emit = defineEmits(['close', 'done'])

const dest = ref('')
const naming = ref(props.allMode ? 'md5' : 'orig')
const includeUnknown = ref(props.allMode)
const busy = ref(false)
const error = ref('')

const title = computed(() =>
  props.allMode ? `备份全部 ${props.ids.length} 个表情` : `导出 ${props.ids.length} 个表情`)

async function doExport() {
  if (!dest.value.trim()) {
    error.value = '请填写导出目的地文件夹（绝对路径）'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const r = await api.export(
      props.ids, dest.value.trim(), naming.value, includeUnknown.value, props.allMode)
    emit('done', r)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal">
      <h3>{{ title }}</h3>
      <div class="row">
        <input type="text" v-model="dest" placeholder="例如 D:\stickers-export（微信目录会被拒绝）" />
      </div>
      <div class="row">
        <select v-model="naming">
          <option value="orig">保留原名 + 补扩展名</option>
          <option value="md5">按 MD5 命名（内容相同自动去重）</option>
        </select>
      </div>
      <div class="row">
        <label style="display: flex; gap: 6px; align-items: center; font-size: 13px">
          <input type="checkbox" v-model="includeUnknown" />
          包含未知格式（微信新版加密表情按 .dat 原样备份）
        </label>
      </div>
      <div class="row">
        <button class="primary" :disabled="busy" @click="doExport">{{ busy ? '导出中…' : '开始' }}</button>
        <button @click="$emit('close')">取消</button>
      </div>
      <p class="hint">
        只复制文件到目的地，不会修改/删除微信里的原始表情；
        导出到微信目录或表情源目录会被安全护栏拒绝。
      </p>
      <p class="hint" style="color: var(--danger)" v-if="error">{{ error }}</p>
    </div>
  </div>
</template>
