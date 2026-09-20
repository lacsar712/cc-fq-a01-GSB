<template>
  <q-page class="page-pad pair-page">
    <div class="row items-center q-mb-md">
      <div class="text-h5">配对作业详情 #{{ pair?.id || '…' }}</div>
      <q-space />
      <q-btn flat icon="refresh" label="刷新" @click="load" :loading="loading" />
      <q-btn flat label="返回配对历史" to="/pairs" />
    </div>

    <q-banner v-if="pair" rounded class="q-mb-md" :class="pairBannerClass">
      整体状态：{{ pairStatusLabel(pair.status) }}
      · 提交人：{{ pair.created_by }}
      <span v-if="failedSides.length"> · 失败侧：{{ failedSides.join('、') }}</span>
      <span v-else-if="pair.status === 'success'"> · 双侧均通过</span>
    </q-banner>

    <!-- 左右分栏：R1 / R2 对照 -->
    <div class="row q-col-gutter-md" v-if="pair">
      <div v-for="side in sideViews" :key="side.key" class="col-12 col-md-6">
        <q-card flat bordered :class="['side-card', side.failed ? 'side-card-failed' : '']">
          <q-card-section class="row items-center">
            <div class="text-h6">{{ side.key }} 端</div>
            <q-badge
              v-if="side.failed"
              color="negative"
              class="q-ml-sm"
              label="失败侧"
            />
            <q-space />
            <q-badge :color="sideStatusColor(side.status)">
              {{ sideStatusLabel(side.status) }}
            </q-badge>
          </q-card-section>
          <q-separator />
          <q-card-section>
            <div class="text-caption text-grey-7">样例</div>
            <div class="q-mb-md">{{ side.sampleName }}</div>

            <q-banner v-if="side.error" rounded dense class="bg-red-1 text-negative q-mb-md">
              失败原因：{{ side.error }}
            </q-banner>

            <div class="text-subtitle2 q-mb-xs">Actor 阶段</div>
            <div class="q-mb-md">
              <div
                v-for="st in side.stages"
                :key="st.id"
                class="row items-center q-py-xs stage-row"
              >
                <q-icon
                  :name="stageIcon(st.status)"
                  :color="stageColor(st.status)"
                  size="20px"
                  class="q-mr-sm"
                />
                <div>{{ st.actor_name }}</div>
                <q-space />
                <q-badge :color="stageColor(st.status)" :label="stageStatusLabel(st.status)" />
                <div class="text-caption text-grey-7 q-ml-sm stage-msg">
                  {{ st.message || '—' }}
                </div>
              </div>
              <div v-if="!side.stages.length" class="text-grey-6">尚无阶段记录</div>
            </div>

            <div class="text-subtitle2 q-mb-xs">质控指标</div>
            <div class="row q-col-gutter-sm" v-if="side.metricCards.length">
              <div class="col-4" v-for="m in side.metricCards" :key="m.label">
                <q-card flat bordered class="metric-card">
                  <q-card-section>
                    <div class="text-caption text-grey-7">{{ m.label }}</div>
                    <div class="text-h6">{{ m.value }}</div>
                  </q-card-section>
                </q-card>
              </div>
            </div>
            <div v-else class="text-grey-6">该侧暂无指标</div>
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
import { getPairJob, getPairJobStages } from '../api/client'

const route = useRoute()
const $q = useQuasar()
const loading = ref(false)
const pair = ref(null)
const stages = ref([])
let timer = null

const SIDE_KEYS = ['R1', 'R2']

const failedSides = computed(() => {
  if (!pair.value) return []
  return SIDE_KEYS.filter((k) => pair.value[`${k.toLowerCase()}_status`] === 'failed').map(
    (k) => `${k} 端`,
  )
})

const sideViews = computed(() => {
  if (!pair.value) return []
  return SIDE_KEYS.map((key) => {
    const lk = key.toLowerCase()
    const metrics = pair.value[`${lk}_metrics`] || null
    const status = pair.value[`${lk}_status`]
    return {
      key,
      status,
      failed: status === 'failed',
      sampleName: pair.value[`${lk}_sample_name`],
      error: pair.value[`${lk}_error`],
      stages: stages.value.filter((s) => s.side === key),
      metricCards: metrics
        ? [
            { label: 'reads', value: metrics.reads ?? metrics.summary?.reads ?? '—' },
            {
              label: 'mean_quality',
              value: metrics.mean_quality ?? metrics.summary?.mean_quality ?? '—',
            },
            { label: 'n_rate', value: metrics.n_rate ?? metrics.summary?.n_rate ?? '—' },
          ]
        : [],
    }
  })
})

const pairBannerClass = computed(() => {
  const s = pair.value?.status
  if (s === 'success') return 'bg-positive text-white'
  if (s === 'failed') return 'bg-negative text-white'
  if (s === 'partial') return 'bg-warning text-dark'
  if (s === 'running') return 'bg-info text-dark'
  return 'bg-grey-3'
})

function pairStatusLabel(s) {
  return (
    {
      pending: '排队中',
      running: '运行中',
      success: '双侧成功',
      partial: '部分成功（一侧失败）',
      failed: '双侧失败',
    }[s] || s
  )
}

function sideStatusLabel(s) {
  return { pending: '排队中', running: '运行中', success: '成功', failed: '失败' }[s] || s
}

function sideStatusColor(s) {
  return { pending: 'grey', running: 'info', success: 'positive', failed: 'negative' }[s] || 'grey'
}

function stageStatusLabel(s) {
  return (
    { pending: '排队中', running: '运行中', success: '成功', failed: '失败', skipped: '跳过' }[s] ||
    s
  )
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

async function load() {
  loading.value = true
  try {
    const id = route.params.id
    pair.value = await getPairJob(id)
    stages.value = await getPairJobStages(id)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  timer = setInterval(async () => {
    if (pair.value && (pair.value.status === 'pending' || pair.value.status === 'running')) {
      await load()
    }
  }, 1500)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.side-card-failed {
  border-color: var(--q-negative);
}
.stage-msg {
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
