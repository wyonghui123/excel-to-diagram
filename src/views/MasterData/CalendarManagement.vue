<template>
  <MultiObjectManagementPage
    ref="pageRef"
    :object-types="objectTypes"
    :options="pageOptions"
    @toolbar-action="handleToolbarAction"
  />
</template>

<script setup>
/**
 * CalendarManagement — 作业日历管理页（MOMP 配置注入）
 *
 * 形态：左树 = 日历树（基准日历 / 派生日历），右表 = 两个 tab
 *      （作业日历 / 日历例外日）。与位置管理、行政区划、业务伙伴页同构，
 *      本页不触碰 MOMP 本体。
 *
 * - objectTypes=['calendar','calendar_day']：
 *   calendar 是主数据主体；calendar_day 是它的 association 子对象
 *   （calendar_day.yaml: parent_object=calendar / hierarchy.parent_field=calendar_id）。
 *   子表原先有独立平级菜单 calendar_day-list（v103 下架），
 *   平级属「放错层」⇒ 收进本页第二 tab（同 party_relation 收进业务伙伴页）。
 *
 * - scopeTree.component=CalendarScopeTree：注入日历范围树（扁平 parent_calendar_id
 *   → 客户端组树），节点标「基准/派生」。
 *
 * - scopeAdapter：树 emit {calendarIds, effectiveCalendarIds} → scopeIds['calendar']
 *   写入键必须与 objectTypes 对齐（handleScopeChange 只遍历 objectTypes）。
 *
 * - filterStrategies（口径 B：聚合，含派生子孙）：
 *   calendar      → id__in effective（勾中基准日历 → 基准 + 其派生日历）
 *   calendar_day  → calendar_id__in effective（勾中基准日历 → 含派生厂区日历的例外日）
 *   未勾选 → 不过滤（后端全量台账）。
 *   注意不是"继承"语义：一期 day_mask_* 为覆盖、例外日按 calendar_id 独立归属，
 *   派生日历并不会自动继承父日历的例外日；这里只是把「所选日历集合」的记录
 *   聚合出来，列表的「日历」列负责说明归属。真正的继承计算留二期排程引擎。
 *
 * - disableVersionContext=true：主数据页无产品/版本上下文
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import CalendarScopeTree from '@/components/common/CalendarScopeTree/CalendarScopeTree.vue'

defineOptions({ name: 'CalendarManagement' })

const objectTypes = ['calendar', 'calendar_day']

const pageOptions = {
  defaultTab: 'calendar',
  tabs: {
    calendar: { label: '作业日历' },
    calendar_day: { label: '日历例外日' }
  },
  scopeTree: {
    component: CalendarScopeTree,
    props: {},
    events: {}
  },
  disableVersionContext: true,
  stateKey: 'calendarManagerState',
  menuCodeProvider: () => 'calendar-list',
  scopeAdapter: {
    handleScopeChange(scope, ctx) {
      const { scopeIds } = ctx
      const effective = scope.effectiveCalendarIds?.length
        ? scope.effectiveCalendarIds
        : (scope.calendarIds || [])
      const target = scopeIds['calendar']
      if (target) {
        target.selected = (scope.calendarIds || [])
        target.effective = effective
      }
    }
  },
  filterStrategies: {
    calendar(filters, scopeIds) {
      const ids = scopeIds?.['calendar']?.effective || []
      if (ids.length) return { ...filters, id__in: ids.join(',') }
      return filters
    },
    // 例外日 tab：左树勾选日历集合 → calendar_id__in（含派生子孙，口径 B）
    calendar_day(filters, scopeIds) {
      const ids = scopeIds?.['calendar']?.effective || []
      if (ids.length) return { ...filters, calendar_id__in: ids.join(',') }
      return filters
    }
  }
}

const pageRef = ref(null)

function handleToolbarAction(action) {
  const actionType = typeof action === 'string' ? action : action?.type
  if (actionType === 'refresh') {
    pageRef.value?.refresh?.()
  }
}
</script>
