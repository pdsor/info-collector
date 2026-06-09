<template>
  <header class="srop-page-header">
    <div>
      <div class="srop-title-group">
        <BackButton v-if="showBack" @click="onBack" />
        <h1 class="srop-page-title">{{ title }}</h1>
      </div>
      <p v-if="description" class="srop-page-description">{{ description }}</p>
    </div>
    <div v-if="hasActions" class="srop-page-actions">
      <slot />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, useSlots } from 'vue';
import { useRouter } from 'vue-router';
import BackButton from './BackButton.vue';

interface Props {
  title: string;
  description?: string;
  showBack?: boolean;
  backTo?: string;
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
  showBack: false,
  backTo: '',
});

const emit = defineEmits<{ back: [] }>();

const slots = useSlots();
const hasActions = computed(() => !!slots.default);

const router = useRouter();
function onBack() {
  emit('back');
  if (props.backTo) {
    router.push(props.backTo);
  } else {
    router.back();
  }
}
</script>
