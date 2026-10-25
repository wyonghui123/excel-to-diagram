<template>
  <div class="op-association-section">
    <template v-if="isManyToMany">
      <MetaListPage
        :ref="setMetaListRef"
        :object-type="targetType"
        :display-mode="'embedded'"
        :columns-override="manyToManyColumns"
        :options="manyToManyOptions"
        :row-actions-override="manyToManyRowActions"
        :toolbar-actions-override="manyToManyToolbarActions"
        :batch-actions-override="manyToManyBatchActions"
        :enable-detail="false"
        :enable-auto-crud="false"
        :row-key="'id'"
        @action="handleEmbeddedAction($event, props.section)"
        @toolbar-action="handleToolbarAction($event, props.section)"
        @batch-action="handleBatchAction($event, props.section)"
      />
    </template>

    <div v-else-if="isMergedRelationships" class="op-merged-relations">
      <el-table :data="mergedRelationsData" v-loading="mergedRelationsLoading" size="small" max-height="400">
        <el-table-column label="关系类型" width="120">
          <template #default="{ row }">
            <span>{{ getRelationTypeName(row.relation_type, row.relation_type_name) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="方向" width="80">
          <template #default="{ row }">
            <span>{{ getRelationDirectionName(row.relation_direction, row.relation_direction_name) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="source_bo_name" label="源对象" min-width="180" />
        <el-table-column prop="target_bo_name" label="目标对象" min-width="180" />
        <el-table-column prop="relation_desc" label="关系描述" min-width="150" />
      </el-table>
      <div class="op-empty-state" v-if="!mergedRelationsLoading && mergedRelationsData.length === 0">
        <AppIcon name="link" size="lg" />
        <p>暂无关系数据</p>
      </div>
    </div>

    <div v-else-if="isPartyRelations" class="op-merged-relations">
      <!-- [入口 2026-10-20] 引导式新建：业务伙伴档案侧预绑对手侧，组织档案侧预绑我方侧 -->
      <div v-if="partyRelationToolbarActions.length" class="op-party-relations-toolbar">
        <AppButton
          v-for="a in partyRelationToolbarActions"
          :key="a.key"
          :variant="a.variant || 'primary'"
          @click="handlePartyRelationToolbar(a)"
        >{{ a.label }}</AppButton>
      </div>

      <el-table :data="partyRelationsData" v-loading="partyRelationsLoading" size="small" max-height="400">
        <!-- [列口径 2026-10-21] 本分区挂在「业务伙伴」档案上 ⇒ 当前对象恒为对手侧，
             「对方」列恒显示我方组织，词义与业务词「对方企业」打架且与归属法人撞脸。
             改为绝对口径：首列直接叫「我方组织」（= party1 侧的组织身份），
             删掉零信息量的「方向」列（本分区恒为对手侧）。组织名下补 org 编码副标题，
             与「归属法人」区分（同名时也能看出是两条不同 org 记录）。
             我方组织与归属法人相邻（与 party_relation.yaml 的「我方信息」分组同序）。
             [组织侧 2026-10-21] 分区改挂组织档案时本对象即我方组织，首列换成「业务伙伴」，
             否则该列整列重复显示当前对象、零信息量。 -->
        <el-table-column v-if="!isOrgPartyRelations" label="我方组织" min-width="200">
          <template #default="{ row }">
            <div class="op-relation-cell">
              <!-- [2026-10-22] 改用 FkLinkField：与列表/详情一致可跳；
                   落点口径由后端 {field}_link_object_type / {field}_link_id 下发。 -->
              <FkLinkField
                :value="row.party1_id"
                :display-value="row._selfOrgName || row.party1_id_display || ''"
                target-object-type="party_internal"
                :link-object-type="row.party1_id_link_object_type"
                :link-id="row.party1_id_link_id"
                target-object-label="我方组织"
              />
              <span v-if="row._selfOrgCode" class="op-relation-cell__code">{{ row._selfOrgCode }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-else label="业务伙伴" min-width="200">
          <template #default="{ row }">
            <FkLinkField
              :value="row.party2_id"
              :display-value="row.party2_id_display || ''"
              target-object-type="party_archive"
              :link-object-type="row.party2_id_link_object_type"
              :link-id="row.party2_id_link_id"
              target-object-label="业务伙伴"
            />
          </template>
        </el-table-column>
        <el-table-column label="归属法人" min-width="200">
          <template #default="{ row }">
            <div class="op-relation-cell">
              <FkLinkField
                :value="row.le_org_id"
                :display-value="row.le_org_id_display || ''"
                target-object-type="org_legal_entity"
                :link-object-type="row.le_org_id_link_object_type"
                :link-id="row.le_org_id_link_id"
                target-object-label="归属法人"
              />
              <span v-if="row._leOrgCode" class="op-relation-cell__code">{{ row._leOrgCode }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <span>{{ ROLE_LABEL[row.role] || row.role || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务伙伴组" min-width="150">
          <template #default="{ row }">
            <FkLinkField
              :value="row.group_id"
              :display-value="row.group_id_display || ''"
              target-object-type="party_group"
              :link-object-type="row.group_id_link_object_type"
              :link-id="row.group_id_link_id"
              target-object-label="业务伙伴组"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span>{{ STATUS_LABEL[row.status] || row.status || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="op-empty-state" v-if="!partyRelationsLoading && partyRelationsData.length === 0">
        <AppIcon name="link" size="lg" />
        <p>暂无往来关系</p>
      </div>

      <!-- [2026-10-20] 显式传标题：本入口为预绑对手侧必传 entityData，MetaDialog 的
           新增/编辑判态（entityData 是否为空）会因此误判为编辑，故不依赖该判态。 -->
      <MetaDialog
        :visible="partyRelationFormVisible"
        :meta="partyRelationMeta"
        :entity-data="partyRelationEntityData"
        :title="partyRelationDialogTitle"
        :saving="partyRelationSaving"
        :field-dependencies="partyRelationFieldDependencies"
        :z-index="9990"
        @close="handlePartyRelationDialogClose"
        @save="handlePartyRelationSave"
        @update:visible="partyRelationFormVisible = $event"
      />
    </div>

    <template v-else-if="isRelationAccounts">
      <!-- [B 2026-10-23] 1:1 明细面：字段组表单，不是表格。
           依据：customer_accounts.relation_id / vendor_accounts.relation_id 均为
           UNIQUE NOT NULL ⇒ 一条关系最多一条档案；表格形态（含 pageSize）是错的。
           形态对齐 SAP S/4 的角色页签字段组 / D365 CustTable 表单页签。 -->
      <template v-if="isSingletonAccount">
        <div class="op-party-relations-toolbar">
          <template v-if="singletonEditing">
            <AppButton variant="default" @click="cancelSingletonEdit">取消</AppButton>
            <AppButton variant="primary" :loading="singletonSaving" @click="saveSingleton">
              {{ singletonRecord ? '保存' : '创建' }}
            </AppButton>
          </template>
          <template v-else-if="singletonRecord">
            <AppButton variant="default" @click="startSingletonEdit">编辑</AppButton>
          </template>
          <template v-else>
            <AppButton
              v-for="a in relationAccountToolbarActions"
              :key="a.key"
              :variant="a.variant || 'primary'"
              @click="startSingletonCreate"
            >{{ a.label }}</AppButton>
          </template>
        </div>

        <div v-loading="relationAccountsLoading">
          <MetaForm
            v-if="singletonEditing"
            :fields="relationAccountFields"
            v-model="singletonDraft"
            layout="vertical"
          />
          <!-- [窄屏 2026-10-23] 写死 :column="2" 在手机抽屉里会把 label/value 挤成两半、
               右侧留大片空白 ⇒ 窄屏降为单列。口径与 DetailSection 的 ds-grid 一致。 -->
          <el-descriptions
            v-else-if="singletonRecord"
            :column="isMobile ? 1 : 2"
            border
            size="small"
          >
            <el-descriptions-item
              v-for="f in relationAccountFields"
              :key="f.key"
              :label="f.label"
            >
              <!-- [风格 2026-10-23] 枚举字段渲染 el-tag（取 enum_values.color），
                   与「状态 启用」的绿色 tag 同风格；此前走纯文本，同一抽屉内两种风格。 -->
              <el-tag
                v-if="singletonIsEnumFilled(f, singletonRecord)"
                :type="singletonTagType(f, singletonRecord)"
                size="small"
              >{{ singletonDisplayValue(f, singletonRecord) }}</el-tag>
              <span v-else :class="{ 'op-singleton-value--empty': singletonIsEmpty(f, singletonRecord) }">
                {{ singletonDisplayValue(f, singletonRecord) }}
              </span>
            </el-descriptions-item>
          </el-descriptions>
          <div v-else class="op-empty-state">
            <AppIcon name="link" size="lg" />
            <p>{{ emptyRelationAccountText }}</p>
          </div>
        </div>
      </template>

      <!-- 集合面兜底（cardinality != one）：保留原表格，避免影响既有配置 -->
      <template v-else>
        <div class="op-party-relations-toolbar">
          <AppButton
            v-for="a in relationAccountToolbarActions"
            :key="a.key"
            :variant="a.variant || 'primary'"
            @click="handleRelationAccountToolbar"
          >{{ a.label }}</AppButton>
        </div>

        <el-table :data="relationAccountsData" v-loading="relationAccountsLoading" size="small" max-height="400">
          <el-table-column prop="name" label="档案名称" min-width="200" />
          <el-table-column prop="description" label="说明" min-width="200" />
          <el-table-column prop="created_at" label="创建时间" width="170" />
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="handleRelationAccountRowAction(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="op-empty-state" v-if="!relationAccountsLoading && relationAccountsData.length === 0">
          <AppIcon name="link" size="lg" />
          <p>{{ emptyRelationAccountText }}</p>
        </div>
      </template>

      <MetaDialog
        :visible="relationAccountFormVisible"
        :meta="relationAccountMeta"
        :entity-data="relationAccountEntityData"
        :title="relationAccountDialogTitle"
        :saving="relationAccountSaving"
        :z-index="9990"
        @close="handleRelationAccountDialogClose"
        @save="handleRelationAccountSave"
        @update:visible="relationAccountFormVisible = $event"
      />
    </template>

    <template v-else-if="isAnnotation">
      <MetaListPage
        v-if="objectType && hasRealObjectId"
        :ref="setMetaListRef"
        object-type="annotation"
        :display-mode="'embedded'"
        :columns-override="props.section.columns || null"
        :options="annotationOptions"
        :toolbar-actions-override="annotationToolbarActions"
        :enable-auto-crud="false"
        :enable-detail="false"
        :row-actions-override="annotationRowActions"
        @action="handleAnnotationAction($event, props.section)"
        @toolbar-action="handleToolbarAction($event, props.section)"
      />
      <MetaDialog
        :visible="annotationFormVisible"
        :meta="annotationMeta"
        :entity-data="annotationEntityData"
        :saving="annotationSaving"
        :z-index="9990"
        @close="handleAnnotationDialogClose"
        @save="handleAnnotationSave"
        @update:visible="annotationFormVisible = $event"
      />
    </template>

    <MetaListPage
      v-else-if="targetType && objectType && objectId"
      :ref="setMetaListRef"
      :object-type="targetType || section.association"
      :options="associationOptions"
      :initial-filters="associationFilters"
      :enable-detail="section.enableDetail !== undefined ? section.enableDetail : true"
      :enable-auto-crud="section.enableAutoCrud !== undefined ? section.enableAutoCrud : !section.readonly"
      :row-mutability="section.rowMutability || (section.readonly ? 'locked' : 'fullEditable')"
      :extra-row-actions="section.extraRowActions || null"
      :external-editing="editing ? true : null"
      :exclude-column-keys="excludedColumnKeys"
      @request-edit="$emit('request-edit')"
      @action="handleEmbeddedAction($event, props.section)"
    />

    <div v-else-if="!objectId || objectId === 'new'" class="op-empty-state">
      <AppIcon name="link" size="lg" />
      <p>保存对象后可以查看关联数据</p>
    </div>
    <div v-else class="op-empty-state">
      <AppIcon name="link" size="lg" />
      <p>缺少关联配置信息，无法加载关联数据。</p>
      <p>调试信息: assocType={{ section.assocType }}, assocName={{ section.assocName }}, objectType={{ objectType }}, objectId={{ objectId }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, shallowRef, inject, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import MetaListPage from '../MetaListPage/MetaListPage.vue'
import AppIcon from '../AppIcon/AppIcon.vue'
import AppButton from '../AppButton/AppButton.vue'
import MetaDialog from '../MetaDialog.vue'
import MetaForm from '../MetaForm.vue'
import FkLinkField from '../FkLinkField/FkLinkField.vue'
import boService from '@/services/boService'
import metaService from '@/services/metaService'
import { useAuthStore } from '@/stores/authStore'
import { CATEGORY_CONFIG } from '@/composables/useMermaid/annotation/annotationConfig'
import * as annotationService from '@/services/annotationService'
import EnumService from '@/services/enumService'
import { useCrudMessage } from '@/composables/useCrudMessage'
import { useBreakpoints } from '@/composables/useBreakpoints'

const props = defineProps({
  section: {
    type: Object,
    required: true
  },
  objectType: {
    type: String,
    default: null
  },
  objectId: {
    type: [String, Number],
    default: null
  },
  editing: {
    type: Boolean,
    default: false
  },
  uiConfig: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['request-edit', 'open-assign', 'refresh', 'embedded-action'])

const message = useCrudMessage()
const authStore = useAuthStore()
const { isMobile } = useBreakpoints()

// [FIX 2026-06-29] 前端兜底 enum 映射
//   之前后端 relationship 序列化时没 join enum_values 表, relation_type_name 总是 null
//   详情页直接显示 code (GENERATES/PULL 等) 不友好
//   这里维护一份前端 enum 映射兜底, 即使后端不返 _name 也能显示中文
//   未来后端真返回 _name 时, computed 会优先用后端的
// [FIX 2026-06-29 v2] relation_direction 没有 enum 表
//   业务约定: PUSH=推送 / PULL=拉取, 直接映射 (这两个是常量)
const RELATION_TYPE_NAME_MAP = Object.freeze({
  GENERATES: '生成',
  UPDATES: '更新',
  TRIGGERS: '触发',
  REFERENCES: '引用'
})
const RELATION_DIRECTION_NAME_MAP = Object.freeze({
  PUSH: '推送',
  PULL: '拉取'
})

function getRelationTypeName(typeCode, typeName) {
  // [FIX V015e 2026-07-10] 兜底清洗历史脏 enum code (legacy_null / null 字符串等)
  //   原 BUG: 数据库早期导入数据时, 后端对空 relation_type 写了字符串 'legacy_null' 占位.
  //     详情页 getRelationTypeName 走 RELATION_TYPE_NAME_MAP[typeCode] 找不到,
  //     fallback 到 typeCode || '' → 直接显示 'legacy_null'.
  //   修复: 把 sentinel 值映射为 '-' (与空值/列表页保持一致).
  const isLegacyNull = (v) => {
    if (v == null) return false
    const s = String(v).trim().toLowerCase()
    return s === 'null' || s === 'undefined' || s === 'none' || s === 'n/a' || s === 'na' ||
           /^legacy[_\s-]*null$/.test(s)
  }
  if (isLegacyNull(typeCode) || isLegacyNull(typeName)) return '-'
  return typeName || RELATION_TYPE_NAME_MAP[typeCode] || typeCode || ''
}
function getRelationDirectionName(dirCode, dirName) {
  // 同 V015e: 兜底清洗 legacy_null
  const isLegacyNull = (v) => {
    if (v == null) return false
    const s = String(v).trim().toLowerCase()
    return s === 'null' || s === 'undefined' || s === 'none' || s === 'n/a' || s === 'na' ||
           /^legacy[_\s-]*null$/.test(s)
  }
  if (isLegacyNull(dirCode) || isLegacyNull(dirName)) return '-'
  return dirName || RELATION_DIRECTION_NAME_MAP[dirCode] || dirCode || '-'
}

const hasRealObjectId = computed(() => {
  const id = props.objectId
  if (id == null || id === '' || id === 'new') return false
  const numId = Number(id)
  return !isNaN(numId) && numId > 0
})

function getAssociationConfig(assocName) {
  if (props.uiConfig?.associations) {
    const assocConfig = props.uiConfig.associations.find(a => a.name === assocName)
    if (assocConfig) {
      return assocConfig
    }
  }
  if (props.section.assocName === assocName || props.section.association === assocName) {
    return { target_type: props.section.association, ...props.section }
  }
  return {}
}

function getAssociationTargetType(assocName) {
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === assocName)
  if (assocConfig?.target_type) return assocConfig.target_type
  if (props.section.assocName === assocName && props.section.association) return props.section.association
  const sectionConfig = getAssociationConfig(assocName)
  return sectionConfig?.target_type || ''
}

const isManyToMany = computed(() => {
  return (props.section.assocType === 'many_to_many' || props.section.assocType === 'reverse_many_to_many')
    && props.section.assocName
    && getAssociationTargetType(props.section.assocName)
    && props.objectType
    && props.objectId
})

const isMergedRelationships = computed(() => {
  return props.section.customFetcher === 'merged_bo_relationships'
})

// [关系分区 2026-10-17] 往来关系（party_relation）分区：两侧合并口径 C。
//   不能走平台关联端点 —— associationFilters 把过滤列写死为 `{父对象类型}_id`，
//   父对象是 party 时会得 `party_id`，而 party_relation 的列是 party1_id/party2_id。
//   故在此做两次查询（party1_id = 本 id / party2_id = 本 id）后按 id 合并去重。
//   同一行不会两侧都命中（party1_id 恒为我方侧、party2_id 为对手侧），去重只为防御。
// [列口径 2026-10-21] 表内不再展示「本对象站哪一侧」：本分区只挂在业务伙伴档案上，
//   那一侧恒为对手侧 ⇒ 该列零信息量。首列改为「我方组织」（party1 侧的组织身份）。
const isPartyRelations = computed(() => {
  return props.section.customFetcher === 'party_relations'
    || props.section.customFetcher === 'org_party_relations'
})

// [组织侧分区 2026-10-21] 分区挂在「组织」档案上，本对象恒为我方侧。
//   列集与业务伙伴侧相反：业务伙伴侧首列是「我方组织」（本对象是对手侧，那一列才有意义），
//   组织侧本对象就是我方组织 ⇒ 首列换成「业务伙伴」（对手侧），不再重复显示自己。
const isOrgPartyRelations = computed(() => {
  return props.section.customFetcher === 'org_party_relations'
})

const ROLE_LABEL = Object.freeze({ customer: '客户', vendor: '供应商' })
const STATUS_LABEL = Object.freeze({ active: '启用', inactive: '停用' })

const partyRelationsData = ref([])
const partyRelationsLoading = ref(false)
let _partyRelationsVersion = 0

function normalizeQueryItems(res) {
  const items = res?.data?.items
    || (Array.isArray(res?.data) ? res.data : (Array.isArray(res) ? res : []))
  return Array.isArray(items) ? items : []
}

// [组织侧 2026-10-21] orgs.id → parties.id：org 的内部表示是 1:1（镜像服务按 org 逐个建），
//   取首行即可；无内部表示的普通组织返回 null。
async function resolveOrgInternalPartyId(orgId) {
  const res = await boService.query('party_internal', { org_id: orgId, page_size: 10 })
  return normalizeQueryItems(res).find(it => it?.id != null)?.id ?? null
}

async function loadPartyRelations() {
  if (!hasRealObjectId.value) {
    partyRelationsData.value = []
    partyRelationsLoading.value = false
    return
  }
  const version = ++_partyRelationsVersion
  partyRelationsLoading.value = true
  try {
    const selfId = props.objectId
    // page_size 200: 单个业务伙伴的关系数量级远小于此（与桥接查询同口径的防御性上限）
    let r1, r2
    if (isOrgPartyRelations.value) {
      // [组织侧 2026-10-21] 本对象是 orgs.id，而 party_relations.party1_id 存的是 parties.id
      //   ⇒ 先经 party_internal（org → 其内部表示）换出 party id，再按我方侧单查。
      //   org → party 内部表示是 1:1（org_party_mirror_service 按 org 逐个建），故取首行即可。
      //   组织恒为我方侧（对外主体不会出现在 party1 侧），故不做两侧合并。
      const selfPartyId = await resolveOrgInternalPartyId(selfId)
      r1 = selfPartyId != null
        ? await boService.query('party_relation', { party1_id: selfPartyId, page_size: 200 })
        : { data: [] }
      r2 = { data: [] }
    } else {
      [r1, r2] = await Promise.all([
        boService.query('party_relation', { party1_id: selfId, page_size: 200 }),
        boService.query('party_relation', { party2_id: selfId, page_size: 200 })
      ])
    }
    if (version !== _partyRelationsVersion) return
    const byId = new Map()
    for (const it of normalizeQueryItems(r1)) {
      if (it?.id == null || byId.has(it.id)) continue
      byId.set(it.id, { ...it })
    }
    for (const it of normalizeQueryItems(r2)) {
      if (it?.id == null || byId.has(it.id)) continue
      byId.set(it.id, { ...it })
    }
    const rows = [...byId.values()]
    await fillPartyRelationOrgCodes(rows)
    if (version !== _partyRelationsVersion) return
    partyRelationsData.value = rows
  } catch (e) {
    if (version !== _partyRelationsVersion) return
    console.error('[AssociationSection] loadPartyRelations 失败:', e)
    partyRelationsData.value = []
  } finally {
    if (version === _partyRelationsVersion) {
      partyRelationsLoading.value = false
    }
  }
}

// [列口径 2026-10-21] 补 org 编码副标题。
//   「我方组织」= party1 侧：party1 是我方组织的内部表示（party_internal 面，source='org'），
//     该面带 org_id ⇒ 可经它取到 org 行的 name / code。
//   「归属法人」= le_org_id：本身就是 org.id ⇒ 直接取 org 行。
//   两次批量查询（id__in），不逐行打接口。
async function fillPartyRelationOrgCodes(rows) {
  if (!rows.length) return
  const party1Ids = [...new Set(rows.map(r => r.party1_id).filter(v => v != null))]
  const leOrgIds = [...new Set(rows.map(r => r.le_org_id).filter(v => v != null))]

  // party1 → org_id（party_internal 面；非 org 来源的存量行查不到 ⇒ 无编码）
  const partyOrgMap = {}
  if (party1Ids.length) {
    const res = await boService.query('party_internal', {
      id__in: party1Ids.join(','), page_size: 200
    })
    for (const it of normalizeQueryItems(res)) {
      if (it?.id != null && it?.org_id != null) partyOrgMap[it.id] = it.org_id
    }
  }

  const orgIds = [...new Set([...leOrgIds, ...Object.values(partyOrgMap)])]
  const orgMap = {}
  if (orgIds.length) {
    const res = await boService.query('org', { id__in: orgIds.join(','), page_size: 200 })
    for (const it of normalizeQueryItems(res)) {
      if (it?.id != null) orgMap[it.id] = it
    }
  }

  for (const row of rows) {
    const selfOrgId = partyOrgMap[row.party1_id]
    const selfOrg = selfOrgId != null ? orgMap[selfOrgId] : null
    row._selfOrgName = (selfOrg && selfOrg.name) || row.party1_id_display || row.party1_id || ''
    row._selfOrgCode = (selfOrg && selfOrg.code) || ''
    const leOrg = row.le_org_id != null ? orgMap[row.le_org_id] : null
    row._leOrgCode = (leOrg && leOrg.code) || ''
  }
}

// ===== [默认带出 2026-10-21] 我方组织 → 归属法人 =====
//   口径: 归属法人默认取「我方组织自身（若它是法人）否则沿组织树上溯的第一个法人」。
//   依据: 组织是单亲树（orgs.parent_id 单值），一个组织沿链上溯的最近法人唯一 ⇒ 默认值可确定。
//   仍可改: le_org_id 是独立字段（同一我方组织可在多个法人下各有一条关系，
//   见 party_relation.yaml 头注 D5 四元组唯一键），故只做默认带出、不做强制。
//   落点: 建关系弹窗的 fieldDependencies（改我方组织即重算），
//     MetaForm 的 setFieldValue 只在字段已存在时写入 ⇒ 不会凭空造字段。
const ORG_TREE_MAX_DEPTH = 20

// 查一个 org 自身及其所有祖先 org（自近及远），返回 [{id, name, code, parent_id}]
async function loadOrgAncestorChain(orgId) {
  const chain = []
  const seen = new Set()
  let curId = orgId
  let depth = 0
  while (curId != null && !seen.has(curId) && depth < ORG_TREE_MAX_DEPTH) {
    seen.add(curId)
    const res = await boService.query('org', { id: curId, page_size: 1 })
    const row = normalizeQueryItems(res)[0]
    if (!row || row.id == null) break
    chain.push(row)
    curId = row.parent_id
    depth += 1
  }
  return chain
}

// 我方组织的 party1_id（party 引用）→ 其 org 行的 id；非 org 来源的存量行返回 null
async function resolveSelfOrgId(party1Id) {
  if (party1Id == null || party1Id === '') return null
  const res = await boService.query('party_internal', { id: party1Id, page_size: 1 })
  const row = normalizeQueryItems(res)[0]
  return row?.org_id ?? null
}

// 默认归属法人 = 自身或最近法人祖先；查不到返回 null（不猜，交由人工选）
async function resolveDefaultLegalEntityOrgId(party1Id) {
  const orgId = await resolveSelfOrgId(party1Id)
  if (orgId == null) return null
  const chain = await loadOrgAncestorChain(orgId)
  const chainIds = chain.map(r => r.id).filter(id => id != null)
  if (!chainIds.length) return null
  // [2026-10-21 收窄] 只回查祖先链上的 id，不拉法人面全表：
  //   法人数量随组织增长，全量拉（原 page_size 200）在法人超过上限时会静默漏判。
  const leRes = await boService.query('org_legal_entity', {
    id__in: chainIds.join(','), page_size: chainIds.length
  })
  const legalEntityIds = new Set(normalizeQueryItems(leRes).map(r => r.id))
  const hit = chain.find(r => legalEntityIds.has(r.id))
  return hit ? hit.id : null
}

// 归属法人是否落在我方组织的祖先链上（含自身）。
//   合法例外: 共享服务 / 集中采购等组织，业务上确实会在多个法人下分别立关系
//   ⇒ 判为 false 时只提示确认，不阻断。
async function isLegalEntityAncestor(party1Id, leOrgId) {
  if (party1Id == null || leOrgId == null) return true
  const orgId = await resolveSelfOrgId(party1Id)
  if (orgId == null) return true
  const chain = await loadOrgAncestorChain(orgId)
  return chain.some(r => String(r.id) === String(leOrgId))
}

// ===== [入口 2026-10-20] 往来关系「引导式新建」=====
//   背景: 本分区此前是纯只读表（零按钮），用户实测报障「业务伙伴这边新增关系」。
//     F3 §7 登记为延期项，前置「镜像防护先落地」已完成 ⇒ 只缺入口形态。
//   方案: 工具条入口 + 自建 MetaDialog（annotation 分支同款先例），
//     字段元取自 party_relation 的真实 ui-config（避免手写字段与 schema 漂移）。
//   口径: 当前业务伙伴固定为「对手侧」(party2_id, 只读预填)，我方侧由用户选（D1）；
//     归属法人在本入口必填（D2，让镜像守卫 assert_no_mirror 真实生效）。
const partyRelationFormVisible = ref(false)
const partyRelationEntityData = ref(null)
const partyRelationSaving = ref(false)
const partyRelationFieldDefs = ref(null)

// 工具条：从 section.actions 取 create，并按 action.permission 做显隐（与平台 action 级权限同源）
const partyRelationToolbarActions = computed(() => {
  if (!hasRealObjectId.value) return []
  const create = (props.section.actions || []).find(
    a => (typeof a === 'string' ? a : (a.key || a.id)) === 'create'
  )
  if (!create) return []
  const perm = typeof create === 'string' ? null : create.permission
  if (perm && !authStore.hasPermission(perm)) return []
  return [{
    key: 'create',
    label: (typeof create === 'string' ? null : create.label) || '新建往来关系',
    variant: (typeof create === 'string' ? null : create.variant) || 'primary'
  }]
})

// 取 party_relation 的真实字段元并归一为 MetaForm 形态
//   （id→key / name→label / enum_values→options / value_help 原形直传）。
//   参考实现：DetailPage.computedFieldDefs。
async function loadPartyRelationFieldDefs() {
  if (partyRelationFieldDefs.value) return partyRelationFieldDefs.value
  const res = await metaService.getUIConfig('party_relation')
  if (!res?.success) throw new Error(res?.message || '加载往来关系字段失败')
  const formSections = res.data?.ui_view_config?.form?.sections || []
  const order = []
  for (const s of formSections) {
    if (Array.isArray(s.fields) && s.fields.length) { order.push(...s.fields); continue }
    for (const c of (s.columns || [])) {
      if (Array.isArray(c.fields)) order.push(...c.fields)
    }
  }
  const all = res.data?.fields || []
  const byId = new Map(all.map(f => [f.id, f]))
  const picked = (order.length ? order : all.map(f => f.id))
    .map(id => byId.get(id))
    .filter(Boolean)
  partyRelationFieldDefs.value = picked.map(f => {
    const hasOptions = !!(f.enum_values?.length || f.options?.length)
    return {
      key: f.id,
      label: f.name || f.id,
      type: (f.type === 'integer' || f.value_help)
        ? 'value_help'
        : (hasOptions ? 'select' : (f.type || 'text')),
      required: f.required === true,
      defaultValue: f.default ?? undefined,
      options: hasOptions
        ? (f.enum_values || f.options).map(o => ({ label: o.label, value: o.value }))
        : undefined,
      value_help: f.value_help || undefined,
      placeholder: f.ui?.placeholder || ''
    }
  })
  return partyRelationFieldDefs.value
}

// [2026-10-20] 本入口永远是新建，故显式给标题：
//   MetaDialog 的新增/编辑判态依据 entityData 是否为空，而本入口为预绑对手侧
//   必传 entityData，会被误判为编辑态（标题显示"编辑…"）。故不依赖该判态。
const partyRelationDialogTitle = computed(() => '新建往来关系')

const partyRelationMeta = computed(() => ({
  label: '往来关系',
  fields: (partyRelationFieldDefs.value || []).map(f => ({
    ...f,
    // D1: 预绑侧 = 当前打开的对象，预填 + 只读。
    //   业务伙伴档案：本对象为对手侧（party2_id）；
    //   组织档案：本对象经 party_internal 换出的内部表示为我方侧（party1_id）。
    ...(!isOrgPartyRelations.value && f.key === 'party2_id'
      ? { disabled: true, required: true } : {}),
    ...(isOrgPartyRelations.value && f.key === 'party1_id'
      ? { disabled: true, required: true } : {}),
    // D2: 本入口归属法人必填（UI 层收窄；schema 仍可空）
    ...(f.key === 'le_org_id' ? { required: true } : {})
  }))
}))

// [2026-10-21] 选我方组织后自动带出默认归属法人（用户仍可改）。
//   MetaForm 的 fieldDependencies 语义：key 为被监听字段，onChange(newVal, allValues, ctx)
//   在该字段值变化时触发一次；ctx.setFieldValue 写入目标字段。
// [竞态守卫 2026-10-21] onChange 是异步的（要查 party_internal + 组织祖先链）：
//   ① 期间用户又改了我方组织 ⇒ 旧请求的结果不得覆盖新选择（序号守卫）；
//   ② 期间用户手选了归属法人 ⇒ 不得覆盖用户的选择（手动值守卫）。
let _leOrgResolveSeq = 0
let _lastAutoLeOrgId = null

const partyRelationFieldDependencies = {
  party1_id: {
    onChange: async (newPartyId, _allValues, ctx) => {
      const seq = ++_leOrgResolveSeq
      try {
        const leOrgId = await resolveDefaultLegalEntityOrgId(newPartyId)
        if (seq !== _leOrgResolveSeq) return
        // 查不到祖先法人时保持原值不动（不猜、不清空用户已填的内容）
        if (leOrgId == null) return
        const currentLe = ctx.getFormData?.()?.le_org_id
        const hasManualValue = currentLe != null && currentLe !== ''
          && String(currentLe) !== String(_lastAutoLeOrgId ?? '')
        if (hasManualValue) return
        _lastAutoLeOrgId = leOrgId
        ctx.setFieldValue('le_org_id', leOrgId)
      } catch (e) {
        console.warn('[AssociationSection] 默认归属法人带出失败:', e)
      }
    }
  }
}

async function handlePartyRelationToolbar(action) {
  if (action?.key !== 'create') return
  try {
    await loadPartyRelationFieldDefs()
  } catch (e) {
    message.error(e?.message || '加载往来关系字段失败')
    return
  }
  // 每次开新弹窗重置联动状态：上次的"自动带出值"不得影响本次的手动选择判定
  _leOrgResolveSeq = 0
  _lastAutoLeOrgId = null

  let entityData
  if (isOrgPartyRelations.value) {
    // 组织档案侧：本对象是我方侧，但 party1_id 存的是 parties.id ⇒ 先换内部表示。
    //   无内部表示 = 该组织不是我方主体（无 BU/LE 职能），不能作为关系一方。
    let selfPartyId = null
    try {
      selfPartyId = await resolveOrgInternalPartyId(props.objectId)
    } catch (e) {
      message.error(e?.message || '查询组织内部表示失败')
      return
    }
    if (selfPartyId == null) {
      message.error('该组织不是我方主体（无内部业务伙伴记录），无法新建往来关系')
      return
    }
    entityData = { party1_id: selfPartyId }
    // 归属法人默认取自身或最近法人祖先（与档案侧选完我方组织后的联动同口径）
    try {
      const leOrgId = await resolveDefaultLegalEntityOrgId(selfPartyId)
      if (leOrgId != null) {
        entityData.le_org_id = leOrgId
        _lastAutoLeOrgId = leOrgId
      }
    } catch (e) {
      console.warn('[AssociationSection] 默认归属法人带出失败:', e)
    }
  } else {
    entityData = { party2_id: props.objectId } // 预绑对手侧（D1）
  }

  partyRelationEntityData.value = entityData
  partyRelationFormVisible.value = true
}

function handlePartyRelationDialogClose() {
  partyRelationFormVisible.value = false
  partyRelationEntityData.value = null
}

async function handlePartyRelationSave(formData) {
  partyRelationSaving.value = true
  try {
    // 共享组件 MetaDialog 在创建态会把每个未设值字段初始化为 ''，
    // 直接提交会让后端把可空 FK（如 group_id）当 '' 解析成无效引用。
    // 在本入口出口剔除空值，避免改动共享组件。
    const payload = {}
    for (const [k, v] of Object.entries(formData || {})) {
      if (v === '' || v === null || v === undefined) continue
      payload[k] = v
    }
    // [2026-10-20] 防自反关系：两侧都不得指向同一个 party。
    //   后端镜像守卫对 A==B 是盲的（镜像 SQL 查反向行，A==B 时查不到），
    //   故前端在出口拦截给出可读提示；后端守卫另补判定兜底（第三 tab 同样漏）。
    //   [组织侧 2026-10-21] 比较两侧 party id，不依赖当前对象 id（组织侧当前对象是 orgs.id，
    //   而我方侧存的是 parties.id，两者不可直接比较）。
    if (payload.party1_id != null && payload.party2_id != null
      && String(payload.party1_id) === String(payload.party2_id)) {
      message.error('我方组织不能与对手侧相同')
      return
    }
    // [2026-10-21] 归属法人不在我方组织祖先链上 → 软提示（可确认继续，不阻断）。
    //   合法例外确实存在（共享服务 / 集中采购：同一组织在多个法人下各立关系），
    //   故不能硬拦；此处只把「非常规选择」显式化，避免脏数据无声入库。
    if (payload.le_org_id != null && !(await isLegalEntityAncestor(payload.party1_id, payload.le_org_id))) {
      const confirmed = await ElMessageBox.confirm(
        '所选归属法人不在该我方组织的上级链上。共享服务、集中采购等场景确实会在多个法人下分别建立关系，' +
        '若本次确属此情形请继续；否则建议改选该组织自身或其上级法人。',
        '归属法人与组织层级不一致',
        { confirmButtonText: '仍然保存', cancelButtonText: '返回修改', type: 'warning' }
      ).then(() => true).catch(() => false)
      if (!confirmed) return
    }
    const res = await boService.create('party_relation', payload)
    if (!res?.success) throw new Error(res?.message || '创建失败')
    message.success('往来关系已创建')
    partyRelationFormVisible.value = false
    partyRelationEntityData.value = null
    // 本分区不能用 refresh()（其只调 metaListRef，对该分支是空操作）
    await loadPartyRelations()
    emit('refresh')
  } catch (e) {
    // 镜像守卫的 MirrorRowError 可读消息在此展示
    message.error(e?.message || '创建往来关系失败')
  } finally {
    partyRelationSaving.value = false
  }
}

const isAnnotation = computed(() => {
  return props.section.type === 'annotation'
})

// [档案分区 2026-10-22] 客户档案 / 供应商档案分区（挂在 party_relation 详情页）。
//   走自定义取数器而非平台关联端点：associationFilters 把过滤列写死
//   `{父对象类型}_id`，本分区父对象是 party_relation ⇒ 会得 `party_relation_id`，
//   而两个档案表的列名是 `relation_id`。列名不匹配时后端忽略该条件返回全量
//   ⇒ 一个关系详情页会列出所有人的档案。故此处按 relation_id 精确查。
const isRelationAccounts = computed(() => {
  return props.section.customFetcher === 'relation_accounts'
})

// [B 2026-10-23] 1:1 明细面判定：档案与关系是 UNIQUE 关系，一条关系最多一条档案。
//   为 true 时渲染内联字段组表单（新建/编辑/保存），不渲染集合表格。
const isSingletonAccount = computed(() => {
  return isRelationAccounts.value && props.section.cardinality === 'one'
})

// 分区所属对象：section.association 由 DetailPage 下发（customer_account / vendor_account）
const relationAccountObjectType = computed(() => {
  return props.section.association || props.section.assocName || ''
})

const isCustomerAccountSection = computed(() => {
  return relationAccountObjectType.value === 'customer_account'
})

// 空态文案：两个分区恒渲染（不按父行 role 隐藏 —— role 可编辑，隐藏会让改完 role
// 后该侧分区立刻消失、用户失去入口），故不匹配的一侧只会显示「暂无档案」。
const emptyRelationAccountText = computed(() => '暂无档案')

const relationAccountsData = ref([])
const relationAccountsLoading = ref(false)
let _relationAccountsVersion = 0

async function loadRelationAccounts() {
  if (!hasRealObjectId.value || !relationAccountObjectType.value) {
    relationAccountsData.value = []
    relationAccountsLoading.value = false
    return
  }
  const version = ++_relationAccountsVersion
  relationAccountsLoading.value = true
  try {
    const res = await boService.query(relationAccountObjectType.value, {
      relation_id: props.objectId,
      page_size: 50
    })
    if (version !== _relationAccountsVersion) return
    relationAccountsData.value = normalizeQueryItems(res)
    // 1:1 明细面的只读展示也依赖字段元（label / options），故与取数一并加载
    if (isSingletonAccount.value) {
      loadRelationAccountFieldDefs().catch(e => {
        console.error('[AssociationSection] 档案字段加载失败:', e)
      })
    }
  } catch (e) {
    if (version !== _relationAccountsVersion) return
    console.error('[AssociationSection] loadRelationAccounts 失败:', e)
    relationAccountsData.value = []
  } finally {
    if (version === _relationAccountsVersion) {
      relationAccountsLoading.value = false
    }
  }
}

const relationAccountFormVisible = ref(false)
const relationAccountEntityData = ref(null)
const relationAccountSaving = ref(false)
const relationAccountFieldDefs = ref(null)

// 工具条：从 section.actions 取 create，按 action.permission 做显隐（与往来关系分区同源）
const relationAccountToolbarActions = computed(() => {
  if (!hasRealObjectId.value) return []
  const create = (props.section.actions || []).find(
    a => (typeof a === 'string' ? a : (a.key || a.id)) === 'create'
  )
  if (!create) return []
  const perm = typeof create === 'string' ? null : create.permission
  if (perm && !authStore.hasPermission(perm)) return []
  return [{
    key: 'create',
    label: (typeof create === 'string' ? null : create.label) || '新建档案',
    variant: (typeof create === 'string' ? null : create.variant) || 'primary'
  }]
})

// 字段元取自档案对象真实 ui-config（避免手写字段与 schema 漂移，同往来关系分区口径）。
// relation_id 不进表单：本分区恒 1:1，创建时必填且由入口预绑，用户无从选择。
async function loadRelationAccountFieldDefs() {
  if (relationAccountFieldDefs.value) return relationAccountFieldDefs.value
  const objectType = relationAccountObjectType.value
  const res = await metaService.getUIConfig(objectType)
  if (!res?.success) throw new Error(res?.message || '加载档案字段失败')
  const formSections = res.data?.ui_view_config?.form?.sections || []
  const order = []
  for (const s of formSections) {
    if (Array.isArray(s.fields) && s.fields.length) { order.push(...s.fields); continue }
    for (const c of (s.columns || [])) {
      if (Array.isArray(c.fields)) order.push(...c.fields)
    }
  }
  const all = res.data?.fields || []
  const byId = new Map(all.map(f => [f.id, f]))
  relationAccountFieldDefs.value = (order.length ? order : all.map(f => f.id))
    .map(id => byId.get(id))
    .filter(f => f && f.id !== 'relation_id')
    .map(f => {
      const hasOptions = !!(f.enum_values?.length || f.options?.length)
      return {
        key: f.id,
        label: f.name || f.id,
        // MetaForm 只认 text / number / textarea / select 等控件类型，不认 schema 的
        // 'string'（落不到任何分支 ⇒ 只渲染 label、没有输入框）⇒ 归一化为 text。
        type: hasOptions ? 'select' : (f.type === 'string' ? 'text' : (f.type || 'text')),
        required: f.required === true,
        defaultValue: f.default ?? undefined,
        options: hasOptions
          ? (f.enum_values || f.options).map(o => ({
              label: o.label,
              value: o.value,
              // [风格 2026-10-23] 只读态要拿 color 渲 el-tag，与 DetailSection.getEnumTagType 同源
              color: o.color || o.tagType || o.tag_type || ''
            }))
          : undefined,
        placeholder: f.ui?.placeholder || ''
      }
    })
  return relationAccountFieldDefs.value
}

const relationAccountDialogTitle = computed(() => {
  const base = isCustomerAccountSection.value ? '客户档案' : '供应商档案'
  return relationAccountEntityData.value?.id ? `编辑${base}` : `新建${base}`
})

const relationAccountMeta = computed(() => ({
  label: isCustomerAccountSection.value ? '客户档案' : '供应商档案',
  fields: relationAccountFieldDefs.value || []
}))

async function handleRelationAccountToolbar() {
  try {
    await loadRelationAccountFieldDefs()
  } catch (e) {
    message.error(e?.message || '加载档案字段失败')
    return
  }
  // 预绑 relation_id：本分区是 1:1 明细面，父 id 由所在分区唯一决定
  relationAccountEntityData.value = { relation_id: props.objectId }
  relationAccountFormVisible.value = true
}

async function handleRelationAccountRowAction(row) {
  try {
    await loadRelationAccountFieldDefs()
  } catch (e) {
    message.error(e?.message || '加载档案字段失败')
    return
  }
  relationAccountEntityData.value = { ...row }
  relationAccountFormVisible.value = true
}

function handleRelationAccountDialogClose() {
  relationAccountFormVisible.value = false
  relationAccountEntityData.value = null
}

async function handleRelationAccountSave(formData) {
  const objectType = relationAccountObjectType.value
  relationAccountSaving.value = true
  try {
    // MetaDialog 创建态会把每个未设值字段初始化为 ''，直接提交会让后端把
    // 可空字段当 '' 解析（同往来关系分区 L703-710 的处理）。
    const payload = {}
    for (const [k, v] of Object.entries(formData || {})) {
      if (v === '' || v === null || v === undefined) continue
      payload[k] = v
    }
    // 不信任前端传来的 relation_id：恒取当前所在关系，杜绝跨关系改挂
    payload.relation_id = props.objectId
    const isEdit = !!relationAccountEntityData.value?.id
    const res = isEdit
      ? await boService.update(objectType, relationAccountEntityData.value.id, payload)
      : await boService.create(objectType, payload)
    if (!res?.success) throw new Error(res?.message || '保存失败')
    message.success(isEdit ? '档案已更新' : '档案已创建')
    relationAccountFormVisible.value = false
    relationAccountEntityData.value = null
    await loadRelationAccounts()
    emit('refresh')
  } catch (e) {
    message.error(e?.message || '保存档案失败')
  } finally {
    relationAccountSaving.value = false
  }
}

// ── [B 2026-10-23] 1:1 明细面：内联字段组表单 ─────────────────────────
// 形态依据：DB 层 relation_id UNIQUE ⇒ 0..1 条；表格无法表达 1:1 语义。
const relationAccountFields = computed(() => relationAccountFieldDefs.value || [])

const singletonRecord = computed(() => relationAccountsData.value[0] || null)
const singletonEditing = ref(false)
const singletonDraft = ref({})
const singletonSaving = ref(false)

// 按字段元取显示值：有 options（枚举/字典）则映射为中文标签，否则原值
function singletonDisplayValue(field, row) {
  const raw = row?.[field?.key]
  if (raw === undefined || raw === null || raw === '') return '—'
  const opt = (field.options || []).find(o => String(o.value) === String(raw))
  return opt ? opt.label : String(raw)
}

// 空值判定：供只读态套用灰色占位样式（与 DetailSection.ds-value--empty 同口径）
function singletonIsEmpty(field, row) {
  const raw = row?.[field?.key]
  return raw === undefined || raw === null || raw === ''
}

// 枚举字段且有值 ⇒ 渲 el-tag（否则渲纯文本，与详情其他分区的枚举呈现不一致）
function singletonIsEnumFilled(field, row) {
  return !!field.options?.length && !singletonIsEmpty(field, row)
}

// tag 配色取自 enum_values.color；未配色的枚举回退 info，避免默认灰底与普通文本混淆
function singletonTagType(field, row) {
  const raw = row?.[field?.key]
  const opt = (field.options || []).find(o => String(o.value) === String(raw))
  return opt?.color || 'info'
}

async function startSingletonCreate() {
  try {
    await loadRelationAccountFieldDefs()
  } catch (e) {
    message.error(e?.message || '加载档案字段失败')
    return
  }
  singletonDraft.value = {}
  singletonEditing.value = true
}

async function startSingletonEdit() {
  try {
    await loadRelationAccountFieldDefs()
  } catch (e) {
    message.error(e?.message || '加载档案字段失败')
    return
  }
  const src = singletonRecord.value || {}
  const draft = {}
  for (const f of relationAccountFields.value) draft[f.key] = src[f.key] ?? ''
  singletonDraft.value = draft
  singletonEditing.value = true
}

function cancelSingletonEdit() {
  singletonEditing.value = false
  singletonDraft.value = {}
}

async function saveSingleton() {
  const objectType = relationAccountObjectType.value
  if (!objectType) return
  singletonSaving.value = true
  try {
    // 空串/空值不提交，避免后端把可空字段解析成 ''（与抽屉保存同口径）
    const payload = {}
    for (const [k, v] of Object.entries(singletonDraft.value || {})) {
      if (v === '' || v === null || v === undefined) continue
      payload[k] = v
    }
    // 不信任前端：relation_id 恒取当前所在关系，杜绝跨关系改挂
    payload.relation_id = props.objectId
    const current = singletonRecord.value
    const res = current
      ? await boService.update(objectType, current.id, payload)
      : await boService.create(objectType, payload)
    if (!res?.success) throw new Error(res?.message || '保存失败')
    message.success(current ? '档案已更新' : '档案已创建')
    singletonEditing.value = false
    singletonDraft.value = {}
    await loadRelationAccounts()
    emit('refresh')
  } catch (e) {
    message.error(e?.message || '保存档案失败')
  } finally {
    singletonSaving.value = false
  }
}

// 父对象切换时退出编辑态，防止把 A 关系的草稿写到 B 关系
watch(() => props.objectId, () => {
  singletonEditing.value = false
  singletonDraft.value = {}
})

const targetType = computed(() => {
  return getAssociationTargetType(props.section.assocName)
})

// [FIX 2026-06-14] 父对象下的子对象 children 列表: 隐藏冗余的"所属产品"列
// 场景: product → version 列表, version 自带 product_name (所属产品) 列
//       但当前上下文父对象已经是 product, 该列是冗余信息
// 仅在 product → version 上下文生效, 不影响其他父子关系
const excludedColumnKeys = computed(() => {
  const parentType = props.objectType
  const childType = targetType.value || props.section.association
  if (parentType === 'product' && childType === 'version') {
    return ['product_id', 'product_name', 'product_code']
  }
  return []
})

const registerMetaListRef = inject('registerMetaListRef', null)
const metaListRef = shallowRef(null)

function setMetaListRef(el) {
  if (el && metaListRef.value !== el) {
    metaListRef.value = el
    registerMetaListRef?.(props.section.key, el)
  }
}

const manyToManyColumns = computed(() => {
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === props.section.assocName)
  return assocConfig?.display?.columns || null
})

const manyToManyFetcher = computed(() => {
  return (params) => {
    // [GUARD 2026-06-14] objectId='new' 是创建态, 后端 /bo/<type>/<id>/associations/<name> 期望 int id
    // 不拦截会触发 GET /api/v2/bo/role/new/associations/assigned_groups -> 404
    if (!hasRealObjectId.value) {
      return Promise.resolve({ success: true, data: { items: [], total: 0, counts: {} } })
    }
    return boService.queryAssociations(props.objectType, props.objectId, props.section.assocName, params)
  }
})

const manyToManyOptions = computed(() => ({
  autoLoad: true,
  pageSize: props.section.pageSize || 10,
  fetcher: manyToManyFetcher.value
}))

const manyToManyRowActions = computed(() => {
  // 如果有批量删除操作，则不显示单行删除按钮
  if (props.section.readonly) return []
  if (manyToManyBatchActions.value.length > 0) return []
  
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === props.section.assocName)
  const unassignAction = assocConfig?.actions?.unassign
  return [{
    key: 'remove',
    label: unassignAction?.label || '移除',
    type: 'danger',
    variant: 'danger'
  }]
})

const manyToManyToolbarActions = computed(() => {
  const section = props.section
  const actions = section?.actions || []
  
  console.debug('[AssociationSection] manyToManyToolbarActions:', {
    assocName: section?.assocName,
    assocType: section?.assocType,
    readonly: section?.readonly,
    actions,
    isManyToMany: isManyToMany.value
  })
  
  if (section?.readonly) {
    console.debug('[AssociationSection] Skipping toolbar actions: readonly=true')
    return []
  }
  
  const hasAssignAction = actions.some(a => {
    if (typeof a === 'string') return a === 'assign'
    return a.key === 'assign' || a.id === 'assign'
  })
  
  if (!hasAssignAction) {
    console.debug('[AssociationSection] Skipping toolbar actions: no assign action')
    return []
  }
  
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === section?.assocName)
  const result = [{
    key: 'assign',
    label: assocConfig?.actions?.assign?.label || '+ 添加',
    variant: 'primary'
  }]
  
  console.debug('[AssociationSection] Returning toolbar actions:', result)
  return result
})

const manyToManyBatchActions = computed(() => {
  const section = props.section
  if (section?.readonly) return []
  
  const actions = section?.actions || []
  const hasUnassignAction = actions.some(a => {
    if (typeof a === 'string') return a === 'unassign'
    return a.key === 'unassign' || a.id === 'unassign'
  })
  
  if (!hasUnassignAction) return []
  
  const assocConfig = props.uiConfig?.associations?.find(a => a.name === section?.assocName)
  return [{
    key: 'batch_unassign',
    label: assocConfig?.actions?.unassign?.label || '批量移除',
    variant: 'danger',
    confirm: assocConfig?.actions?.unassign?.confirm_message || '确定要移除选中的项目吗？'
  }]
})

const associationFilters = computed(() => {
  const section = props.section
  if (section.assocType === 'many_to_many' || section.assocType === 'reverse_many_to_many') {
    return {}
  }
  const parentKey = `${props.objectType}_id`
  return { [parentKey]: props.objectId }
})

const associationFetcher = computed(() => {
  return (params) => {
    // [GUARD 2026-06-14] 同 manyToManyFetcher, 创建态 objectId='new' 拦截
    if (!hasRealObjectId.value) {
      return Promise.resolve({ success: true, data: { items: [], total: 0, counts: {} } })
    }
    return boService.queryAssociations(props.objectType, props.objectId, props.section.assocName, params)
  }
})

const associationOptions = computed(() => {
  const baseOptions = {
    autoLoad: true,
    pageSize: props.section.pageSize || 10
  }
  
  if (props.section.inlineEdit) {
    baseOptions.inlineEdit = props.section.inlineEdit
  }
  
  if (props.section.assocType === 'parent_child') {
    return baseOptions
  }
  return {
    ...baseOptions,
    fetcher: associationFetcher.value
  }
})

const annotationFetcher = computed(() => {
  return async (queryParams) => {
    const { page = 1, pageSize = props.section.pageSize || 10 } = queryParams || {}
    try {
      const result = await annotationService.queryAnnotations({
        target_type: props.objectType,
        target_id: props.objectId,
        page,
        page_size: pageSize
      })
      if (result.success) {
        const data = result.data?.data || result.data || []
        const total = result.data?.total ?? result.total ?? data.length
        return { success: true, data: { items: Array.isArray(data) ? data : [], total } }
      }
      return { success: false, message: result.message || '获取备注失败', data: { items: [], total: 0 } }
    } catch (e) {
      console.error('[AssociationSection] Failed to fetch annotations:', e)
      return { success: false, message: e.message, data: { items: [], total: 0 } }
    }
  }
})

const annotationOptions = computed(() => ({
  autoLoad: true,
  pageSize: props.section.pageSize || 10,
  fetcher: annotationFetcher.value
}))

const annotationRowActions = computed(() => [
  { key: 'annotation-edit', label: '编辑', type: 'primary' },
  { key: 'annotation-delete', label: '删除', type: 'danger' }
])

const annotationToolbarActions = computed(() => {
  if (!hasRealObjectId.value) return []
  const hasCreateAction = props.section.actions?.some(a => (typeof a === 'string' ? a : a.key) === 'create')
  if (!hasCreateAction) return []
  return [{
    key: 'create',
    label: '添加备注',
    variant: 'primary'
  }]
})

function handleToolbarAction(action, section) {
  console.debug('[AssociationSection] handleToolbarAction:', { action, section })
  if (action.key === 'assign') {
    console.debug('[AssociationSection] Emitting open-assign with section:', section)
    emit('open-assign', section)
  } else if (action.key === 'create') {
    handleAnnotationCreate(section)
  }
}

async function handleBatchAction(event, section) {
  const { action, selectedIds, selectedRows } = event
  console.debug('[AssociationSection] handleBatchAction:', { action, selectedIds, selectedRows, section })
  
  if (action.key === 'batch_unassign') {
    const confirmMsg = action.confirm || '确定要移除选中的项目吗？'
    try {
      await ElMessageBox.confirm(confirmMsg, '批量移除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch {
      return
    }
    
    const results = []
    const errors = []

    // [FIX 2026-06-08] 用后端 /batch_unassign 替代 N 次单条 unassign 循环
    // 原因：循环里第一条成功后,后端可能因 stale association_record_id 返回 404;
    //      且 N 次 HTTP 请求慢、不原子。后端 bo_api.py:585 已提供 batch_unassign 端点。
    // 重要：表格 row.id 是 **target_id (role.id)**，不是 through-table 行 id (group_roles.id)。
    //      之前 v1 unassign 循环误把 role.id 当 association_record_id 传给后端,所以后端查 group_roles 找不到。
    //      后端 /batch_unassign 接受 { target_ids, target_type } 直接按 role.id 删除,无需 SQL 反查。
    const assocConfig = getAssociationConfig(section.assocName)
    const targetType = assocConfig?.target_type
    const targetIds = selectedRows.map(r => r.id).filter(id => id != null)
    if (targetIds.length === 0) {
      message.warning('没有可移除的记录')
      return
    }

    try {
      const result = await boService.batchUnassignAssociationsV2(
        props.objectType,
        props.objectId,
        section.assocName,
        {
          target_ids: targetIds,
          target_type: targetType
        }
      )
      if (result && (result.success || result === true)) {
        results.push(...targetIds)
      } else {
        // 后端 batch_unassign 的 data.results 数组里每项含 success/target_id;
        // 失败项的 target_id 即本次请求里的 target_id 之一
        const resultsArr = result?.data?.results
        const failedIds = (Array.isArray(resultsArr) ? resultsArr : [])
          .filter(r => !r.success)
          .map(r => r.target_id)
        const failedSet = new Set(failedIds)
        const successIds = targetIds.filter(id => !failedSet.has(id))
        results.push(...successIds)
        targetIds.filter(id => failedSet.has(id)).forEach(id => {
          errors.push({ id, message: result?.message || '移除失败' })
        })
      }
    } catch (e) {
      targetIds.forEach(id => errors.push({ id, message: e.message }))
    }
    
    if (errors.length === 0) {
      message.success(`已移除 ${results.length} 项`)
    } else if (results.length > 0) {
      message.warning(`成功移除 ${results.length} 项，失败 ${errors.length} 项`)
    } else {
      message.error('移除失败')
    }

    boService._clearCache(props.objectType)
    await refresh()
    // [FIX 2026-06-08] 批量删除成功后清空 el-table 勾选状态。
    // 原因: refresh() 重新拉数据,但 el-table 内部的 selectionChange 状态没动,
    //      totalSelectedCount 仍然 > 0 → 工具栏 "已选择 N 项 / 清除选择 / 批量删除"
    //      持续显示,即便底层数据已删。clearAllSelection 由 MetaListPage
    //      defineExpose 暴露(L1480),走 tableRef.clearSelection() 把勾选清掉。
    if (results.length > 0 && metaListRef.value?.clearAllSelection) {
      metaListRef.value.clearAllSelection()
    }
    emit('refresh')
  }
}

const mergedRelationsData = ref([])
const mergedRelationsLoading = ref(false)
let _mergedLoadVersion = 0

async function loadMergedRelationships() {
  if (!props.objectId) return
  // [GUARD 2026-06-14] 创建态 objectId='new' 拦截, 避免 source_bo_id='new' 触发后端异常
  if (!hasRealObjectId.value) {
    mergedRelationsData.value = []
    mergedRelationsLoading.value = false
    return
  }
  const version = ++_mergedLoadVersion
  mergedRelationsLoading.value = true
  try {
    const [r1, r2] = await Promise.all([
      boService.query('relationship', { page_size: 9999, source_bo_id: props.objectId }),
      boService.query('relationship', { page_size: 9999, target_bo_id: props.objectId })
    ])
    if (version !== _mergedLoadVersion) return
    const seen = new Set()
    const merged = []
    for (const r of [r1, r2]) {
      const items = r?.success ? (r.data?.items || (Array.isArray(r.data) ? r.data : [])) : []
      for (const it of items) {
        if (!seen.has(it.id)) { seen.add(it.id); merged.push(it) }
      }
    }
    mergedRelationsData.value = merged
  } catch (e) {
    console.error('[AssociationSection] loadMergedRelationships:', e)
  } finally {
    if (version === _mergedLoadVersion) {
      mergedRelationsLoading.value = false
    }
  }
}

async function handleAnnotationAction(event, section) {
  const { action, row } = event
  const actionKey = action?.key || action
  try {
    if (actionKey === 'annotation-edit') {
      handleAnnotationEdit(row, section)
    } else if (actionKey === 'annotation-delete') {
      await handleAnnotationDelete(row, section)
    }
  } catch (e) {
    console.error('[AssociationSection] Annotation action failed:', e)
    message.error(e?.message || '关联操作失败', e)
  }
}

const defaultCategories = [
  { code: 'important', name: '重要' },
  { code: 'warning', name: '警告' },
  { code: 'info', name: '信息' },
  { code: 'tip', name: '提示' }
]

const annotationCategories = ref([...defaultCategories])
const annotationFormVisible = ref(false)
const annotationEditingId = ref(null)
const annotationEntityData = ref(null)
const annotationSaving = ref(false)

const annotationMeta = computed(() => ({
  label: '备注',
  fields: [
    {
      key: 'category',
      label: '分类',
      type: 'select',
      required: true,
      defaultValue: annotationCategories.value.length > 0 ? annotationCategories.value[0].code : '',
      options: annotationCategories.value.map(c => ({ label: c.name, value: c.code }))
    },
    {
      key: 'content',
      label: '内容',
      type: 'textarea',
      required: true,
      placeholder: '请输入备注内容...'
    }
  ]
}))

let categoriesLoaded = false

async function loadAnnotationCategories() {
  console.log('[AssociationSection] loadAnnotationCategories START')
  // [FIX 2026-06-29] 始终调用 API, 不依赖缓存
  //   之前: categoriesLoaded 模块级共享, 第一次失败后即使再打开也不会重试
  //   弹窗可能保持默认 4 个 (defaultCategories), 即使数据库有 6 个
  // [FIX-2 2026-06-29 v2] EnumService._extractValuesArray 递归找数组 (兼容双层包装)
  try {
    const items = await EnumService.loadOptions('annotation_category', {
      useHighSpeedEndpoint: false,
      cache: false,
      throwError: false
    })
    if (items && items.length > 0) {
      annotationCategories.value = items.map(item => {
        const config = CATEGORY_CONFIG[item.value]
        return {
          code: item.value,
          name: config ? config.label : item.label
        }
      })
      categoriesLoaded = true
    }
  } catch {
    // 失败时保持默认 4 个 (annotationCategories.value 初始化时已是 defaultCategories)
    categoriesLoaded = false
  }
}

async function handleAnnotationCreate(section) {
  await loadAnnotationCategories()
  annotationEditingId.value = null
  annotationEntityData.value = null
  annotationFormVisible.value = true
}

async function handleAnnotationEdit(row, section) {
  await loadAnnotationCategories()
  annotationEditingId.value = row.id
  annotationEntityData.value = {
    category: row.category || '',
    content: row.content || ''
  }
  annotationFormVisible.value = true
}

function handleAnnotationDialogClose() {
  annotationFormVisible.value = false
  annotationEditingId.value = null
  annotationEntityData.value = null
}

async function handleAnnotationSave(formData) {
  annotationSaving.value = true
  try {
    let result
    if (annotationEditingId.value) {
      result = await annotationService.updateAnnotation(annotationEditingId.value, {
        category: formData.category,
        content: formData.content
      })
    } else {
      result = await annotationService.createAnnotation({
        target_type: props.objectType,
        target_id: props.objectId,
        category: formData.category,
        content: formData.content
      })
    }
    if (!result.success) throw new Error(result.message)
    message.success(annotationEditingId.value ? '备注已更新' : '备注已添加')
    annotationFormVisible.value = false
    refresh()
    emit('refresh')
  } catch (e) {
    const backendMsg = e?.message || ''
    if (backendMsg && backendMsg !== 'undefined') {
      message.error(backendMsg)
    } else {
      message.saveFailed('备注')
    }
  } finally {
    annotationSaving.value = false
  }
}

async function handleAnnotationDelete(row, section) {
  const result = await annotationService.deleteAnnotation(row.id)
  if (result.success) {
    message.success('备注已删除')
    refresh()
  } else {
    const backendMsg = result?.message || ''
    if (backendMsg && backendMsg !== 'undefined') {
      message.error(backendMsg)
    } else {
      message.error('删除备注失败')
    }
  }
}

async function handleEmbeddedAction({ action, row }, section) {
  emit('embedded-action', { action, row }, section)
  if (action?.key === 'remove' && row?.id) {
    try {
      const assocConfig = getAssociationConfig(section.assocName)
      const result = await boService.unassignAssociationV2(
        props.objectType,
        props.objectId,
        section.assocName,
        { association_record_id: row.id }
      )
      if (result && (result.success || result === true)) {
        message.success('已移除')
        boService._clearCache(props.objectType)
      } else {
        message.error('移除失败', result)
      }
    } catch (e) {
      console.error('[AssociationSection] unassign failed:', e)
      message.error('移除失败', e)
    }
    await refresh()
    emit('refresh')
  }
}

onMounted(() => {
  loadAnnotationCategories()
})

watch(() => props.objectId, (newVal, oldVal) => {
  if (newVal === oldVal) return
  if (isMergedRelationships.value) {
    loadMergedRelationships()
  } else if (isPartyRelations.value) {
    loadPartyRelations()
  } else if (isRelationAccounts.value) {
    loadRelationAccounts()
  }
}, { immediate: true })

function refresh() {
  if (isPartyRelations.value) { loadPartyRelations(); return }
  if (isRelationAccounts.value) { loadRelationAccounts(); return }
  if (isMergedRelationships.value) { loadMergedRelationships(); return }
  metaListRef.value?.refresh?.()
}

defineExpose({ refresh, loadMergedRelationships, loadPartyRelations, loadRelationAccounts })
</script>

<style scoped>
.op-association-section {
  padding: var(--spacing-sm) 0;
  min-height: 200px;
}

.op-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  color: var(--color-text-secondary);
  text-align: center;
}

.op-merged-relations {
  padding: var(--spacing-sm) 0;
}

.op-party-relations-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

/* [列口径 2026-10-21] 组织名 + org 编码副标题：两列都是组织名时靠编码区分 */
.op-relation-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.op-relation-cell__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.op-relation-cell__code {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

/* [窄屏 2026-10-23] 只读态空值占位灰字，与 DetailSection.ds-value--empty 同口径 */
.op-singleton-value--empty {
  color: var(--color-text-placeholder);
}
</style>
