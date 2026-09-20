<template>
  <q-page class="page-pad">
    <div class="text-h5 q-mb-md">提交配对质控（R1 / R2）</div>

    <q-banner v-if="auth.role !== 'bioops'" class="bg-warning text-dark q-mb-md" rounded>
      审计员不可提交作业，请使用 bioops 账号。
    </q-banner>

    <div class="row q-col-gutter-md">
      <div v-for="side in sides" :key="side.key" class="col-12 col-md-6">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-subtitle1 q-mb-sm">
              {{ side.label }}
              <q-badge v-if="isReady(side)" color="positive" class="q-ml-sm">已就绪</q-badge>
            </div>

            <div class="text-subtitle2 q-mb-xs">方式一：选择 seed 样例</div>
            <q-select
              v-model="side.sampleId"
              :options="sampleOptions"
              label="样例"
              outlined
              dense
              clearable
              emit-value
              map-options
              class="q-mb-md"
            />

            <div class="text-subtitle2 q-mb-xs">方式二：粘贴 FASTQ 文本</div>
            <q-input
              v-model="side.fastqText"
              type="textarea"
              outlined
              autogrow
              :input-style="{ minHeight: '140px', fontFamily: 'monospace' }"
              hint="四行一组：@header / 序列 / + / 质量串。若已选样例则优先用样例。"
            />
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-card flat bordered class="q-mt-md">
      <q-card-actions align="right">
        <q-btn flat label="取消" to="/pairs" />
        <q-btn
          color="primary"
          label="启动配对 Actor 流水线"
          :loading="submitting"
          @click="submit"
        />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { createPairJob, listSamples } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const $q = useQuasar()

const samples = ref([])
const submitting = ref(false)

const sides = reactive([
  { key: 'r1', label: 'R1 端（Read 1）', sampleId: null, fastqText: '' },
  { key: 'r2', label: 'R2 端（Read 2）', sampleId: null, fastqText: '' },
])

// 每侧是否已有输入（选中样例或贴了文本）
function isReady(side) {
  return Boolean(side.sampleId) || Boolean(side.fastqText.trim())
}

const sampleOptions = computed(() =>
  samples.value.map((s) => ({
    label: `${s.name}（${s.is_broken ? '损坏' : '合格'}）`,
    value: s.id,
  })),
)

async function load() {
  try {
    samples.value = await listSamples()
    // 支持从样例库带入：/pairs/new?r1SampleId=1&r2SampleId=2
    const r1 = route.query.r1SampleId
    const r2 = route.query.r2SampleId
    if (r1) sides[0].sampleId = Number(r1)
    if (r2) sides[1].sampleId = Number(r2)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载样例失败' })
  }
}

function sidePayload(side) {
  return side.sampleId
    ? { sampleId: side.sampleId }
    : { fastqText: side.fastqText }
}

async function submit() {
  const empty = sides.filter((s) => !isReady(s))
  if (empty.length) {
    $q.notify({
      type: 'warning',
      message: `${empty.map((s) => s.label).join('、')} 请选择样例或粘贴 FASTQ 文本`,
    })
    return
  }
  submitting.value = true
  try {
    const pair = await createPairJob({
      r1: sidePayload(sides[0]),
      r2: sidePayload(sides[1]),
    })
    $q.notify({ type: 'positive', message: `配对作业 #${pair.id} 已创建` })
    router.push(`/pairs/${pair.id}`)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '提交失败' })
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>
