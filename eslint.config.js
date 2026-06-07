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
