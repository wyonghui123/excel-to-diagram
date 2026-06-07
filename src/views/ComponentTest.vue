<template>
  <div class="component-test">
    <div class="page-header">
      <AppButton variant="secondary" size="sm" @click="goBack">
        ← 返回
      </AppButton>
      <h1 class="page-title">UI组件测试页面</h1>
    </div>

    <!-- 按钮组件测试 -->
    <section class="test-section">
      <h2 class="section-title">AppButton 按钮组件</h2>
      <div class="button-group">
        <h3>按钮类型</h3>
        <AppButton variant="primary">主要按钮</AppButton>
        <AppButton variant="secondary">次要按钮</AppButton>
        <AppButton variant="text">文字按钮</AppButton>
        <AppButton variant="danger">危险按钮</AppButton>
        <AppButton variant="success">成功按钮</AppButton>
        <AppButton variant="warning">警告按钮</AppButton>
      </div>

      <div class="button-group">
        <h3>按钮尺寸</h3>
        <AppButton size="xs">超小</AppButton>
        <AppButton size="sm">小</AppButton>
        <AppButton size="md">中</AppButton>
        <AppButton size="lg">大</AppButton>
        <AppButton size="xl">超大</AppButton>
      </div>

      <div class="button-group">
        <h3>按钮状态</h3>
        <AppButton loading>加载中</AppButton>
        <AppButton disabled>禁用</AppButton>
        <AppButton variant="primary" ghost>幽灵按钮</AppButton>
        <AppButton circle>+</AppButton>
      </div>

      <div class="button-group">
        <h3>块级按钮</h3>
        <AppButton block variant="primary">块级按钮</AppButton>
      </div>
    </section>

    <!-- 输入框组件测试 -->
    <section class="test-section">
      <h2 class="section-title">AppInput 输入框组件</h2>
      <div class="input-group">
        <h3>基础输入框</h3>
        <AppInput v-model="inputValue" placeholder="请输入内容" />
      </div>

      <div class="input-group">
        <h3>带标签</h3>
        <AppInput v-model="inputValue2" label="用户名" placeholder="请输入用户名" />
      </div>

      <div class="input-group">
        <h3>带错误信息</h3>
        <AppInput v-model="inputValue3" label="邮箱" :error="emailError" placeholder="请输入邮箱" />
      </div>

      <div class="input-group">
        <h3>可清空</h3>
        <AppInput v-model="inputValue4" clearable placeholder="可清空的输入框" />
      </div>

      <div class="input-group">
        <h3>不同尺寸</h3>
        <AppInput v-model="inputValue5" size="sm" placeholder="小尺寸" />
        <AppInput v-model="inputValue6" size="md" placeholder="中尺寸" />
        <AppInput v-model="inputValue7" size="lg" placeholder="大尺寸" />
      </div>
    </section>

    <!-- 卡片组件测试 -->
    <section class="test-section">
      <h2 class="section-title">AppCard 卡片组件</h2>
      <div class="card-grid">
        <AppCard title="基础卡片" subtitle="副标题描述">
          这是卡片的内容区域
        </AppCard>

        <AppCard title="可点击卡片" clickable hoverable @click="handleCardClick">
          点击此卡片会触发事件
        </AppCard>

        <AppCard title="带底部" shadow="md">
          卡片内容
          <template #footer>
            <AppButton size="sm" variant="primary">操作</AppButton>
          </template>
        </AppCard>

        <AppCard title="边框样式" border="primary">
          带主色边框的卡片
        </AppCard>
      </div>
    </section>

    <!-- 选择框组件测试 -->
    <section class="test-section">
      <h2 class="section-title">AppSelect 选择框组件</h2>
      <div class="select-group">
        <h3>基础选择框</h3>
        <AppSelect v-model="selectedValue" :options="options" placeholder="请选择" />
      </div>

      <div class="select-group">
        <h3>可搜索</h3>
        <AppSelect v-model="selectedValue2" :options="options" searchable placeholder="搜索并选择" />
      </div>

      <div class="select-group">
        <h3>多选</h3>
        <AppSelect v-model="selectedMultiple" :options="options" multiple placeholder="可多选" />
      </div>
    </section>

    <!-- 模态框组件测试 -->
    <section class="test-section">
      <h2 class="section-title">AppModal 模态框组件</h2>
      <div class="modal-group">
        <AppButton @click="showModal = true">打开基础模态框</AppButton>
        <AppButton variant="secondary" @click="showConfirmModal = true">打开确认模态框</AppButton>
      </div>

      <AppModal v-model="showModal" title="模态框标题">
        这是模态框的内容区域
      </AppModal>

      <AppModal
        v-model="showConfirmModal"
        title="确认操作"
        show-default-footer
        @confirm="handleConfirm"
        @cancel="handleCancel"
      >
        确定要执行此操作吗？
      </AppModal>
    </section>

    <!-- YonDesign颜色系统展示 -->
    <section class="test-section">
      <h2 class="section-title">YonDesign颜色系统</h2>
      <div class="token-showcase">
        <h3>Orange 橙色系 (主色)</h3>
        <div class="color-palette">
          <div class="color-item" style="background: var(--yonyou-orange-400)"><span>400</span></div>
          <div class="color-item" style="background: var(--yonyou-orange-500)"><span>500</span></div>
          <div class="color-item" style="background: var(--yonyou-orange-600)"><span>600 Primary</span></div>
          <div class="color-item" style="background: var(--yonyou-orange-700)"><span>700</span></div>
        </div>

        <h3>Amber 琥珀色</h3>
        <div class="color-palette">
          <div class="color-item" style="background: var(--yonyou-amber-400)"><span>400</span></div>
          <div class="color-item" style="background: var(--yonyou-amber-500)"><span>500 Secondary</span></div>
          <div class="color-item" style="background: var(--yonyou-amber-600)"><span>600</span></div>
        </div>

        <h3>Yellow 黄色</h3>
        <div class="color-palette">
          <div class="color-item" style="background: var(--yonyou-yellow-400)"><span>400</span></div>
          <div class="color-item" style="background: var(--yonyou-yellow-500)"><span>500 Accent</span></div>
          <div class="color-item" style="background: var(--yonyou-yellow-600)"><span>600</span></div>
        </div>

        <h3>Lime 青柠色 (信息)</h3>
        <div class="color-palette">
          <div class="color-item" style="background: var(--yonyou-lime-400)"><span>400</span></div>
          <div class="color-item" style="background: var(--yonyou-lime-500)"><span>500</span></div>
          <div class="color-item" style="background: var(--yonyou-lime-600)"><span>600 Info</span></div>
        </div>

        <h3>Green 绿色 (成功)</h3>
        <div class="color-palette">
          <div class="color-item" style="background: var(--yonyou-green-400)"><span>400</span></div>
          <div class="color-item" style="background: var(--yonyou-green-500)"><span>500 Success</span></div>
          <div class="color-item" style="background: var(--yonyou-green-600)"><span>600</span></div>
        </div>

        <h3>功能色映射</h3>
        <div class="color-palette">
          <div class="color-item" style="background: var(--color-primary)"><span>Primary</span></div>
          <div class="color-item" style="background: var(--color-secondary)"><span>Secondary</span></div>
          <div class="color-item" style="background: var(--color-success)"><span>Success</span></div>
          <div class="color-item" style="background: var(--color-warning)"><span>Warning</span></div>
          <div class="color-item" style="background: var(--color-error)"><span>Error</span></div>
          <div class="color-item" style="background: var(--color-info)"><span>Info</span></div>
        </div>

        <h3>中性色 (灰蓝色系)</h3>
        <div class="text-colors">
          <p class="text-primary">Primary Text - 主要文本 #1f2937</p>
          <p class="text-secondary">Secondary Text - 次要文本 #4b5563</p>
          <p class="text-tertiary">Tertiary Text - 第三级文本 #6b7280</p>
          <p class="text-disabled">Disabled Text - 禁用文本</p>
        </div>

        <h3>间距系统</h3>
        <div class="spacing-showcase">
          <div class="spacing-item p-xs">xs (4px)</div>
          <div class="spacing-item p-sm">sm (8px)</div>
          <div class="spacing-item p-md">md (16px)</div>
          <div class="spacing-item p-lg">lg (24px)</div>
          <div class="spacing-item p-xl">xl (32px)</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { AppButton, AppInput, AppCard, AppSelect, AppModal } from '@/components/common'

