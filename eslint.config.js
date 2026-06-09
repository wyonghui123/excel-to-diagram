import js from '@eslint/js'
import vuePlugin from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'

export default [
  // 基础推荐规则
  js.configs.recommended,

  // 全局忽略
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      '*.min.js',
      'src/services/graphqlClient.js',  // POC 阶段豁免
      // TypeScript 语法在 .vue 中，ESLint 无法解析
      'src/views/SystemManagement/components/ConditionRuleList.vue',
      'src/views/SystemManagement/components/MenuPermissionMatrix.vue',
      'src/views/SystemManagement/components/OverlapWarning.vue',
      'src/views/SystemManagement/components/PermissionConfigPanel.vue',
      'src/views/SystemManagement/RolePermissionDetail.vue',
    ],
  },

  // Vue 文件配置
  {
    files: ['src/**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: 'module',
      },
      globals: {
        console: 'readonly',
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        FormData: 'readonly',
        FileReader: 'readonly',
        HTMLElement: 'readonly',
        Event: 'readonly',
        CustomEvent: 'readonly',
        IntersectionObserver: 'readonly',
        ResizeObserver: 'readonly',
        navigator: 'readonly',
        alert: 'readonly',
        confirm: 'readonly',
        fetch: 'readonly',  // C3 规则单独拦截
      },
    },
    plugins: {
      vue: vuePlugin,
    },
    rules: {
      // Vue 核心规则
      'vue/no-unused-components': 'off',
      'vue/no-unused-vars': 'off',
      'vue/no-v-text-v-html-on-component': 'warn',
      'vue/require-v-for-key': 'warn',
      'vue/no-mutating-props': 'warn',
      // 关闭格式化规则（由 IDE/Prettier 处理）
      'vue/html-indent': 'off',
      'vue/html-self-closing': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/max-len': 'off',
    },
  },

  // C3: .vue 文件内禁止 fetch()（Spec 约束 C3）
  {
    files: ['src/**/*.vue'],
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'C3: .vue 文件禁止直接调用 fetch()，请使用 service 层或 httpClient (apiV1/apiV2)',
        },
      ],
    },
  },

  // C2: Pinia store 内禁止 fetch()（Spec 约束 C2）
  {
    files: ['src/stores/**/*.js'],
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'C2: Pinia store 禁止直接调用 fetch()，请使用 service 层或 httpClient (apiV1/apiV2)',
        },
      ],
    },
  },

  // C4: composable 层禁止 fetch()（Spec 约束 C4）
  {
    files: ['src/composables/**/*.js', 'src/components/composables/**/*.js'],
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'C4: composable 层禁止直接调用 fetch()，请使用 httpClient (apiV1/apiV2)',
        },
      ],
    },
  },

  // C1: composable 内函数行数限制（Spec 约束 C1）
  {
    files: ['src/composables/**/*.js'],
    rules: {
      'max-lines-per-function': [
        'error',
        {
          max: 30,
          skipBlankLines: true,
          skipComments: true,
        },
      ],
    },
  },

  // service 层允许 fetch（通过 httpClient 间接使用）
  {
    files: ['src/services/**/*.js', 'src/utils/httpClient.js'],
    rules: {
      'no-restricted-globals': 'off',
    },
  },

  // [NEW 2026-06-09] 禁止 Vue 文件内直接使用 Element Plus 的 ElMessage / ElNotification
  // 必须走 useCrudMessage (基于 useMessage/NotificationContainer, z-index 1700, teleport to body)
  // 原因：ElMessage fixed 定位在 high-z modal 场景下被遮挡, 文案五花八门不利于 i18n
  // ElMessageBox 是 modal 确认对话框 (UX 跟 toast 不同), 不在禁止范围, 单独走 el-dialog
  // dev/* 路径下豁免 (组件展示页面故意展示 EP 原生效果)
  // 详见: docs/superpowers/specs/2026-06-09-user-lock-and-feedback-design.md
  {
    files: ['src/**/*.vue'],
    // 注意：使用否定模式排除 dev 页面 (ComponentComparison, dev/*)
    // ESLint flat config 的 files 不支持 !, 改用单独块覆盖 (见下方)
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'element-plus',
              importNames: ['ElMessage', 'ElNotification'],
              message: '禁止直接使用 Element Plus 消息组件，请改用 useCrudMessage / useMessage composable。',
            },
          ],
        },
      ],
    },
  },

  // 覆盖: dev 页面 + ComponentComparison 豁免 (故意展示 EP 原生组件效果)
  {
    files: [
      'src/views/dev/**/*.vue',
      'src/views/ComponentComparison.vue',
    ],
    rules: {
      'no-restricted-imports': 'off',
    },
  },

  // 通用规则
  {
    files: ['src/**/*.{js,vue}'],
    languageOptions: {
      globals: {
        console: 'readonly',
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        FormData: 'readonly',
        FileReader: 'readonly',
        HTMLElement: 'readonly',
        Event: 'readonly',
        CustomEvent: 'readonly',
        IntersectionObserver: 'readonly',
        ResizeObserver: 'readonly',
        navigator: 'readonly',
        alert: 'readonly',
        confirm: 'readonly',
        fetch: 'readonly',  // C2/C3 规则单独拦截
        process: 'readonly',
        __VITE_API_BASE__: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-console': 'off',
      'no-undef': 'warn',              // 浏览器全局变量多，降级为 warn
      'no-empty': 'off',
      'no-useless-assignment': 'off',
      'no-useless-escape': 'off',
      'no-prototype-builtins': 'off',
      'no-regex-spaces': 'off',
      'no-constant-condition': 'off',
      'no-const-assign': 'warn',
      'no-case-declarations': 'off',
      'no-dupe-class-members': 'warn',
    },
  },
]
