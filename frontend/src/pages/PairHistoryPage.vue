<template>
  <q-page class="page-pad">
    <div class="row items-center q-mb-md">
      <div class="text-h5">双端配对记录</div>
      <q-space />
      <q-btn flat icon="refresh" label="刷新" @click="load" :loading="loading" />
      <q-btn
        v-if="auth.role === 'bioops'"
        color="primary"
        class="q-ml-sm"
        label="新建配对"
        to="/pair-runs/new"
      />
    </div>

    <q-table
      flat
      bordered
      row-key="id"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      hide-pagination
      :pagination="{ rowsPerPage: 0 }"
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-badge :color="pairStatusColor(props.row.status)">
            {{ pairStatusLabel(props.row.status) }}
          </q-badge>
        </q-td>
      </template>
      <template #body-cell-sides="props">
        <q-td :props="props">
          <div class="text-caption">
            <q-icon name="labels" color="deep-purple" size="14px" />
            R1：{{ props.row.r1_name }}
            <q-badge dense class="q-ml-xs" :color="jobStatusColor(props.row.r1_status)">
              {{ jobStatusLabel(props.row.r1_status) }}
            </q-badge>
          </div>
          <div class="text-caption q-mt-xs">
            <q-icon name="labels" color="teal" size="14px" />
            R2：{{ props.row.r2_name }}
            <q-badge dense class="q-ml-xs" :color="jobStatusColor(props.row.r2_status)">
              {{ jobStatusLabel(props.row.r2_status) }}
            </q-badge>
          </div>
        </q-td>
      </template>
      <template #body-cell-failed_side="props">
        <q-td :props="props">
          <q-badge v-if="props.row.failed_side" color="negative">
            {{ failedSideLabel(props.row.failed_side) }}
          </q-badge>
          <span v-else-if="props.row.status === 'success'" class="text-positive">无（两侧合格）</span>
          <span v-else class="text-grey-6">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props">
          <q-btn dense flat color="primary" label="对照详情" :to="`/pair-runs/${props.row.id}`" />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { listPairRuns } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const $q = useQuasar()
const loading = ref(false)
const rows = ref([])

const columns = [
  { name: 'id', label: 'ID', field: 'id', align: 'left' },
  { name: 'status', label: '配对状态', field: 'status', align: 'left' },
  { name: 'sides', label: '两侧样例 / 结果', field: 'sides', align: 'left' },
  { name: 'failed_side', label: '失败侧', field: 'failed_side', align: 'left' },
  { name: 'created_by', label: '提交人', field: 'created_by', align: 'left' },
  {
    name: 'created_at',
    label: '创建时间',
    field: 'created_at',
    align: 'left',
    format: (v) => (v ? new Date(v).toLocaleString() : ''),
  },
  { name: 'actions', label: '操作', field: 'actions', align: 'left' },
]

function pairStatusLabel(s) {
  return {
    pending: '排队中',
    running: '运行中',
    success: '两侧均成功',
    partial: '单侧失败',
    failed: '两侧均失败',
  }[s] || s
}

function pairStatusColor(s) {
  return {
    pending: 'grey',
    running: 'info',
    success: 'positive',
    partial: 'orange',
    failed: 'negative',
  }[s] || 'grey'
}

function failedSideLabel(s) {
  return { r1: 'R1', r2: 'R2', both: 'R1 与 R2' }[s] || s
}

function jobStatusLabel(s) {
  return { pending: '排队', running: '运行中', success: '成功', failed: '失败' }[s] || '—'
}

function jobStatusColor(s) {
  return { pending: 'grey', running: 'info', success: 'positive', failed: 'negative' }[s] || 'grey'
}

async function load() {
  loading.value = true
  try {
    rows.value = await listPairRuns()
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
