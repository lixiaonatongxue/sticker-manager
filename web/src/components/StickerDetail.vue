<script setup>
import { computed, ref } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  sticker: { type: Object, required: true },
})
const emit = defineEmits(['close', 'updated'])

const tags = computed(() =>
  props.sticker.tags ? props.sticker.tags.split(',').filter(Boolean) : [])
const newTag = ref('')
const busy = ref(false)
const error = ref('')

async function saveTags(next) {
  busy.value = true
  error.value = ''
  try {
    const s = await api.setTags(props.sticker.id, next)
    emit('updated', s)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function addTag() {
  const t = newTag.value.trim()
  if (!t || tags.value.includes(t)) { newTag.value = ''; return }
  saveTags([...tags.value, t])
  newTag.value = ''
}

function removeTag(t) {
  saveTags(tags.value.filter(x => x !== t))
}
</script>

<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal detail">
      <div class="detail-body">
        <div class="detail-img">
          <img
            v-if="['gif', 'png', 'jpg', 'jpeg', 'webp', 'bmp'].includes(sticker.format)"
            :src="'/api/thumbnail/' + sticker.id"
          />
          <span v-else class="placeholder">{{ sticker.format === 'mp4' ? '🎬' : '❓' }}</span>
        </div>
        <div class="detail-side">
          <h3 style="margin-top:0">表情 #{{ sticker.id }}</h3>
          <table class="meta-table">
            <tr><td>格式</td><td>{{ sticker.format }}</td></tr>
            <tr><td>尺寸</td><td>{{ sticker.width ? sticker.width + '×' + sticker.height : '—' }}</td></tr>
            <tr><td>帧数</td><td>{{ sticker.frames ?? '—' }}</td></tr>
            <tr><td>大小</td><td>{{ (sticker.size / 1024).toFixed(1) }} KB</td></tr>
            <tr><td>收藏时间</td><td>{{ sticker.first_seen }}</td></tr>
            <tr><td>MD5</td><td class="mono">{{ sticker.md5 }}</td></tr>
          </table>
          <p class="hint mono" style="word-break: break-all">{{ sticker.path }}</p>

          <div class="tag-edit">
            <div class="tagrow">
              <span class="tag-chip" v-for="t in tags" :key="t">
                {{ t }} <b @click="removeTag(t)" title="移除">×</b>
              </span>
              <span v-if="!tags.length" class="hint">暂无标签</span>
            </div>
            <div class="row">
              <input
                type="text" v-model="newTag" placeholder="添加标签，如：猫 / 开心 / 文字梗"
                :disabled="busy" @keyup.enter="addTag"
              />
              <button class="primary" :disabled="busy || !newTag.trim()" @click="addTag">添加</button>
            </div>
            <p class="hint" style="color: var(--danger)" v-if="error">{{ error }}</p>
          </div>
          <div class="row">
            <button @click="$emit('close')">关闭</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail { width: min(640px, 94vw); }
.detail-body { display: flex; gap: 18px; }
.detail-img {
  flex: 0 0 280px; aspect-ratio: 1; border-radius: 10px;
  background: #fafbfc; border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
}
.detail-img img { max-width: 100%; max-height: 100%; object-fit: contain; }
.detail-img .placeholder { font-size: 64px; opacity: .4; }
.detail-side { flex: 1; min-width: 0; }
.meta-table { font-size: 13px; border-spacing: 0 4px; }
.meta-table td:first-child { color: var(--muted); padding-right: 12px; white-space: nowrap; }
.mono { font-family: Consolas, monospace; font-size: 12px; }
.tag-edit { margin: 10px 0; }
.tagrow { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.tag-chip {
  background: #e0ecff; color: #1d4ed8; border-radius: 999px;
  padding: 3px 10px; font-size: 13px;
}
.tag-chip b { cursor: pointer; margin-left: 4px; }
.tag-chip b:hover { color: var(--danger); }
</style>
