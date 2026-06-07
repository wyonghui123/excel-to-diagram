<template>
  <div class="theme-preview">
    <h1>Element Plus + YonDesign 主题验证</h1>
    
    <section class="preview-section">
      <h2>主色 (Primary - YonDesign Orange)</h2>
      <div class="color-swatches">
        <div class="swatch" style="background: var(--el-color-primary)">
          <span>Primary</span>
          <small>#ea580c</small>
        </div>
        <div class="swatch" style="background: var(--el-color-primary-light-3)">
          <span>Light-3</span>
        </div>
        <div class="swatch" style="background: var(--el-color-primary-light-5)">
          <span>Light-5</span>
        </div>
        <div class="swatch" style="background: var(--el-color-primary-light-7)">
          <span>Light-7</span>
        </div>
        <div class="swatch" style="background: var(--el-color-primary-dark-2)">
          <span>Dark-2</span>
        </div>
      </div>
    </section>

    <section class="preview-section">
      <h2>功能色</h2>
      <div class="color-swatches">
        <div class="swatch" style="background: var(--el-color-success)">
          <span>Success</span>
        </div>
        <div class="swatch" style="background: var(--el-color-warning)">
          <span>Warning</span>
        </div>
        <div class="swatch" style="background: var(--el-color-danger)">
          <span>Danger</span>
        </div>
        <div class="swatch" style="background: var(--el-color-info)">
          <span>Info</span>
        </div>
      </div>
    </section>

    <section class="preview-section">
      <h2>按钮组件</h2>
      <div class="component-row">
        <el-button>默认按钮</el-button>
        <el-button type="primary">主要按钮</el-button>
        <el-button type="success">成功按钮</el-button>
        <el-button type="warning">警告按钮</el-button>
        <el-button type="danger">危险按钮</el-button>
        <el-button type="info">信息按钮</el-button>
      </div>
      <div class="component-row">
        <el-button plain>朴素按钮</el-button>
        <el-button type="primary" plain>主要按钮</el-button>
        <el-button type="success" plain>成功按钮</el-button>
        <el-button type="warning" plain>警告按钮</el-button>
        <el-button type="danger" plain>危险按钮</el-button>
      </div>
      <div class="component-row">
        <el-button round>圆角按钮</el-button>
        <el-button type="primary" round>主要按钮</el-button>
        <el-button type="success" round>成功按钮</el-button>
      </div>
      <div class="component-row">
        <el-button size="small">小型按钮</el-button>
        <el-button size="default">默认按钮</el-button>
        <el-button size="large">大型按钮</el-button>
      </div>
    </section>

    <section class="preview-section">
      <h2>输入框组件</h2>
      <div class="component-row">
        <el-input v-model="inputValue" placeholder="请输入内容" style="width: 200px" />
        <el-input v-model="inputValue" placeholder="禁用状态" disabled style="width: 200px" />
        <el-input v-model="inputValue" placeholder="可清空" clearable style="width: 200px" />
      </div>
      <div class="component-row">
        <el-input v-model="inputValue" size="small" placeholder="小型" style="width: 150px" />
        <el-input v-model="inputValue" size="default" placeholder="默认" style="width: 150px" />
        <el-input v-model="inputValue" size="large" placeholder="大型" style="width: 150px" />
      </div>
    </section>

    <section class="preview-section">
      <h2>选择器组件</h2>
      <div class="component-row">
        <el-select v-model="selectValue" placeholder="请选择" style="width: 200px">
          <el-option label="选项一" value="1" />
          <el-option label="选项二" value="2" />
          <el-option label="选项三" value="3" />
        </el-select>
        <el-select v-model="selectValue" placeholder="禁用状态" disabled style="width: 200px">
          <el-option label="选项一" value="1" />
        </el-select>
        <el-select v-model="multiSelect" multiple placeholder="多选" style="width: 240px">
          <el-option label="选项一" value="1" />
          <el-option label="选项二" value="2" />
          <el-option label="选项三" value="3" />
        </el-select>
      </div>
    </section>

    <section class="preview-section">
      <h2>表格组件 - 含排序</h2>
      <el-table :data="tableData" stripe>
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="name" label="名称" sortable />
        <el-table-column prop="status" label="状态">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '活跃' : '未激活' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="date" label="日期" sortable />
        <el-table-column label="操作" width="180">
          <template #default>
            <el-button size="small" type="primary">编辑</el-button>
            <el-button size="small" type="danger">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="preview-section">
      <h2>表格组件</h2>
      <el-table :data="tableData" stripe border>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="status" label="状态">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '活跃' : '未激活' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="date" label="日期" />
        <el-table-column label="操作" width="180">
          <template #default>
            <el-button size="small" type="primary">编辑</el-button>
            <el-button size="small" type="danger">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="preview-section">
      <h2>表单组件</h2>
      <el-form :model="formData" label-width="100px" style="max-width: 500px">
        <el-form-item label="用户名" required>
          <el-input v-model="formData.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="邮箱" required>
          <el-input v-model="formData.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="formData.role" placeholder="请选择角色">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="formData.active" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="formData.remark" type="textarea" :rows="3" placeholder="请输入备注" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary">提交</el-button>
          <el-button>取消</el-button>
        </el-form-item>
      </el-form>
    </section>

    <section class="preview-section">
      <h2>消息提示</h2>
      <div class="component-row">
        <el-button @click="showMessage('info')">Info 消息</el-button>
        <el-button type="primary" @click="showMessage('success')">Success 消息</el-button>
        <el-button type="warning" @click="showMessage('warning')">Warning 消息</el-button>
        <el-button type="danger" @click="showMessage('error')">Error 消息</el-button>
      </div>
    </section>

    <section class="preview-section">
      <h2>对话框</h2>
      <el-button type="primary" @click="dialogVisible = true">打开对话框</el-button>
      <el-dialog v-model="dialogVisible" title="对话框标题" width="500px">
        <p>这是一个对话框内容</p>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="dialogVisible = false">确定</el-button>
        </template>
      </el-dialog>
    </section>

    <section class="preview-section">
      <h2>标签</h2>
      <div class="component-row">
        <el-tag>默认标签</el-tag>
        <el-tag type="primary">主要标签</el-tag>
        <el-tag type="success">成功标签</el-tag>
        <el-tag type="warning">警告标签</el-tag>
        <el-tag type="danger">危险标签</el-tag>
        <el-tag type="info">信息标签</el-tag>
      </div>
      <div class="component-row">
        <el-tag effect="plain">朴素标签</el-tag>
        <el-tag type="primary" effect="plain">主要标签</el-tag>
        <el-tag type="success" effect="plain">成功标签</el-tag>
      </div>
    </section>

    <section class="preview-section">
      <h2>卡片</h2>
      <el-row :gutter="20">
        <el-col :span="8">
          <el-card shadow="hover">
            <template #header>
              <span>卡片标题</span>
            </template>
            <p>卡片内容</p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="always">
            <template #header>
              <span>总是显示阴影</span>
            </template>
            <p>卡片内容</p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>
              <span>从不显示阴影</span>
            </template>
            <p>卡片内容</p>
          </el-card>
        </el-col>
      </el-row>
    </section>

    <section class="preview-section">
      <h2>分页</h2>
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="1000"
        layout="total, sizes, prev, pager, next, jumper"
      />
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const inputValue = ref('')
const selectValue = ref('')
const multiSelect = ref([])

const formData = ref({
  username: '',
  email: '',
  role: '',
  active: true,
  remark: ''
})

const tableData = ref([
  { id: 1, name: '张三', status: 'active', date: '2024-01-15' },
  { id: 2, name: '李四', status: 'inactive', date: '2024-01-16' },
  { id: 3, name: '王五', status: 'active', date: '2024-01-17' }
])

const dialogVisible = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)

const showMessage = (type) => {
  ElMessage({
    message: `这是一条 ${type} 消息`,
    type
  })
}
</script>

<style scoped>
.theme-preview {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.theme-preview h1 {
  color: var(--el-color-primary);
  margin-bottom: 24px;
  font-size: 24px;
}

.preview-section {
  margin-bottom: 32px;
  padding: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.preview-section h2 {
  font-size: 16px;
  color: var(--el-text-color-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.color-swatches {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.swatch {
  width: 100px;
  height: 60px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.swatch small {
  font-size: 10px;
  opacity: 0.8;
}

.component-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 12px;
}

.component-row:last-child {
  margin-bottom: 0;
}

</style>
