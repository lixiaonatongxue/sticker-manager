<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'

const emit = defineEmits(['pick'])
const tags = ref([])
const loading = ref(true)
const newTag = ref('')
const stickerId = ref('')
const busy = ref(false)

async function load() {
  loading.value = true
  try {
    tags.value = await api.allTags()
  } finally {
    loading.value = false
  }
}

async function addTag() {
  const id = parseInt(stickerId.value)
  const name = newTag.value.trim()
  if (!id || !name) return
  busy.value = true
  try {
    const s = await api.sticker(id)
    const merged = s.tags ? s.tags.split(',').concat([name]) : [name]
    await api.setTags(id, merged)
    stickerId.value = ''
    newTag.value = ''
    await load()
  } catch (e) {
    alert('添加失败：' + e.message)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>给表情打标签：</span>
      <input type="text" v-model="stickerId" placeholder="表情 id" style="width: 90px" />
      <input type="text" v-model="newTag" placeholder="标签名，如：猫 / 开心 / 文字梗" style="width: 220px" />
      <button class="primary" :disabled="busy" @click="addTag">添加</button>
      <span style="color: var(--muted)">（在「全部表情」里点击卡片可看到 id；后续版本支持点图打标签与自动打标）</span>
    </div>

    <div class="loader" v-if="loading">加载中…</div>
    <div class="empty" v-else-if="!tags.length">还没有任何标签</div>
    <div class="taglist" v-else>
      <button v-for="t in tags" :key="t.tag" @click="emit('pick', t.tag)">
        {{ t.tag }} · {{ t.count }}
      </button>
    </div>
  </div>
</template>