const router = useRouter()

const goBack = () => {
  router.push('/')
}

const inputValue = ref('')
const inputValue2 = ref('')
const inputValue3 = ref('')
const inputValue4 = ref('可清空的内容')
const inputValue5 = ref('')
const inputValue6 = ref('')
const inputValue7 = ref('')
const emailError = ref('请输入正确的邮箱格式')

// 选择框数据
const selectedValue = ref('')
const selectedValue2 = ref('')
const selectedMultiple = ref([])

const options = [
  { label: '选项1', value: '1' },
  { label: '选项2', value: '2' },
  { label: '选项3', value: '3' },
  { label: '选项4 (禁用)', value: '4', disabled: true },
  { label: '选项5', value: '5' }
]

// 模态框数据
const showModal = ref(false)
const showConfirmModal = ref(false)

const handleCardClick = () => {
  alert('卡片被点击了！')
}

const handleConfirm = () => {
  alert('确认操作')
  showConfirmModal.value = false
}

const handleCancel = () => {
  console.log('取消操作')
}
</script>

<style scoped>
.component-test {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-xl);
}

.page-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-xl);
}

.page-title {
  font-size: var(--font-size-xxxl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  flex: 1;
  text-align: center;
}

.test-section {
  margin-bottom: var(--spacing-xxxl);
  padding: var(--spacing-xl);
  background: var(--color-bg-container);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.section-title {
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border);
}

.button-group,
.input-group,
.select-group,
.modal-group {
  margin-bottom: var(--spacing-lg);
}

.button-group h3,
.input-group h3,
.select-group h3 {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
}

.button-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  align-items: center;
}

.input-group {
  max-width: 400px;
  margin-bottom: var(--spacing-md);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-lg);
}

.select-group {
  max-width: 300px;
  margin-bottom: var(--spacing-md);
}

.token-showcase h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin: var(--spacing-lg) 0 var(--spacing-sm);
}

.color-palette {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.color-item {
  width: 100px;
  height: 60px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-sm);
}

.text-colors p {
  margin: var(--spacing-xs) 0;
}

.spacing-showcase {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.spacing-item {
  background: var(--color-primary-bg);
  border: var(--border-width-thin) solid var(--color-primary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}
</style>
