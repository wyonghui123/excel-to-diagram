## 目录

1. [一、当前 Landing Page 结构](#一-当前-landing-page-结构)
2. [二、方案A：Header 右侧用户区域（推荐）](#二-方案a：header-右侧用户区域（推荐）)
3. [三、方案B：独立应用卡片（备选）](#三-方案b：独立应用卡片（备选）)
4. [四、推荐方案：方案A](#四-推荐方案：方案a)
5. [五、交互流程](#五-交互流程)
6. [六、状态管理](#六-状态管理)
7. [七、总结](#七-总结)

---
# Landing Page 系统管理入口位置设计

## 一、当前 Landing Page 结构

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] BIP应用架构管理                    [⚙ 设置]            │  ← Header
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  快捷应用                                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │产品版本  │ │架构数据  │ │AA图生成  │ │系统配置  │           │  ← 应用卡片
│  │管理      │ │管理      │ │          │ │          │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                 │
│  常用产品                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │  ← 常用产品
│  │  ...                                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  统计概览                                                        │  ← 统计概览
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ...                                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                      © 2026 BIP应用架构管理                      │  ← Footer
└─────────────────────────────────────────────────────────────────┘
```

## 二、方案A：Header 右侧用户区域（推荐）

### 未登录状态

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] BIP应用架构管理                    [⚙ 设置] [👤 登录]   │
└─────────────────────────────────────────────────────────────────┘
```

### 已登录状态（普通用户）

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] BIP应用架构管理              [⚙] [张三 ▼]              │
│                                            ↓                    │
│                                      ┌──────────┐              │
│                                      │ 个人设置 │              │
│                                      │ 退出登录 │              │
│                                      └──────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 已登录状态（管理员）

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] BIP应用架构管理              [⚙] [张三(管理员) ▼]      │
│                                            ↓                    │
│                                      ┌──────────────┐          │
│                                      │ 个人设置     │          │
│                                      │ ──────────── │          │
│                                      │ 系统管理  →  │ ← 仅管理员│
│                                      │ ──────────── │          │
│                                      │ 退出登录     │          │
│                                      └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 系统管理子菜单

```
                                      ┌──────────────────┐
                                      │ 用户管理         │
                                      │ 角色管理         │
                                      │ 权限配置         │
                                      │ 数据权限         │
                                      │ ──────────────── │
                                      │ 系统日志         │
                                      └──────────────────┘
```

## 三、方案B：独立应用卡片（备选）

### 在快捷应用区域新增卡片

```
┌─────────────────────────────────────────────────────────────────┐
│  快捷应用                                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │产品版本  │ │架构数据  │ │AA图生成  │ │系统配置  │           │
│  │管理      │ │管理      │ │          │ │          │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
│                                                                 │
│  系统管理（仅管理员可见）                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │用户管理  │ │角色管理  │ │数据权限  │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

### 优点
- 与现有应用卡片风格一致
- 管理功能一目了然

### 缺点
- 占用更多空间
- 与"快捷应用"定位不符（管理功能不是常用功能）

## 四、推荐方案：方案A

### 理由

1. **符合常见设计模式**：大多数企业级应用的管理入口都在用户菜单中
2. **节省空间**：不占用主内容区域
3. **权限清晰**：只有管理员能看到"系统管理"选项
4. **层级分明**：用户 → 个人设置；管理员 → 系统管理

### 实现要点

```vue
<!-- ArchWorkspaceNew.vue Header部分修改 -->
<header class="workspace-header">
  <div class="logo">
    <!-- ... logo内容 ... -->
  </div>
  <div class="header-actions">
    <button class="action-btn" title="设置" @click="openApp('config')">
      <AppIcon name="settings" size="sm" />
    </button>
    
    <!-- 新增：用户区域 -->
    <div class="user-area" v-if="!isLoggedIn">
      <button class="login-btn" @click="showLoginDialog = true">
        <AppIcon name="user" size="sm" />
        <span>登录</span>
      </button>
    </div>
    
    <div class="user-area" v-else>
      <button class="user-btn" @click="toggleUserMenu">
        <span class="user-name">{{ currentUser.displayName }}</span>
        <span v-if="isAdmin" class="admin-badge">管理员</span>
        <AppIcon name="chevron-down" size="sm" />
      </button>
      
      <div class="user-menu" v-show="showUserMenu">
        <div class="menu-item" @click="openPersonalSettings">
          <AppIcon name="user-cog" size="sm" />
          <span>个人设置</span>
        </div>
        
        <template v-if="isAdmin">
          <div class="menu-divider"></div>
          <div class="menu-item" @click="openSystemManagement">
            <AppIcon name="cog" size="sm" />
            <span>系统管理</span>
            <AppIcon name="chevron-right" size="sm" class="submenu-arrow" />
          </div>
          
          <!-- 子菜单 -->
          <div class="submenu" v-show="showSystemSubmenu">
            <div class="submenu-item" @click="openAdminPage('users')">用户管理</div>
            <div class="submenu-item" @click="openAdminPage('roles')">角色管理</div>
            <div class="submenu-item" @click="openAdminPage('permissions')">权限配置</div>
            <div class="submenu-item" @click="openAdminPage('data-permissions')">数据权限</div>
            <div class="submenu-divider"></div>
            <div class="submenu-item" @click="openAdminPage('logs')">系统日志</div>
          </div>
        </template>
        
        <div class="menu-divider"></div>
        <div class="menu-item logout" @click="handleLogout">
          <AppIcon name="logout" size="sm" />
          <span>退出登录</span>
        </div>
      </div>
    </div>
  </div>
</header>
```

### 样式设计

```scss
.user-area {
  display: flex;
  align-items: center;
  margin-left: var(--spacing-md);
}

.login-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 14px;
  transition: all var(--transition-normal);
  
  &:hover {
    background: var(--color-primary-dark);
  }
}

.user-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-normal);
  
  &:hover {
    border-color: var(--color-primary);
  }
}

.admin-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--color-primary);
  color: white;
  border-radius: var(--radius-sm);
}

