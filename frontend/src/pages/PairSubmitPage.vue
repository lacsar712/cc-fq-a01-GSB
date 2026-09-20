<template>
  <q-page class="page-pad">
    <div class="text-h5 q-mb-md">提交双端配对质控</div>

    <q-banner v-if="auth.role !== 'bioops'" class="bg-warning text-dark q-mb-md" rounded>
      审计员只读，不可提交配对作业，请使用 bioops 账号。
    </q-banner>

    <q-banner class="bg-blue-1 q-mb-md text-dark" rounded>
      将两条读段（R1 / R2）一次送入，服务端为每侧各跑一条 Actor 链；一侧解析失败时，
      另一侧结果仍保留，并在详情中标明失败侧。
    </q-banner>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-6" v-for="side in sides" :key="side.key">
        <q-card flat bordered :class="side.key === 'r1' ? 'side-r1' : 'side-r2'">
          <q-card-section>
            <div class="row items-center q-mb-sm">
              <q-avatar :color="side.key === 'r1' ? 'deep-purple' : 'teal'" text-color="white" :size="32">
                {{ side.label }}
              </q-avatar>
              <div class="text-subtitle1 q-ml-sm">{{ side.title }}</div>
            </div>

            <div class="text-caption q-mb-xs">方式一：选择样例</div>
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

            <div class="text-caption q-mb-xs">方式二：粘贴 FASTQ 文本</div>
            <q-input
              v-model="side.fastqText"
              type="textarea"
              outlined
              autogrow
              :input-style="{ minHeight: '120px', fontFamily: 'monospace' }"
              hint="四行一组：@header / 序列 / + / 质量串。已选样例时优先用样例。"
            />
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-card-actions align="right" class="q-mt-md">
      <q-btn flat label="取消" to="/pair-runs" />
      <q-btn color="primary" label="两侧同时开跑" :loading="submitting" @click="submit" />
    </q-card-actions>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { createPairRun, listSamples } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const $q = useQuasar()

const samples = ref([])
const submitting = ref(false)

const sides = ref([
  { key: 'r1', label: 'R1', title: '读段 1（正向）', sampleId: null, fastqText: '' },
  { key: 'r2', label: 'R2', title: '读段 2（反向）', sampleId: null, fastqText: '' },
])

const sampleOptions = ref([])

async function load() {
  try {
    samples.value = await listSamples()
    sampleOptions.value = samples.value.map((s) => ({
      label: `${s.name}（${s.is_broken ? '损坏' : '合格'}）`,
      value: s.id,
    }))
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载样例失败' })
  }
}

function sideBody(side) {
  return side.sampleId ? { sampleId: side.sampleId } : { fastqText: side.fastqText }
}

async function submit() {
  for (const side of sides.value) {
    if (!side.sampleId && !side.fastqText.trim()) {
      $q.notify({ type: 'warning', message: `${side.label} 侧请选择样例或粘贴 FASTQ 文本` })
      return
    }
  }
  submitting.value = true
  try {
    const [r1, r2] = sides.value
    const pair = await createPairRun({ r1: sideBody(r1), r2: sideBody(r2) })
    $q.notify({ type: 'positive', message: `配对 #${pair.id} 已创建，两侧 Actor 链开跑` })
    router.push(`/pair-runs/${pair.id}`)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '提交失败' })
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.side-r1 {
  border-top: 3px solid #5e35b1;
}
.side-r2 {
  border-top: 3px solid #00897b;
}
</style>
