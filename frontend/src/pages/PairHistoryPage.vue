<template>
  <q-page class="page-pad">
    <div class="row items-center q-mb-md">
      <div class="text-h5">配对质控历史</div>
      <q-space />
      <q-btn flat icon="refresh" label="刷新" @click="load" :loading="loading" />
      <q-btn
        v-if="auth.role === 'bioops'"
        color="primary"
        class="q-ml-sm"
        label="新建配对作业"
        to="/pairs/new"
      />
    </div>

    <q-banner v-if="auth.role !== 'bioops'" class="bg-grey-3 text-dark q-mb-md" rounded>
      审计员只读：可查看配对结果，提交需运维账号。
    </q-banner>

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
      <template #body-cell-r1="props">
        <q-td :props="props">
          <div>{{ props.row.r1_sample_name }}</div>
          <q-badge :color="sideStatusColor(props.row.r1_status)" class="q-mt-xs">
            R1 {{ sideStatusLabel(props.row.r1_status) }}
          </q-badge>
        </q-td>
      </template>
      <template #body-cell-r2="props">
        <q-td :props="props">
          <div>{{ props.row.r2_sample_name }}</div>
          <q-badge :color="sideStatusColor(props.row.r2_status)" class="q-mt-xs">
            R2 {{ sideStatusLabel(props.row.r2_status) }}
          </q-badge>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props">
          <q-btn dense flat color="primary" label="对照详情" :to="`/pairs/${props.row.id}`" />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { listPairJobs } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const $q = useQuasar()
const loading = ref(false)
const rows = ref([])

const columns = [
  { name: 'id', label: 'ID', field: 'id', align: 'left' },
  { name: 'r1', label: 'R1 端', field: 'r1_sample_name', align: 'left' },
  { name: 'r2', label: 'R2 端', field: 'r2_sample_name', align: 'left' },
  { name: 'status', label: '整体状态', field: 'status', align: 'left' },
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
  return (
    {
      pending: '排队中',
      running: '运行中',
      success: '双侧成功',
      partial: '部分成功',
      failed: '双侧失败',
    }[s] || s
  )
}

function pairStatusColor(s) {
  return (
    {
      pending: 'grey',
      running: 'info',
      success: 'positive',
      partial: 'warning',
      failed: 'negative',
    }[s] || 'grey'
  )
}

function sideStatusLabel(s) {
  return { pending: '排队中', running: '运行中', success: '成功', failed: '失败' }[s] || s
}

function sideStatusColor(s) {
  return { pending: 'grey', running: 'info', success: 'positive', failed: 'negative' }[s] || 'grey'
}

async function load() {
  loading.value = true
  try {
    rows.value = await listPairJobs()
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