.user-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: var(--spacing-xs);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  min-width: 180px;
  z-index: 100;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background var(--transition-normal);
  
  &:hover {
    background: var(--color-bg-secondary);
  }
  
  &.logout {
    color: var(--color-danger);
  }
}

.menu-divider {
  height: 1px;
  background: var(--color-border);
  margin: var(--spacing-xs) 0;
}

.submenu {
  position: absolute;
  left: 100%;
  top: 0;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  min-width: 140px;
}

.submenu-item {
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background var(--transition-normal);
  
  &:hover {
    background: var(--color-bg-secondary);
  }
}
```

## 五、交互流程

### 登录流程

```
1. 用户点击"登录"按钮
   ↓
2. 显示登录对话框
   ↓
3. 输入用户名密码
   ↓
4. 验证成功，获取用户信息和权限
   ↓
5. 更新Header显示用户名
   ↓
6. 如果是管理员，显示"系统管理"菜单项
```

### 访问系统管理

```
1. 管理员点击用户菜单
   ↓
2. 显示下拉菜单
   ↓
3. 悬停"系统管理"项
   ↓
4. 显示子菜单
   ↓
5. 点击具体管理项
   ↓
6. 打开对应管理页面
```

## 六、状态管理

```javascript
// stores/authStore.js
export const useAuthStore = defineStore('auth', {
  state: () => ({
    isLoggedIn: false,
    currentUser: null,
    permissions: [],
    dataPermissions: []
  }),
  
  getters: {
    isAdmin: (state) => {
      return state.currentUser?.roles?.some(r => r.code === 'admin')
    },
    
    hasPermission: (state) => (permissionCode) => {
      return state.permissions.includes(permissionCode) || 
             state.permissions.includes('*')
    }
  },
  
  actions: {
    async login(username, password) {
      // 调用登录API
      const response = await authApi.login(username, password)
      
      // 保存token
      localStorage.setItem('token', response.token)
      
      // 设置用户信息
      this.currentUser = response.user
      this.permissions = response.permissions
      this.dataPermissions = response.dataPermissions
      this.isLoggedIn = true
    },
    
    logout() {
      localStorage.removeItem('token')
      this.currentUser = null
      this.permissions = []
      this.dataPermissions = []
      this.isLoggedIn = false
    }
  }
})
```

## 七、总结

### 推荐方案

**Header右侧用户区域**：
- 未登录：显示"登录"按钮
- 已登录：显示用户名 + 下拉菜单
- 管理员：下拉菜单中包含"系统管理"子菜单

### 优势

1. 符合主流企业级应用设计
2. 不占用主内容区域
3. 权限分层清晰
4. 实现简单，改动小
