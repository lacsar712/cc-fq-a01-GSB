<template>
  <q-page class="page-pad pair-wide">
    <div class="row items-center q-mb-md">
      <div class="text-h5">配对质控详情 #{{ pair?.id || '…' }}</div>
      <q-space />
      <q-btn flat icon="refresh" label="刷新" @click="load" :loading="loading" />
      <q-btn flat label="返回配对记录" to="/pair-runs" />
    </div>

    <q-banner v-if="pair" rounded class="q-mb-md" :class="pairBannerClass">
      <div>
        配对状态：{{ pairStatusLabel(pair.status) }}
        · 提交人：{{ pair.created_by }}
        <span v-if="pair.failed_side" class="q-ml-sm">
          <q-icon name="warning" />
          失败侧：{{ failedSideLabel(pair.failed_side) }}
        </span>
        <span v-else-if="pair.status === 'success'" class="q-ml-sm">
          <q-icon name="verified" /> 两侧均合格
        </span>
      </div>
      <div v-if="pair.error_message" class="q-mt-sm">{{ pair.error_message }}</div>
    </q-banner>

    <div class="row q-col-gutter-md">
      <div
        class="col-12 col-md-6"
        v-for="side in sideList"
        :key="side.key"
      >
        <q-card flat bordered :class="['side-card', side.key === 'r1' ? 'side-r1' : 'side-r2', { 'side-failed': side.data && side.data.status === 'failed' }]">
          <q-card-section>
            <div class="row items-center q-mb-sm">
              <q-avatar :color="side.key === 'r1' ? 'deep-purple' : 'teal'" text-color="white" :size="36">
                {{ side.label }}
              </q-avatar>
              <div class="q-ml-sm">
                <div class="text-subtitle1">{{ side.title }}</div>
                <div class="text-caption text-grey-7">{{ side.data?.sample_name || '—' }}</div>
              </div>
              <q-space />
              <q-badge v-if="side.data" :color="jobStatusColor(side.data.status)" :label="jobStatusLabel(side.data.status)" />
              <q-chip
                v-if="pair && pair.failed_side === side.key"
                dense
                color="negative"
                text-color="white"
                icon="error"
                label="失败侧"
              />
              <q-chip
                v-else-if="pair && pair.status === 'success'"
                dense
                color="positive"
                text-color="white"
                icon="check_circle"
                label="合格侧"
              />
            </div>

            <div v-if="!side.data" class="text-grey-6">等待该侧结果…</div>

            <template v-else>
              <div v-if="side.data.error_message" class="text-negative text-caption q-mb-sm bg-red-1 q-pa-sm rounded-borders">
                <q-icon name="error" size="14px" /> {{ side.data.error_message }}
              </div>

              <div class="text-caption text-grey-8 q-mb-xs">质控指标</div>
              <div v-if="metricCards(side.data).length" class="row q-col-gutter-xs q-mb-md">
                <div class="col-4" v-for="m in metricCards(side.data)" :key="m.label">
                  <q-card flat bordered class="metric-card">
                    <q-card-section class="q-pa-sm">
                      <div class="text-caption text-grey-7">{{ m.label }}</div>
                      <div class="text-subtitle1">{{ m.value }}</div>
                    </q-card-section>
                  </q-card>
                </div>
              </div>
              <div v-else class="text-grey-6 text-caption q-mb-md">
                无指标（{{ side.data.status === 'failed' ? '该侧解析/质控失败' : '运行中' }}）
              </div>

              <div class="text-caption text-grey-8 q-mb-xs">Actor 阶段</div>
              <q-list dense separator>
                <q-item v-for="s in side.data.stages" :key="s.id">
                  <q-item-section avatar>
                    <q-icon :name="stageIcon(s.status)" :color="stageColor(s.status)" size="20px" />
                  </q-item-section>
                  <q-item-section class="text-caption">
                    <q-item-label>{{ s.actor_name }}</q-item-label>
                    <q-item-label caption class="text-grey-7">
                      {{ s.message || '—' }}
                    </q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-badge dense :color="stageColor(s.status)">{{ stageLabel(s.status) }}</q-badge>
                  </q-item-section>
                </q-item>
              </q-list>
            </template>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useQuasar } from 'quasar'
import { getPairRun } from '../api/client'

const route = useRoute()
const $q = useQuasar()
const loading = ref(false)
const pair = ref(null)
let timer = null

const sideList = computed(() => [
  { key: 'r1', label: 'R1', title: '读段 1（正向）', data: pair.value?.r1 || null },
  { key: 'r2', label: 'R2', title: '读段 2（反向）', data: pair.value?.r2 || null },
])

const pairBannerClass = computed(() => {
  const s = pair.value?.status
  if (s === 'success') return 'bg-positive text-white'
  if (s === 'partial') return 'bg-orange text-white'
  if (s === 'failed') return 'bg-negative text-white'
  if (s === 'running') return 'bg-info text-dark'
  return 'bg-grey-3'
})

function pairStatusLabel(s) {
  return {
    pending: '排队中',
    running: '两侧运行中',
    success: '两侧均成功',
    partial: '单侧失败（另一侧结果已保留）',
    failed: '两侧均失败',
  }[s] || s
}

function failedSideLabel(s) {
  return { r1: 'R1（正向）', r2: 'R2（反向）', both: 'R1 与 R2 两侧' }[s] || s
}

function jobStatusLabel(s) {
  return { pending: '排队', running: '运行中', success: '成功', failed: '失败' }[s] || s
}

function jobStatusColor(s) {
  return { pending: 'grey', running: 'info', success: 'positive', failed: 'negative' }[s] || 'grey'
}

function stageLabel(s) {
  return { pending: '待执行', running: '运行中', success: '成功', failed: '失败', skipped: '跳过' }[s] || s
}

function stageColor(status) {
  return (
    {
      pending: 'grey',
      running: 'info',
      success: 'positive',
      failed: 'negative',
      skipped: 'warning',
    }[status] || 'grey'
  )
}

function stageIcon(status) {
  return (
    {
      pending: 'hourglass_empty',
      running: 'play_circle',
      success: 'check_circle',
      failed: 'error',
      skipped: 'skip_next',
    }[status] || 'circle'
  )
}

function metricCards(data) {
  const m = data.metrics
  if (!m) return []
  return [
    { label: 'reads', value: m.reads ?? m.summary?.reads ?? '—' },
    { label: 'mean_quality', value: m.mean_quality ?? m.summary?.mean_quality ?? '—' },
    { label: 'n_rate', value: m.n_rate ?? m.summary?.n_rate ?? '—' },
  ]
}

async function load() {
  loading.value = true
  try {
    pair.value = await getPairRun(route.params.id)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  timer = setInterval(async () => {
    if (pair.value && ['pending', 'running'].includes(pair.value.status)) {
      await load()
    }
  }, 1500)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.pair-wide {
  max-width: 1280px;
}
.side-r1 {
  border-top: 3px solid #5e35b1;
}
.side-r2 {
  border-top: 3px solid #00897b;
}
.side-card.side-failed {
  box-shadow: 0 0 0 2px rgba(198, 40, 40, 0.35);
}
.metric-card .q-card__section {
  min-height: 64px;
}
</style>
