<script setup>
defineProps({
  sticker: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  isKeeper: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
defineEmits(['toggle'])
</script>

<template>
  <div class="scard" :class="{ selected }" @click="$emit('toggle', sticker.id)">
    <div class="check"></div>
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
  </div>
</template>
