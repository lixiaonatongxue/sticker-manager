<script setup>
defineProps({
  sticker: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  isKeeper: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
defineEmits(['toggle', 'open'])
</script>

<template>
  <div class="scard" :class="{ selected }" @click="$emit('open', sticker)">
    <div class="check" title="勾选导出" @click.stop="$emit('toggle', sticker.id)"></div>
    <span class="star" v-if="isKeeper">★ 最优</span>
    <div class="thumb">
      <img
        v-if="['gif', 'png', 'jpg', 'jpeg', 'webp', 'bmp'].includes(sticker.format)"
        :src="'/api/thumbnail/' + sticker.id"
        loading="lazy"
        :alt="sticker.path"
      />
      <span v-else class="placeholder">{{ sticker.format === 'mp4' ? '🎬' : '❓' }}</span>
    </div>
    <div class="meta">
      <span class="badge">{{ sticker.format }}</span>
      <span v-if="sticker.width">{{ sticker.width }}×{{ sticker.height }}</span>
      <span v-else>—</span>
      <span>{{ (sticker.size / 1024).toFixed(0) }}KB</span>
    </div>
    <div class="tagrow" v-if="sticker.tags">
      <span class="mini-tag" v-for="t in sticker.tags.split(',')" :key="t">{{ t }}</span>
    </div>
  </div>
</template>

<style scoped>
.tagrow { display: flex; gap: 3px; flex-wrap: wrap; padding: 0 6px 6px; }
.mini-tag {
  font-size: 10px; background: #e0ecff; color: #1d4ed8;
  border-radius: 4px; padding: 1px 5px;
}
</style>
