<template>
  <div class="op-attachment-section">
    <div class="op-attachment-toolbar">
      <div class="op-attachment-toolbar__filters">
        <el-select
          v-model="filterCategory"
          size="small"
          clearable
          placeholder="全部分类"
          style="width: 130px"
          @change="load"
        >
          <el-option
            v-for="c in categories"
            :key="c.value"
            :label="c.label"
            :value="c.value"
          />
        </el-select>
        <el-select
          v-if="!readonly && hasValidTarget"
          v-model="uploadCategory"
          size="small"
          style="width: 130px"
          title="上传时使用的分类"
        >
          <el-option
            v-for="c in categories"
            :key="c.value"
            :label="`上传分类：${c.label}`"
            :value="c.value"
          />
        </el-select>
        <el-checkbox v-model="includeHidden" size="small" @change="load">显示隐藏项</el-checkbox>
      </div>
      <div class="op-attachment-toolbar__right">
        <span class="op-attachment-count">{{ items.length }} 个附件</span>
      </div>
    </div>

    <el-upload
      v-if="!readonly && hasValidTarget"
      class="op-attachment-upload"
      drag
      multiple
      :show-file-list="false"
      :disabled="uploading"
      :before-upload="beforeUpload"
      :http-request="handleUpload"
    >
      <div class="op-attachment-upload__inner">
        <AppIcon name="file" size="lg" />
        <p class="op-attachment-upload__text">
          拖拽文件到此处，或 <em>点击选择文件</em>
        </p>
        <p class="op-attachment-upload__hint">单个文件不超过 {{ maxFileMb }}MB，上传中请勿关闭页面</p>
      </div>
    </el-upload>

    <div v-else-if="!readonly" class="op-attachment-hint">
      <AppIcon name="info" size="sm" />
      <span>保存单据后可上传附件。</span>
    </div>

    <el-table
      v-loading="loading"
      :data="items"
      size="small"
      max-height="420"
      empty-text="暂无附件"
    >
      <el-table-column label="文件" min-width="240">
        <template #default="{ row }">
          <div class="op-attachment-file">
            <button
              v-if="isPreviewable(row)"
              type="button"
              class="op-attachment-file__name op-attachment-file__name--link"
              @click="handlePreview(row)"
            >{{ row.file_name }}</button>
            <span v-else class="op-attachment-file__name">{{ row.file_name }}</span>
            <span class="op-attachment-file__meta">{{ row.code }} · {{ row.mime_type || '未知类型' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="110">
        <template #default="{ row }">
          <span>{{ categoryLabel(row.category) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">
          <span>{{ formatSize(row.size_bytes) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上传人" width="110">
        <template #default="{ row }">
          <span>{{ row.uploaded_by || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="150">
        <template #default="{ row }">
          <span>{{ formatTime(row.uploaded_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <div class="op-attachment-actions">
            <el-button link type="primary" size="small" @click="handleDownload(row)">下载</el-button>
            <el-button
              v-if="!readonly"
              link
              type="danger"
              size="small"
              :loading="unlinkingId === row.link_id"
              @click="handleUnlink(row)"
            >解除挂接</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="preview.visible"
      :title="preview.item?.file_name || '附件预览'"
      width="72%"
      destroy-on-close
      @closed="closePreview"
    >
      <div class="op-attachment-preview" v-loading="preview.loading">
        <img
          v-if="preview.kind === 'image'"
          :src="preview.url"
          :alt="preview.item?.file_name"
          class="op-attachment-preview__image"
        >
        <iframe
          v-else-if="preview.kind === 'pdf'"
          :src="preview.url"
          class="op-attachment-preview__frame"
          title="PDF 预览"
        />
        <div v-else class="op-attachment-preview__fallback">
          <p>该类型不支持在线预览。</p>
          <el-button type="primary" size="small" @click="handleDownload(preview.item)">下载查看</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import AppIcon from '../AppIcon/AppIcon.vue'
import { useMessage } from '@/composables/useMessage'
import {
  getAttachmentCategories,
  uploadAttachment,
  queryByTarget,
  unlinkAttachment,
  fetchAttachmentBlob,
  downloadAttachment,
} from '@/services/attachmentService'

const props = defineProps({
  objectType: { type: String, default: null },
  objectId: { type: [String, Number], default: null },
  readonly: { type: Boolean, default: false },
  section: { type: Object, default: () => ({}) },
})

const message = useMessage()

const ERROR_MAP = {
  attachment_too_large: '文件超过大小上限',
  attachment_limit_exceeded: '该对象附件数量已达上限',
  attachment_invalid_mime: '不支持的文件类型',
  attachment_duplicate_link: '该附件已挂接到当前对象',
  attachment_duplicate_primary: '该对象已存在同类主附件',
  attachment_not_found: '附件不存在或已被删除',
  attachment_link_not_found: '挂接记录不存在',
  attachment_missing_file: '附件文件已缺失',
  attachment_storage_error: '附件存储异常，请稍后重试',
  attachment_target_invalid: '当前对象不支持附件',
  attachment_visibility_unsupported: '不支持的可见性设置',
  attachment_in_use: '附件仍被引用，无法删除',
}

const items = ref([])
const loading = ref(false)
// 分类下拉：唯一来源为后端 attachment_category 枚举（metaEnumService fail-closed）
const categories = ref([])
const categoryLabelMap = computed(() => {
  const map = {}
  for (const c of categories.value) map[c.value] = c.label
  return map
})

function categoryLabel(value) {
  return categoryLabelMap.value[value] || value || '其他'
}
const uploadingCount = ref(0)
const uploading = computed(() => uploadingCount.value > 0)
const unlinkingId = ref(null)
const includeHidden = ref(false)
const filterCategory = ref(null)
const uploadCategory = ref('other')

const maxFileMb = computed(() => {
  const cfg = props.section?.props?.maxFileSizeMb
  const n = Number(cfg)
  return Number.isFinite(n) && n > 0 ? n : 50
})

const hasValidTarget = computed(() => {
  if (!props.objectType) return false
  const id = props.objectId
  if (id === null || id === undefined) return false
  const str = String(id).trim()
  return str !== '' && str !== 'new' && str !== '0'
})

function friendlyError(res) {
  const code = res?.businessCode || res?.code
  return ERROR_MAP[code] || res?.message || '操作失败'
}

function formatSize(bytes) {
  const n = Number(bytes)
  if (!Number.isFinite(n) || n < 0) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

function isPreviewable(row) {
  const mime = row?.mime_type || ''
  return mime.startsWith('image/') || mime === 'application/pdf'
}

async function load() {
  if (!hasValidTarget.value) {
    items.value = []
    return
  }
  loading.value = true
  try {
    const res = await queryByTarget(props.objectType, props.objectId, {
      includeHidden: includeHidden.value,
    })
    if (!res.success) {
      message.error(friendlyError(res))
      items.value = []
      return
    }
    let list = res.data?.items || []
    // 分类筛选在前端做（后端 by-target 只支持 link_role 过滤）
    if (filterCategory.value) {
      list = list.filter(item => item.category === filterCategory.value)
    }
    items.value = list
  } catch (e) {
    message.error('附件列表加载失败', e)
    items.value = []
  } finally {
    loading.value = false
  }
}

function beforeUpload(file) {
  const limit = maxFileMb.value * 1024 * 1024
  if (file.size > limit) {
    message.error(`「${file.name}」超过 ${maxFileMb.value}MB 上限`)
    return false
  }
  if (!hasValidTarget.value) {
    message.error('请先保存单据后再上传附件')
    return false
  }
  return true
}

async function handleUpload(options) {
  uploadingCount.value += 1
  try {
    const res = await uploadAttachment({
      file: options.file,
      targetType: props.objectType,
      targetId: props.objectId,
      category: uploadCategory.value || 'other',
    })
    if (!res.success) {
      message.error(friendlyError(res))
      return
    }
    message.success(`「${options.file.name}」上传成功`)
    await load()
  } catch (e) {
    message.error('附件上传失败', e)
  } finally {
    uploadingCount.value = Math.max(0, uploadingCount.value - 1)
  }
}

async function handleDownload(row) {
  if (!row) return
  try {
    const res = await downloadAttachment(row, {
      targetType: props.objectType,
      targetId: props.objectId,
    })
    if (!res.success) message.error(friendlyError(res))
  } catch (e) {
    message.error('附件下载失败', e)
  }
}

async function handleUnlink(row) {
  if (!row?.link_id) return
  if (!(await message.confirm({ title: '解除挂接', content: `确定从当前对象移除「${row.file_name}」？（不会删除附件字节）` }))) {
    return
  }
  unlinkingId.value = row.link_id
  try {
    const res = await unlinkAttachment(row.link_id)
    if (!res.success) {
      message.error(friendlyError(res))
      return
    }
    message.success('已解除挂接')
    await load()
  } catch (e) {
    message.error('解除挂接失败', e)
  } finally {
    unlinkingId.value = null
  }
}

const preview = reactive({
  visible: false,
  loading: false,
  item: null,
  kind: '',
  url: '',
})

function releasePreviewUrl() {
  if (preview.url) window.URL.revokeObjectURL(preview.url)
  preview.url = ''
}

async function handlePreview(row) {
  if (!row) return
  const mime = row.mime_type || ''
  preview.item = row
  preview.kind = mime.startsWith('image/') ? 'image' : (mime === 'application/pdf' ? 'pdf' : '')
  preview.visible = true
  if (!preview.kind) return

  releasePreviewUrl()
  preview.loading = true
  try {
    const res = await fetchAttachmentBlob(row, {
      targetType: props.objectType,
      targetId: props.objectId,
      inline: true,
    })
    if (!res.success) {
      message.error(friendlyError(res))
      preview.visible = false
      return
    }
    preview.url = window.URL.createObjectURL(res.data)
  } catch (e) {
    message.error('附件预览失败', e)
    preview.visible = false
  } finally {
    preview.loading = false
  }
}

function closePreview() {
  releasePreviewUrl()
  preview.item = null
  preview.kind = ''
  preview.loading = false
}

async function loadCategories() {
  try {
    categories.value = await getAttachmentCategories()
  } catch (e) {
    // fail-closed：枚举不可用时不回退硬编码码值
    categories.value = []
  }
}
loadCategories()

watch(
  () => [props.objectType, props.objectId],
  () => { load() },
  { immediate: true }
)

onBeforeUnmount(releasePreviewUrl)

defineExpose({ load })
</script>

<style scoped>
.op-attachment-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.op-attachment-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.op-attachment-toolbar__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.op-attachment-count {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.op-attachment-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 4px;
}

.op-attachment-upload :deep(.el-upload) {
  width: 100%;
}

.op-attachment-upload :deep(.el-upload-dragger) {
  padding: 14px;
  border-style: dashed;
}

.op-attachment-upload__inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary, #909399);
}

.op-attachment-upload__text {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
}

.op-attachment-upload__text em {
  color: var(--el-color-primary, #409eff);
  font-style: normal;
}

.op-attachment-upload__hint {
  margin: 0;
  font-size: 12px;
}

.op-attachment-file {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.op-attachment-file__name {
  font-size: 13px;
  color: var(--el-text-color-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.op-attachment-file__name--link {
  padding: 0;
  border: none;
  background: none;
  text-align: left;
  cursor: pointer;
  color: var(--el-color-primary, #409eff);
}

.op-attachment-file__name--link:hover {
  text-decoration: underline;
}

.op-attachment-file__meta {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.op-attachment-actions {
  display: flex;
  align-items: center;
}

.op-attachment-preview {
  min-height: 240px;
}

.op-attachment-preview__image {
  display: block;
  max-width: 100%;
  max-height: 68vh;
  margin: 0 auto;
}

.op-attachment-preview__frame {
  width: 100%;
  height: 68vh;
  border: none;
}

.op-attachment-preview__fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 0;
  color: var(--el-text-color-secondary, #909399);
}
</style>