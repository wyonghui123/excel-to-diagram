<template>
  <div class="component-comparison">
    <div class="page-header">
      <h1>UI组件库全量对比测试</h1>
      <p class="subtitle">自建组件（60+） vs Element Plus — 逐个对比 | 包含顶部导航系统 [2026-05-19 更新]</p>
    </div>

    <!-- ==================== Tab 导航 ==================== -->
    <div class="comparison-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- ==================== 基础组件对比 Tab ==================== -->
    <div v-show="activeTab === 'basic'" class="tab-content">
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-number">60+</span>
        <span class="stat-label">自建组件总数</span>
      </div>
      <div class="stat-item">
        <span class="stat-number">~15,000</span>
        <span class="stat-label">自建代码行数</span>
      </div>
      <div class="stat-item">
        <span class="stat-number">82+</span>
        <span class="stat-label">Element Plus 组件数</span>
      </div>
      <div class="stat-item">
        <span class="stat-number">6</span>
        <span class="stat-label">新增导航组件</span>
      </div>
    </div>

    <!-- ==================== 圆润风格预览 ==================== -->
    <section class="rounded-preview-section">
      <h2>[SYMBOL] Element Plus 圆润风格预览 (YonDesign 风格)</h2>
      <p class="preview-intro">
        对比 Element Plus 默认直角风格与圆润风格（改造后）的视觉效果差异。
        圆润风格将圆角从 2px/4px 增加到 4px/6px，更加柔和舒适。
      </p>

      <div class="rounded-comparison">
        <!-- 按钮对比 -->
        <div class="rounded-group">
          <h3>按钮</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-button type="primary">主要按钮</el-button>
                <el-button type="success">成功</el-button>
                <el-button type="danger">危险</el-button>
                <el-button round>圆角</el-button>
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-button type="primary">主要按钮</el-button>
                <el-button type="success">成功</el-button>
                <el-button type="danger">危险</el-button>
                <el-button round>圆角</el-button>
              </div>
              <p class="rounded-info">圆角: 6px</p>
            </div>
          </div>
        </div>

        <!-- ==================== Link 按钮 Material Design 风格 ==================== -->
        <div class="rounded-group link-button-section">
          <h3>Link 按钮 (操作列) - Material Design 风格</h3>
          <p class="preview-intro link-intro">
            <strong>[设计原则]</strong> 采用 Google Material Design 3 Text Button 规范<br>
            - Hover/Focus/Active 状态<strong>只改变背景透明度</strong>，文字颜色始终保持不变<br>
            - 通过背景深浅 (6% &lt; 12% &lt; 16%) 表达交互状态层次<br>
            - 文字颜色固定使用 YonDesign Orange (#ea580c)，确保可读性稳定
          </p>

          <div class="link-demo-container">
            <!-- 状态展示区域 -->
            <div class="link-states-grid">
              <div class="link-state-item">
                <h4>默认状态 (Default)</h4>
                <div class="link-state-demo">
                  <el-button size="small" link>详情</el-button>
                  <el-button size="small" link>编辑</el-button>
                  <el-button size="small" link>删除</el-button>
                </div>
                <div class="state-specs">
                  <span class="spec-item">
                    <span class="spec-label">文字色:</span>
                    <span class="spec-value color-orange">#ea580c</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">背景:</span>
                    <span class="spec-value">transparent</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">透明度:</span>
                    <span class="spec-value">0%</span>
                  </span>
                </div>
              </div>

              <div class="link-state-item">
                <h4>Hover 状态 (鼠标悬停)</h4>
                <div class="link-state-demo hover-simulation">
                  <el-button size="small" link class="simulated-hover">详情</el-button>
                  <el-button size="small" link class="simulated-hover">编辑</el-button>
                  <el-button size="small" link class="simulated-hover">删除</el-button>
                </div>
                <div class="state-specs">
                  <span class="spec-item">
                    <span class="spec-label">文字色:</span>
                    <span class="spec-value color-orange">#ea580c</span>
                    <span class="spec-remark">(不变)</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">背景:</span>
                    <span class="spec-value bg-opacity-6">rgba(234, 88, 12, 0.06)</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">透明度:</span>
                    <span class="spec-value opacity-highlight">6%</span>
                  </span>
                </div>
              </div>

              <div class="link-state-item">
                <h4>Focus 状态 (键盘导航)</h4>
                <div class="link-state-demo focus-simulation">
                  <el-button size="small" link class="simulated-focus">详情</el-button>
                  <el-button size="small" link class="simulated-focus">编辑</el-button>
                  <el-button size="small" link class="simulated-focus">删除</el-button>
                </div>
                <div class="state-specs">
                  <span class="spec-item">
                    <span class="spec-label">文字色:</span>
                    <span class="spec-value color-orange">#ea580c</span>
                    <span class="spec-remark">(不变)</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">背景:</span>
                    <span class="spec-value bg-opacity-12">rgba(234, 88, 12, 0.12)</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">透明度:</span>
                    <span class="spec-value opacity-highlight">12%</span>
                  </span>
                </div>
              </div>

              <div class="link-state-item">
                <h4>Active 状态 (鼠标点击)</h4>
                <div class="link-state-demo active-simulation">
                  <el-button size="small" link class="simulated-active">详情</el-button>
                  <el-button size="small" link class="simulated-active">编辑</el-button>
                  <el-button size="small" link class="simulated-active">删除</el-button>
                </div>
                <div class="state-specs">
                  <span class="spec-item">
                    <span class="spec-label">文字色:</span>
                    <span class="spec-value color-orange">#ea580c</span>
                    <span class="spec-remark">(不变)</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">背景:</span>
                    <span class="spec-value bg-opacity-16">rgba(234, 88, 12, 0.16)</span>
                  </span>
                  <span class="spec-item">
                    <span class="spec-label">透明度:</span>
                    <span class="spec-value opacity-highlight">16%</span>
                  </span>
                </div>
              </div>
            </div>

            <!-- 核心优势说明 -->
            <div class="link-advantages">
              <h4>核心优势</h4>
              <ul class="advantages-list">
                <li><strong>[OK] 可读性稳定</strong>: 文字颜色始终 #ea580c，对比度保持 ~3.2:1</li>
                <li><strong>[OK] 符合 Material Design</strong>: 遵循 Google 最佳实践</li>
                <li><strong>[OK] 渐进式反馈</strong>: 6% &lt; 12% &lt; 16%，状态层次清晰</li>
                <li><strong>[OK] 性能优秀</strong>: 只改变背景透明度，无需重绘文字</li>
                <li><strong>[OK] 代码简洁</strong>: 实现简单，维护成本低</li>
              </ul>
            </div>

            <!-- 实际应用场景示例 -->
            <div class="link-real-world-example">
              <h4>实际应用：表格操作列</h4>
              <div class="example-table">
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>邮箱</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>test_user_001</td>
                      <td>test@example.com</td>
                      <td class="action-cell">
                        <el-button size="small" link>详情</el-button>
                        <el-button size="small" link>编辑</el-button>
                        <el-button size="small" link>删除</el-button>
                      </td>
                    </tr>
                    <tr>
                      <td>admin_user</td>
                      <td>admin@local</td>
                      <td class="action-cell">
                        <el-button size="small" link>详情</el-button>
                        <el-button size="small" link>编辑</el-button>
                        <el-button size="small" link>删除</el-button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="example-note">
                [NOTE] 将鼠标悬停在上方按钮上查看实际 Hover 效果（6% 橙色背景）
              </p>
            </div>
          </div>
        </div>

        <!-- ==================== Filled 按钮（实心按钮） ==================== -->
        <div class="rounded-group filled-button-section">
          <h3>Filled 按钮（实心按钮） - YonDesign 规范</h3>
          <p class="preview-intro filled-intro">
            <strong>[设计原则]</strong> 采用 YonDesign Filled Button 规范<br>
            - 所有状态<strong>保持白色文字</strong>，确保高对比度和可读性<br>
            - 通过背景色深浅变化表达交互状态层次<br>
            - Primary 使用橙色系，Success/Warning/Danger 使用对应色系
          </p>

          <div class="filled-demo-container">
            <!-- Primary 按钮状态 -->
            <div class="filled-type-group">
              <h4>Primary 按钮 (主要操作)</h4>
              <div class="filled-states-grid">
                <div class="filled-state-item">
                  <h5>默认状态 (Default)</h5>
                  <div class="filled-state-demo">
                    <el-button type="primary">新建用户</el-button>
                    <el-button type="primary" size="small">保存</el-button>
                  </div>
                  <div class="state-specs">
                    <span class="spec-item">
                      <span class="spec-label">背景:</span>
                      <span class="spec-value color-orange">#ea580c</span>
                    </span>
                    <span class="spec-item">
                      <span class="spec-label">文字:</span>
                      <span class="spec-value color-white">#ffffff</span>
                    </span>
                    <span class="spec-item">
                      <span class="spec-label">对比度:</span>
                      <span class="spec-value contrast-good">4.6:1 [OK]</span>
                    </span>
                  </div>
                </div>

                <div class="filled-state-item">
                  <h5>Hover 状态 (鼠标悬停)</h5>
                  <div class="filled-state-demo">
                    <el-button type="primary" class="simulated-hover-primary">新建用户</el-button>
                    <el-button type="primary" size="small" class="simulated-hover-primary">保存</el-button>
                  </div>
                  <div class="state-specs">
                    <span class="spec-item">
                      <span class="spec-label">背景:</span>
                      <span class="spec-value color-light-orange">#fb923c</span>
                    </span>
                    <span class="spec-item">
                      <span class="spec-label">文字:</span>
                      <span class="spec-value color-white">#ffffff</span>
                      <span class="spec-remark">(不变)</span>
                    </span>
                    <span class="spec-item">
                      <span class="spec-label">对比度:</span>
                      <span class="spec-value contrast-good">3.8:1 [OK]</span>
                    </span>
                  </div>
                </div>

                <div class="filled-state-item">
                  <h5>Active 状态 (鼠标点击)</h5>
                  <div class="filled-state-demo">
                    <el-button type="primary" class="simulated-active-primary">新建用户</el-button>
                    <el-button type="primary" size="small" class="simulated-active-primary">保存</el-button>
                  </div>
                  <div class="state-specs">
                    <span class="spec-item">
                      <span class="spec-label">背景:</span>
                      <span class="spec-value color-dark-orange">#c2410c</span>
                    </span>
                    <span class="spec-item">
                      <span class="spec-label">文字:</span>
                      <span class="spec-value color-white">#ffffff</span>
                      <span class="spec-remark">(不变)</span>
                    </span>
                    <span class="spec-item">
                      <span class="spec-label">对比度:</span>
                      <span class="spec-value contrast-excellent">5.5:1 [优秀]</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 其他类型按钮 -->
            <div class="filled-type-group">
              <h4>其他类型按钮 (Success / Warning / Danger)</h4>
              <div class="filled-other-types">
                <div class="type-row">
                  <span class="type-label">Success:</span>
                  <el-button type="success">成功</el-button>
                  <span class="type-spec">背景 #22c55e | 文字 #fff | Hover #4ade80</span>
                </div>
                <div class="type-row">
                  <span class="type-label">Warning:</span>
                  <el-button type="warning">警告</el-button>
                  <span class="type-spec">背景 #f59e0b | 文字 #fff | Hover #fbbf24</span>
                </div>
                <div class="type-row">
                  <span class="type-label">Danger:</span>
                  <el-button type="danger">危险</el-button>
                  <span class="type-spec">背景 #ea580c | 文字 #fff | Hover #f97316</span>
                </div>
              </div>
            </div>

            <!-- 核心优势说明 -->
            <div class="filled-advantages">
              <h4>核心优势</h4>
              <ul class="advantages-list">
                <li><strong>[OK] 对比度优秀</strong>: 白色文字 + 有色背景，始终满足 WCAG AA 标准</li>
                <li><strong>[OK] 交互清晰</strong>: 背景色变化明确表达 Hover/Active 状态</li>
                <li><strong>[OK] 一致性高</strong>: 所有按钮类型遵循相同的设计模式</li>
                <li><strong>[OK] 符合 YonDesign</strong>: 使用橙色系作为主色调，统一视觉语言</li>
                <li><strong>[FIXED] 已修复</strong>: Hover 时不再出现橙/红色文字，避免视觉混淆</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- 输入框对比 -->
        <div class="rounded-group">
          <h3>输入框</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-input placeholder="请输入内容" style="width: 180px" />
                <el-input placeholder="禁用状态" disabled style="width: 180px; margin-top: 8px" />
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-input placeholder="请输入内容" style="width: 180px" />
                <el-input placeholder="禁用状态" disabled style="width: 180px; margin-top: 8px" />
              </div>
              <p class="rounded-info">圆角: 6px</p>
            </div>
          </div>
        </div>

        <!-- 选择器对比 -->
        <div class="rounded-group">
          <h3>选择器</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-select placeholder="请选择" style="width: 180px">
                  <el-option label="选项一" value="1" />
                  <el-option label="选项二" value="2" />
                </el-select>
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-select placeholder="请选择" style="width: 180px">
                  <el-option label="选项一" value="1" />
                  <el-option label="选项二" value="2" />
                </el-select>
              </div>
              <p class="rounded-info">圆角: 6px</p>
            </div>
          </div>
        </div>

        <!-- 标签对比 -->
        <div class="rounded-group">
          <h3>标签</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-tag type="primary">主要</el-tag>
                <el-tag type="success">成功</el-tag>
                <el-tag type="warning">警告</el-tag>
                <el-tag type="danger">危险</el-tag>
                <el-tag>默认</el-tag>
              </div>
              <p class="rounded-info">圆角: 2px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-tag type="primary">主要</el-tag>
                <el-tag type="success">成功</el-tag>
                <el-tag type="warning">警告</el-tag>
                <el-tag type="danger">危险</el-tag>
                <el-tag>默认</el-tag>
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
          </div>
        </div>

        <!-- 卡片对比 -->
        <div class="rounded-group">
          <h3>卡片</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-card style="width: 200px">
                  <template #header>卡片标题</template>
                  <p>卡片内容区域</p>
                </el-card>
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-card style="width: 200px">
                  <template #header>卡片标题</template>
                  <p>卡片内容区域</p>
                </el-card>
              </div>
              <p class="rounded-info">圆角: 8px</p>
            </div>
          </div>
        </div>

        <!-- 分页对比 -->
        <div class="rounded-group">
          <h3>分页</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-pagination :current-page="1" :page-size="10" :total="100" layout="prev, pager, next" style="justify-content: flex-start" />
              </div>
              <p class="rounded-info">圆角: 2px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-pagination :current-page="1" :page-size="10" :total="100" layout="prev, pager, next" style="justify-content: flex-start" />
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
          </div>
        </div>

        <!-- 表格对比 -->
        <div class="rounded-group">
          <h3>表格</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Element Plus 默认</h4>
              <div class="rounded-demo">
                <el-table :data="tableDataPreview" style="width: 350px" size="small">
                  <el-table-column prop="name" label="名称" />
                  <el-table-column prop="status" label="状态" />
                  <el-table-column label="操作" width="80">
                    <template #default>
                      <el-button size="small" type="primary">编辑</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <p class="rounded-info">圆角: 4px</p>
            </div>
            <div class="rounded-item rounded">
              <h4>圆润风格 (改造后)</h4>
              <div class="rounded-demo">
                <el-table :data="tableDataPreview" style="width: 350px" size="small">
                  <el-table-column prop="name" label="名称" />
                  <el-table-column prop="status" label="状态" />
                  <el-table-column label="操作" width="80">
                    <template #default>
                      <el-button size="small" type="primary">编辑</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
              <p class="rounded-info">圆角: 6px</p>
            </div>
          </div>
        </div>
      </div>

      <div class="rounded-summary">
        <h3>改造说明</h3>
        <p>圆润风格通过修改 <code>element-variables.scss</code> 中的圆角变量实现：</p>
        <div class="rounded-vars">
          <div class="var-item">
            <code>--el-border-radius-base</code>: 4px → <strong>6px</strong>
          </div>
          <div class="var-item">
            <code>--el-border-radius-small</code>: 2px → <strong>4px</strong>
          </div>
          <div class="var-item">
            <code>--el-border-radius-round</code>: 20px → <strong>8px</strong>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 未使用的 Element Plus 组件展示 ==================== -->
    <section class="unused-preview-section">
      <h2>[DECORATIVE] Element Plus 有但我们没有的组件（50个）</h2>
      <p class="preview-intro">
        以下是 Element Plus 提供的组件，但在当前应用中尚未使用。对比展示标准样式与圆润风格（改造后）的视觉效果，供后续开发参考。
      </p>

      <!-- 组件对比表格 -->
      <div class="ep-comparison-table">
        <!-- 表头 -->
        <div class="ep-comparison-header">
          <div class="ep-col-name">组件名称</div>
          <div class="ep-col-standard">Element Plus 标准</div>
          <div class="ep-col-yondesign">Element Plus + YonDesign（圆润+yondesign）</div>
        </div>

        <!-- Alert 警告提示 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Alert</strong>
            <span>警告提示</span>
          </div>
          <div class="ep-col-standard">
            <el-alert type="success" title="成功提示" :closable="false" show-icon />
            <el-alert type="warning" title="警告提示" :closable="false" show-icon style="margin-top: 4px" />
          </div>
          <div class="ep-col-yondesign">
            <el-alert type="success" title="成功提示" :closable="false" show-icon class="ep-rounded" />
            <el-alert type="warning" title="警告提示" :closable="false" show-icon class="ep-rounded" style="margin-top: 4px" />
          </div>
        </div>

        <!-- Badge 徽标 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Badge</strong>
            <span>徽标</span>
          </div>
          <div class="ep-col-standard">
            <el-badge :value="12" type="primary">
              <el-button size="small">评论</el-button>
            </el-badge>
            <el-badge :value="3" type="danger" style="margin-left: 12px">
              <el-button size="small">通知</el-button>
            </el-badge>
          </div>
          <div class="ep-col-yondesign">
            <el-badge :value="12" type="primary">
              <el-button size="small" class="ep-rounded">评论</el-button>
            </el-badge>
            <el-badge :value="3" type="danger" style="margin-left: 12px">
              <el-button size="small" class="ep-rounded">通知</el-button>
            </el-badge>
          </div>
        </div>

        <!-- Button 按钮 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Button</strong>
            <span>按钮</span>
          </div>
          <div class="ep-col-standard">
            <el-button type="primary">主要</el-button>
            <el-button type="success">成功</el-button>
            <el-button type="danger">危险</el-button>
          </div>
          <div class="ep-col-yondesign">
            <el-button type="primary" class="ep-rounded">主要</el-button>
            <el-button type="success" class="ep-rounded">成功</el-button>
            <el-button type="danger" class="ep-rounded">危险</el-button>
          </div>
        </div>

        <!-- Input 输入框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Input</strong>
            <span>输入框</span>
          </div>
          <div class="ep-col-standard">
            <el-input placeholder="请输入" style="width: 180px" />
          </div>
          <div class="ep-col-yondesign">
            <el-input placeholder="请输入" style="width: 180px" class="ep-rounded" />
          </div>
        </div>

        <!-- Select 选择器 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Select</strong>
            <span>选择器</span>
          </div>
          <div class="ep-col-standard">
            <el-select placeholder="请选择" style="width: 180px">
              <el-option label="选项一" value="1" />
              <el-option label="选项二" value="2" />
            </el-select>
          </div>
          <div class="ep-col-yondesign">
            <el-select placeholder="请选择" style="width: 180px" class="ep-rounded" />
          </div>
        </div>

        <!-- Tag 标签 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Tag</strong>
            <span>标签</span>
          </div>
          <div class="ep-col-standard">
            <el-tag type="primary">主要</el-tag>
            <el-tag type="success">成功</el-tag>
            <el-tag type="warning">警告</el-tag>
            <el-tag type="danger">危险</el-tag>
            <div style="margin-top: 8px; font-size: 11px; color: #909399">EP 标准 2px 圆角</div>
          </div>
          <div class="ep-col-yondesign">
            <el-tag type="primary" class="ep-rounded-tag">主要</el-tag>
            <el-tag type="success" class="ep-rounded-tag">成功</el-tag>
            <el-tag type="warning" class="ep-rounded-tag">警告</el-tag>
            <el-tag type="danger" class="ep-rounded-tag">危险</el-tag>
            <div style="margin-top: 8px; font-size: 11px; color: var(--el-color-primary)">YonDesign 4px 圆角</div>
          </div>
        </div>

        <!-- Card 卡片 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Card</strong>
            <span>卡片</span>
          </div>
          <div class="ep-col-standard">
            <el-card style="width: 180px">
              <template #header>标题</template>
              <p>内容</p>
            </el-card>
          </div>
          <div class="ep-col-yondesign">
            <el-card style="width: 180px" class="ep-rounded-card">
              <template #header>标题</template>
              <p>内容</p>
            </el-card>
          </div>
        </div>

        <!-- Progress 进度条 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Progress</strong>
            <span>进度条</span>
          </div>
          <div class="ep-col-standard">
            <el-progress :percentage="70" style="width: 180px" />
            <el-progress :percentage="100" status="success" style="width: 180px; margin-top: 8px" />
          </div>
          <div class="ep-col-yondesign">
            <el-progress :percentage="70" style="width: 180px" class="ep-progress" />
            <el-progress :percentage="100" status="success" style="width: 180px; margin-top: 8px" class="ep-progress" />
          </div>
        </div>

        <!-- Avatar 头像 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Avatar</strong>
            <span>头像</span>
          </div>
          <div class="ep-col-standard">
            <el-avatar :size="36" src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png" />
            <el-avatar :size="36" style="margin-left: 8px">U</el-avatar>
            <el-avatar :size="36" style="margin-left: 8px" icon="UserFilled" />
          </div>
          <div class="ep-col-yondesign">
            <el-avatar :size="36" src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png" class="ep-rounded-avatar" />
            <el-avatar :size="36" style="margin-left: 8px" class="ep-rounded-avatar">U</el-avatar>
            <el-avatar :size="36" style="margin-left: 8px" icon="UserFilled" class="ep-rounded-avatar" />
          </div>
        </div>

        <!-- Tooltip 文字提示 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Tooltip</strong>
            <span>文字提示</span>
          </div>
          <div class="ep-col-standard">
            <el-tooltip content="提示信息" placement="top">
              <el-button>悬停</el-button>
            </el-tooltip>
          </div>
          <div class="ep-col-yondesign">
            <el-tooltip content="提示信息" placement="top">
              <el-button class="ep-rounded">悬停</el-button>
            </el-tooltip>
          </div>
        </div>

        <!-- Switch 开关 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Switch</strong>
            <span>开关</span>
          </div>
          <div class="ep-col-standard">
            <el-switch v-model="switchValue1" />
            <el-switch v-model="switchValue2" style="margin-left: 16px" />
          </div>
          <div class="ep-col-yondesign">
            <el-switch v-model="switchValue1" class="ep-rounded-switch" />
            <el-switch v-model="switchValue2" style="margin-left: 16px" class="ep-rounded-switch" />
          </div>
        </div>

        <!-- Slider 滑块 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Slider</strong>
            <span>滑块</span>
          </div>
          <div class="ep-col-standard">
            <el-slider v-model="sliderValue" style="width: 180px" />
          </div>
          <div class="ep-col-yondesign">
            <el-slider v-model="sliderValue" style="width: 180px" class="ep-slider" />
          </div>
        </div>

        <!-- Radio 单选框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Radio</strong>
            <span>单选框</span>
          </div>
          <div class="ep-col-standard">
            <el-radio-group v-model="radioValue">
              <el-radio value="1">选项一</el-radio>
              <el-radio value="2">选项二</el-radio>
            </el-radio-group>
          </div>
          <div class="ep-col-yondesign">
            <el-radio-group v-model="radioValue">
              <el-radio value="1" class="ep-rounded-radio">选项一</el-radio>
              <el-radio value="2" class="ep-rounded-radio">选项二</el-radio>
            </el-radio-group>
          </div>
        </div>

        <!-- Checkbox 多选框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Checkbox</strong>
            <span>多选框</span>
          </div>
          <div class="ep-col-standard">
            <el-checkbox-group v-model="checkboxValue">
              <el-checkbox value="1">选项一</el-checkbox>
              <el-checkbox value="2">选项二</el-checkbox>
            </el-checkbox-group>
          </div>
          <div class="ep-col-yondesign">
            <el-checkbox-group v-model="checkboxValue">
              <el-checkbox value="1" class="ep-rounded-checkbox">选项一</el-checkbox>
              <el-checkbox value="2" class="ep-rounded-checkbox">选项二</el-checkbox>
            </el-checkbox-group>
          </div>
        </div>

        <!-- InputNumber 数字输入框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>InputNumber</strong>
            <span>数字输入框</span>
          </div>
          <div class="ep-col-standard">
            <el-input-number v-model="inputNumberValue" :min="1" :max="10" />
          </div>
          <div class="ep-col-yondesign">
            <el-input-number v-model="inputNumberValue" :min="1" :max="10" class="ep-rounded" />
          </div>
        </div>

        <!-- DatePicker 日期选择器 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>DatePicker</strong>
            <span>日期选择器</span>
          </div>
          <div class="ep-col-standard">
            <el-date-picker v-model="dateValue" type="date" placeholder="选择日期" style="width: 180px" />
          </div>
          <div class="ep-col-yondesign">
            <el-date-picker v-model="dateValue" type="date" placeholder="选择日期" style="width: 180px" class="ep-rounded" />
          </div>
        </div>

        <!-- TimePicker 时间选择器 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>TimePicker</strong>
            <span>时间选择器</span>
          </div>
          <div class="ep-col-standard">
            <el-time-picker v-model="timeValue" placeholder="选择时间" style="width: 180px" />
          </div>
          <div class="ep-col-yondesign">
            <el-time-picker v-model="timeValue" placeholder="选择时间" style="width: 180px" class="ep-rounded" />
          </div>
        </div>

        <!-- Cascader 级联选择器 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Cascader</strong>
            <span>级联选择器</span>
          </div>
          <div class="ep-col-standard">
            <el-cascader v-model="cascaderValue" :options="cascaderOptions" placeholder="请选择" style="width: 180px" />
          </div>
          <div class="ep-col-yondesign">
            <el-cascader v-model="cascaderValue" :options="cascaderOptions" placeholder="请选择" style="width: 180px" class="ep-rounded" />
          </div>
        </div>

        <!-- Transfer 穿梭框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Transfer</strong>
            <span>穿梭框</span>
          </div>
          <div class="ep-col-standard">
            <el-transfer v-model="transferValue" :data="transferData" style="height: 160px" />
          </div>
          <div class="ep-col-yondesign">
            <el-transfer v-model="transferValue" :data="transferData" style="height: 160px" class="ep-rounded-transfer" />
          </div>
        </div>

        <!-- Rate 评分 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Rate</strong>
            <span>评分</span>
          </div>
          <div class="ep-col-standard">
            <el-rate v-model="rateValue" />
          </div>
          <div class="ep-col-yondesign">
            <el-rate v-model="rateValue" class="ep-rounded-rate" />
          </div>
        </div>

        <!-- ColorPicker 颜色选择器 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>ColorPicker</strong>
            <span>颜色选择器</span>
          </div>
          <div class="ep-col-standard">
            <el-color-picker v-model="colorValue" />
          </div>
          <div class="ep-col-yondesign">
            <el-color-picker v-model="colorValue" class="ep-rounded" />
          </div>
        </div>

        <!-- Popover 弹出框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Popover</strong>
            <span>弹出框</span>
          </div>
          <div class="ep-col-standard">
            <el-popover placement="top" title="标题" :content="'描述文字'" trigger="click">
              <template #reference>
                <el-button>点击</el-button>
              </template>
            </el-popover>
          </div>
          <div class="ep-col-yondesign">
            <el-popover placement="top" title="标题" :content="'描述文字'" trigger="click">
              <template #reference>
                <el-button class="ep-rounded">点击</el-button>
              </template>
            </el-popover>
          </div>
        </div>

        <!-- Dialog 对话框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Dialog</strong>
            <span>对话框</span>
          </div>
          <div class="ep-col-standard">
            <el-button @click="dialogVisible = true">打开对话框</el-button>
          </div>
          <div class="ep-col-yondesign">
            <el-button @click="dialogVisible = true" class="ep-rounded">打开对话框</el-button>
          </div>
        </div>

        <!-- Drawer 抽屉 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Drawer</strong>
            <span>抽屉</span>
          </div>
          <div class="ep-col-standard">
            <el-button @click="drawerVisible = true">打开抽屉</el-button>
          </div>
          <div class="ep-col-yondesign">
            <el-button @click="drawerVisible = true" class="ep-rounded">打开抽屉</el-button>
          </div>
        </div>

        <!-- Message 消息提示 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Message</strong>
            <span>消息提示</span>
          </div>
          <div class="ep-col-standard">
            <el-button @click="showMessage('success')">成功</el-button>
            <el-button @click="showMessage('warning')" style="margin-left: 8px">警告</el-button>
          </div>
          <div class="ep-col-yondesign">
            <el-button @click="showMessage('success')" class="ep-rounded">成功</el-button>
            <el-button @click="showMessage('warning')" style="margin-left: 8px" class="ep-rounded">警告</el-button>
          </div>
        </div>

        <!-- MessageBox 消息确认框 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>MessageBox</strong>
            <span>消息确认框</span>
          </div>
          <div class="ep-col-standard">
            <el-button @click="showConfirm">确认框</el-button>
          </div>
          <div class="ep-col-yondesign">
            <el-button @click="showConfirm" class="ep-rounded">确认框</el-button>
          </div>
        </div>

        <!-- Notification 通知 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Notification</strong>
            <span>通知</span>
          </div>
          <div class="ep-col-standard">
            <el-button @click="showNotification('success')">通知</el-button>
          </div>
          <div class="ep-col-yondesign">
            <el-button @click="showNotification('success')" class="ep-rounded">通知</el-button>
          </div>
        </div>

        <!-- Pagination 分页 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Pagination</strong>
            <span>分页</span>
          </div>
          <div class="ep-col-standard">
            <el-pagination :current-page="1" :page-size="10" :total="100" layout="prev, pager, next" small />
            <div style="margin-top: 8px; font-size: 11px; color: #909399">当前样式</div>
          </div>
          <div class="ep-col-yondesign">
            <el-pagination :current-page="1" :page-size="10" :total="100" layout="prev, pager, next" small class="ep-rounded-pagination" />
            <div style="margin-top: 8px; font-size: 11px; color: var(--el-color-primary)">圆润圆角 + 主题色</div>
          </div>
        </div>

        <!-- Table 表格 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Table</strong>
            <span>表格</span>
          </div>
          <div class="ep-col-standard">
            <el-table :data="tableDataPreview" style="width: 250px" size="small">
              <el-table-column prop="name" label="名称" />
              <el-table-column prop="status" label="状态" />
            </el-table>
          </div>
          <div class="ep-col-yondesign">
            <el-table :data="tableDataPreview" style="width: 250px" size="small" class="ep-rounded-table">
              <el-table-column prop="name" label="名称" />
              <el-table-column prop="status" label="状态" />
            </el-table>
          </div>
        </div>

        <!-- Tabs 标签页 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Tabs</strong>
            <span>标签页</span>
          </div>
          <div class="ep-col-standard">
            <el-tabs v-model="tabValue" style="width: 200px">
              <el-tab-pane label="标签一" value="1">内容一</el-tab-pane>
              <el-tab-pane label="标签二" value="2">内容二</el-tab-pane>
            </el-tabs>
          </div>
          <div class="ep-col-yondesign">
            <el-tabs v-model="tabValue" style="width: 200px" class="ep-rounded-tabs">
              <el-tab-pane label="标签一" value="1">内容一</el-tab-pane>
              <el-tab-pane label="标签二" value="2">内容二</el-tab-pane>
            </el-tabs>
          </div>
        </div>

        <!-- Steps 步骤条 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Steps</strong>
            <span>步骤条</span>
          </div>
          <div class="ep-col-standard">
            <el-steps :active="1" style="width: 250px">
              <el-step title="步骤1" />
              <el-step title="步骤2" />
              <el-step title="步骤3" />
            </el-steps>
          </div>
          <div class="ep-col-yondesign">
            <el-steps :active="1" style="width: 250px" class="ep-rounded-steps">
              <el-step title="步骤1" />
              <el-step title="步骤2" />
              <el-step title="步骤3" />
            </el-steps>
          </div>
        </div>

        <!-- Tree 树形控件 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Tree</strong>
            <span>树形控件</span>
          </div>
          <div class="ep-col-standard">
            <el-tree :data="treeData" :props="{ label: 'label' }" style="width: 150px" />
          </div>
          <div class="ep-col-yondesign">
            <el-tree :data="treeData" :props="{ label: 'label' }" style="width: 150px" class="ep-rounded-tree" />
          </div>
        </div>

        <!-- Menu 导航菜单 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Menu</strong>
            <span>导航菜单</span>
          </div>
          <div class="ep-col-standard">
            <el-menu :default-active="'1'" mode="horizontal" style="width: 280px">
              <el-menu-item index="1">菜单1</el-menu-item>
              <el-menu-item index="2">菜单2</el-menu-item>
              <el-menu-item index="3">菜单3</el-menu-item>
            </el-menu>
          </div>
          <div class="ep-col-yondesign">
            <el-menu :default-active="'1'" mode="horizontal" style="width: 280px" class="ep-rounded-menu">
              <el-menu-item index="1">菜单1</el-menu-item>
              <el-menu-item index="2">菜单2</el-menu-item>
              <el-menu-item index="3">菜单3</el-menu-item>
            </el-menu>
          </div>
        </div>

        <!-- Dropdown 下拉菜单 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Dropdown</strong>
            <span>下拉菜单</span>
          </div>
          <div class="ep-col-standard">
            <el-dropdown>
              <el-button>下拉菜单</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item>选项1</el-dropdown-item>
                  <el-dropdown-item>选项2</el-dropdown-item>
                  <el-dropdown-item>选项3</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          <div class="ep-col-yondesign">
            <el-dropdown>
              <el-button class="ep-rounded">下拉菜单</el-button>
              <template #dropdown>
                <el-dropdown-menu class="ep-rounded-dropdown">
                  <el-dropdown-item class="ep-rounded-dropdown-item">选项1</el-dropdown-item>
                  <el-dropdown-item class="ep-rounded-dropdown-item">选项2</el-dropdown-item>
                  <el-dropdown-item class="ep-rounded-dropdown-item">选项3</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <!-- Skeleton 骨架屏 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Skeleton</strong>
            <span>骨架屏</span>
          </div>
          <div class="ep-col-standard">
            <el-skeleton :rows="2" />
          </div>
          <div class="ep-col-yondesign">
            <el-skeleton :rows="2" class="ep-rounded-skeleton" />
          </div>
        </div>

        <!-- Empty 空状态 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Empty</strong>
            <span>空状态</span>
          </div>
          <div class="ep-col-standard">
            <el-empty description="暂无数据" :image-size="50" />
          </div>
          <div class="ep-col-yondesign">
            <el-empty description="暂无数据" :image-size="50" class="ep-rounded-empty">
              <template #image>
                <div style="color: var(--el-color-primary); font-size: 48px;">
                  <svg viewBox="0 0 1024 1024" width="1em" height="1em" fill="currentColor">
                    <path d="M512 64C282.624 64 96 218.624 96 416c0 197.376 186.624 352 416 352s416-154.624 416-352C928 218.624 741.376 64 512 64zm0 128c141.376 0 256 82.624 256 192 0 109.376-114.624 192-256 192-141.376 0-256-82.624-256-192 0-109.376 114.624-192 256-192zm0 384c-70.688 0-128-57.312-128-128h256c0 70.688-57.312 128-128 128z"/>
                  </svg>
                </div>
              </template>
            </el-empty>
          </div>
        </div>

        <!-- Result 结果页 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Result</strong>
            <span>结果页</span>
          </div>
          <div class="ep-col-standard">
            <el-result
              icon="success"
              title="操作成功"
              sub-title="请查看详情"
              style="width: 280px"
            />
          </div>
          <div class="ep-col-yondesign">
            <el-result
              icon="success"
              title="操作成功"
              sub-title="请查看详情"
              style="width: 280px"
              class="ep-rounded-result"
            />
          </div>
        </div>

        <!-- Timeline 时间线 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Timeline</strong>
            <span>时间线</span>
          </div>
          <div class="ep-col-standard">
            <el-timeline style="width: 150px">
              <el-timeline-item timestamp="2024-01-01" type="primary">创建项目</el-timeline-item>
              <el-timeline-item timestamp="2024-02-01" type="success">完成设计</el-timeline-item>
            </el-timeline>
          </div>
          <div class="ep-col-yondesign">
            <el-timeline style="width: 150px" class="ep-rounded-timeline">
              <el-timeline-item timestamp="2024-01-01" type="primary">创建项目</el-timeline-item>
              <el-timeline-item timestamp="2024-02-01" type="success">完成设计</el-timeline-item>
            </el-timeline>
          </div>
        </div>

        <!-- Descriptions 描述列表 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Descriptions</strong>
            <span>描述列表</span>
          </div>
          <div class="ep-col-standard">
            <el-descriptions :column="1" size="small" border style="width: 200px">
              <el-descriptions-item label="用户名">admin</el-descriptions-item>
              <el-descriptions-item label="手机号">18100000000</el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="ep-col-yondesign">
            <el-descriptions :column="1" size="small" border style="width: 200px" class="ep-rounded-descriptions">
              <el-descriptions-item label="用户名">admin</el-descriptions-item>
              <el-descriptions-item label="手机号">18100000000</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>

        <!-- Calendar 日历 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Calendar</strong>
            <span>日历</span>
          </div>
          <div class="ep-col-standard">
            <el-calendar style="width: 280px">
              <template #date-cell="{ data }">
                <span>{{ data.day.split('-').slice(2).join('') }}</span>
              </template>
            </el-calendar>
          </div>
          <div class="ep-col-yondesign">
            <el-calendar style="width: 280px" class="ep-rounded-calendar">
              <template #date-cell="{ data }">
                <span>{{ data.day.split('-').slice(2).join('') }}</span>
              </template>
            </el-calendar>
          </div>
        </div>

        <!-- Image 图片 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Image</strong>
            <span>图片</span>
          </div>
          <div class="ep-col-standard">
            <el-image style="width: 100px; height: 60px" src="https://cube.elemecdn.com/6/94/4d3ea53c084bad6931a56d5158a48jpeg.jpeg" fit="cover" />
          </div>
          <div class="ep-col-yondesign">
            <el-image style="width: 100px; height: 60px" src="https://cube.elemecdn.com/6/94/4d3ea53c084bad6931a56d5158a48jpeg.jpeg" fit="cover" class="ep-rounded-image" />
          </div>
        </div>

        <!-- Backtop 回到顶部 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Backtop</strong>
            <span>回到顶部</span>
          </div>
          <div class="ep-col-standard">
            <span style="color: #909399; font-size: 12px">滚动查看效果</span>
          </div>
          <div class="ep-col-yondesign">
            <span style="color: var(--el-color-primary); font-size: 12px">滚动查看效果</span>
          </div>
        </div>

        <!-- InfiniteScroll 无限滚动 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>InfiniteScroll</strong>
            <span>无限滚动</span>
          </div>
          <div class="ep-col-standard">
            <span style="color: #909399; font-size: 12px">需要长列表容器</span>
          </div>
          <div class="ep-col-yondesign">
            <span style="color: var(--el-color-primary); font-size: 12px">需要长列表容器</span>
          </div>
        </div>

        <!-- Link 链接 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Link</strong>
            <span>链接</span>
          </div>
          <div class="ep-col-standard">
            <el-link type="primary">主要链接</el-link>
            <el-link type="success" style="margin-left: 12px">成功链接</el-link>
          </div>
          <div class="ep-col-yondesign">
            <el-link type="primary" class="ep-rounded-link">主要链接</el-link>
            <el-link type="success" style="margin-left: 12px" class="ep-rounded-link">成功链接</el-link>
          </div>
        </div>

        <!-- Space 间距 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Space</strong>
            <span>间距</span>
          </div>
          <div class="ep-col-standard">
            <el-space>
              <el-button>按钮1</el-button>
              <el-button type="primary">按钮2</el-button>
              <el-button type="success">按钮3</el-button>
            </el-space>
          </div>
          <div class="ep-col-yondesign">
            <el-space class="ep-rounded-space">
              <el-button class="ep-rounded">按钮1</el-button>
              <el-button type="primary" class="ep-rounded">按钮2</el-button>
              <el-button type="success" class="ep-rounded">按钮3</el-button>
            </el-space>
          </div>
        </div>

        <!-- Statistic 统计数值 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Statistic</strong>
            <span>统计数值</span>
          </div>
          <div class="ep-col-standard">
            <el-statistic title="活跃用户" :value="12689" />
          </div>
          <div class="ep-col-yondesign">
            <el-statistic title="活跃用户" :value="12689" class="ep-rounded-statistic" />
          </div>
        </div>

        <!-- Segment 段落 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Segment</strong>
            <span>段落选择</span>
          </div>
          <div class="ep-col-standard">
            <el-segmented v-model="segmentValue" :options="['选项1', '选项2', '选项3']" />
          </div>
          <div class="ep-col-yondesign">
            <el-segmented v-model="segmentValue" :options="['选项1', '选项2', '选项3']" class="ep-rounded-segment" />
          </div>
        </div>

        <!-- Watermark 水印 -->
        <div class="ep-comparison-row">
          <div class="ep-col-name">
            <strong>Watermark</strong>
            <span>水印</span>
          </div>
          <div class="ep-col-standard">
            <el-watermark content="水印文字" :height="60" style="width: 120px; height: 40px; border: 1px solid #ebeef5; display: flex; align-items: center; justify-content: center">
              <span style="font-size: 12px">内容区</span>
            </el-watermark>
          </div>
          <div class="ep-col-yondesign">
            <el-watermark content="水印文字" :height="60" style="width: 120px; height: 40px; border: 1px solid var(--el-color-primary-light-5); display: flex; align-items: center; justify-content: center; border-radius: 6px">
              <span style="font-size: 12px">内容区</span>
            </el-watermark>
          </div>
        </div>
      </div>
    </section>

    <div class="comparison-container">

      <!-- ==================== 1. DateTimePicker ==================== -->
      <section class="comparison-section">
        <h2>1. DateTimePicker 日期时间选择器</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 DateTimePicker</h3>
            <div class="component-demo">
              <DateTimePicker v-model="customDatetime" :show-time="true" placeholder="选择日期时间" size="md" />
              <p class="value-display">值: {{ customDatetime || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 日期选择</li>
                <li>[OK] 时间选择</li>
                <li>[OK] 年份下拉选择</li>
                <li>[OK] 月份下拉选择</li>
                <li>[X] 无快捷选项</li>
                <li>[X] 无范围选择</li>
                <li>[X] 无禁用日期</li>
                <li>[X] 无自定义格式</li>
              </ul>
              <p class="code-lines">代码量: ~600行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus DatePicker</h3>
            <div class="component-demo">
              <el-date-picker v-model="elementDatetime" type="datetime" placeholder="选择日期时间" format="YYYY年MM月DD日 HH:mm:ss" value-format="YYYY-MM-DD HH:mm:ss" :shortcuts="datetimeShortcuts" />
              <p class="value-display">值: {{ elementDatetime || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 日期选择</li>
                <li>[OK] 时间选择</li>
                <li>[OK] 年份选择</li>
                <li>[OK] 月份选择</li>
                <li>[OK] 快捷选项</li>
                <li>[OK] 范围选择</li>
                <li>[OK] 禁用日期</li>
                <li>[OK] 自定义格式</li>
                <li>[OK] 国际化</li>
                <li>[OK] 无障碍访问</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-date-picker
                v-model="elementDatetime"
                type="datetime"
                placeholder="选择日期时间"
                format="YYYY年MM月DD日 HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
                :shortcuts="datetimeShortcuts"
                class="ep-rounded"
              />
              <p class="value-display">值: {{ elementDatetime || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 2. AppButton ==================== -->
      <section class="comparison-section">
        <h2>2. AppButton 按钮</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppButton</h3>
            <div class="component-demo">
              <div class="btn-row">
                <AppButton variant="primary">主要</AppButton>
                <AppButton variant="secondary">次要</AppButton>
                <AppButton variant="danger">危险</AppButton>
                <AppButton variant="text">文本</AppButton>
              </div>
              <div class="btn-row">
                <AppButton variant="primary" size="sm">小</AppButton>
                <AppButton variant="primary" size="md">中</AppButton>
                <AppButton variant="primary" size="lg">大</AppButton>
              </div>
              <div class="btn-row">
                <AppButton variant="primary" :loading="true">加载中</AppButton>
                <AppButton variant="primary" :disabled="true">禁用</AppButton>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 多种变体/尺寸/加载/禁用</li>
                <li>[X] 无圆形按钮</li>
                <li>[X] 无幽灵按钮</li>
                <li>[X] 无块级按钮</li>
              </ul>
              <p class="code-lines">代码量: ~200行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Button</h3>
            <div class="component-demo">
              <div class="btn-row">
                <el-button type="primary">主要</el-button>
                <el-button>次要</el-button>
                <el-button type="danger">危险</el-button>
                <el-button type="text">文本</el-button>
              </div>
              <div class="btn-row">
                <el-button type="primary" size="small">小</el-button>
                <el-button type="primary" size="default">中</el-button>
                <el-button type="primary" size="large">大</el-button>
              </div>
              <div class="btn-row">
                <el-button type="primary" :loading="true">加载中</el-button>
                <el-button type="primary" :disabled="true">禁用</el-button>
                <el-button type="primary" round>圆形</el-button>
                <el-button type="primary" plain>幽灵</el-button>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 多种变体/尺寸/加载/禁用</li>
                <li>[OK] 圆形按钮</li>
                <li>[OK] 幽灵按钮</li>
                <li>[OK] 块级按钮</li>
                <li>[OK] 自动聚焦</li>
                <li>[OK] 图标插槽</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <div class="btn-row">
                <el-button type="primary" class="ep-rounded">主要</el-button>
                <el-button class="ep-rounded">次要</el-button>
                <el-button type="danger" class="ep-rounded">危险</el-button>
                <el-button type="text" class="ep-rounded">文本</el-button>
              </div>
              <div class="btn-row" style="margin-top: 8px">
                <el-button type="primary" size="small" class="ep-rounded">小</el-button>
                <el-button type="primary" size="default" class="ep-rounded">中</el-button>
                <el-button type="primary" size="large" class="ep-rounded">大</el-button>
              </div>
              <div class="btn-row" style="margin-top: 8px">
                <el-button type="primary" :loading="true" class="ep-rounded">加载中</el-button>
                <el-button type="primary" :disabled="true" class="ep-rounded">禁用</el-button>
                <el-button type="primary" round class="ep-rounded">圆形</el-button>
                <el-button type="primary" plain class="ep-rounded">幽灵</el-button>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 3. AppInput ==================== -->
      <section class="comparison-section">
        <h2>3. AppInput 输入框</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppInput</h3>
            <div class="component-demo">
              <AppInput v-model="customInput" placeholder="请输入内容" size="md" clearable />
              <AppInput v-model="customPassword" type="password" placeholder="密码" size="md" style="margin-top:8px" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标签/前缀/后缀/清除/密码</li>
                <li>[X] 无字数统计</li>
                <li>[X] 无文本域自动高度</li>
                <li>[X] 无复合型输入框</li>
              </ul>
              <p class="code-lines">代码量: ~300行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Input</h3>
            <div class="component-demo">
              <el-input v-model="elementInput" placeholder="请输入内容" clearable />
              <el-input v-model="elementPassword" type="password" placeholder="密码" show-password style="margin-top:8px" />
              <el-input v-model="elementInput" placeholder="复合输入" style="margin-top:8px">
                <template #prepend>Http://</template>
                <template #append>.com</template>
              </el-input>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标签/前缀/后缀/清除/密码</li>
                <li>[OK] 字数统计</li>
                <li>[OK] 文本域自动高度</li>
                <li>[OK] 复合型输入框</li>
                <li>[OK] 输入验证</li>
                <li>[OK] 尺寸配置</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-input placeholder="请输入" size="default" class="ep-rounded" style="margin-bottom: 8px" />
              <el-input v-model="customPassword" type="password" placeholder="密码" size="default" class="ep-rounded" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 4. AppSelect ==================== -->
      <section class="comparison-section">
        <h2>4. AppSelect 下拉选择</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppSelect</h3>
            <div class="component-demo">
              <AppSelect v-model="customSelect" :options="selectOptions" placeholder="请选择" />
              <p class="value-display">值: {{ customSelect || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 单选/多选/搜索/分组</li>
                <li>[X] 无远程搜索</li>
                <li>[X] 无虚拟滚动</li>
                <li>[X] 无可创建条目</li>
              </ul>
              <p class="code-lines">代码量: ~500行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Select</h3>
            <div class="component-demo">
              <el-select v-model="elementSelect" placeholder="请选择" clearable filterable>
                <el-option v-for="item in selectOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <p class="value-display">值: {{ elementSelect || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 单选/多选/搜索/分组</li>
                <li>[OK] 远程搜索</li>
                <li>[OK] 虚拟滚动</li>
                <li>[OK] 可创建条目</li>
                <li>[OK] 自定义模板</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-select v-model="elementSelect" placeholder="请选择" clearable filterable class="ep-rounded" style="width: 100%">
                <el-option v-for="item in selectOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <p class="value-display">值: {{ elementSelect || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 5. AppModal ==================== -->
      <section class="comparison-section">
        <h2>5. AppModal 对话框</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppModal</h3>
            <div class="component-demo">
              <AppButton @click="showCustomModal = true">打开对话框</AppButton>
              <AppModal v-model="showCustomModal" title="自建对话框" width="500px">
                <p>对话框内容</p>
              </AppModal>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/宽度/关闭/遮罩</li>
                <li>[X] 无拖拽</li>
                <li>[X] 无全屏</li>
                <li>[X] 无嵌套</li>
              </ul>
              <p class="code-lines">代码量: ~250行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Dialog</h3>
            <div class="component-demo">
              <el-button @click="showElementDialog = true">打开对话框</el-button>
              <el-dialog v-model="showElementDialog" title="Element Plus 对话框" width="500px" draggable>
                <p>对话框内容，支持拖拽</p>
              </el-dialog>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/宽度/关闭/遮罩</li>
                <li>[OK] 拖拽</li>
                <li>[OK] 全屏</li>
                <li>[OK] 嵌套对话框</li>
                <li>[OK] 居中布局</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-button @click="dialogYonDesign = true" class="ep-rounded">打开对话框</el-button>
              <el-dialog v-model="dialogYonDesign" title="Element Plus 对话框" width="350px" class="ep-rounded-dialog">
                <p>对话框内容，支持拖拽</p>
                <template #footer>
                  <el-button class="ep-rounded" @click="dialogYonDesign = false">取消</el-button>
                  <el-button type="primary" class="ep-rounded">确定</el-button>
                </template>
              </el-dialog>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色按钮</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 6. AppTabs ==================== -->
      <section class="comparison-section">
        <h2>6. AppTabs 标签页</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppTabs</h3>
            <div class="component-demo">
              <AppTabs v-model="customTab" :tabs="tabsOptions" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 基础标签切换</li>
                <li>[OK] 图标/徽章</li>
                <li>[X] 无卡片风格</li>
                <li>[X] 无位置配置</li>
              </ul>
              <p class="code-lines">代码量: ~400行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Tabs</h3>
            <div class="component-demo">
              <el-tabs v-model="elementTab" type="card">
                <el-tab-pane label="用户管理" name="user">用户管理内容</el-tab-pane>
                <el-tab-pane label="配置管理" name="config">配置管理内容</el-tab-pane>
                <el-tab-pane label="角色管理" name="role">角色管理内容</el-tab-pane>
              </el-tabs>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 基础标签切换</li>
                <li>[OK] 图标/徽章</li>
                <li>[OK] 卡片风格</li>
                <li>[OK] 位置配置（上下左右）</li>
                <li>[OK] 可编辑/可关闭</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-tabs v-model="elementTab" type="card" class="ep-rounded-tabs">
                <el-tab-pane label="用户管理" name="user">用户管理内容</el-tab-pane>
                <el-tab-pane label="配置管理" name="config">配置管理内容</el-tab-pane>
                <el-tab-pane label="角色管理" name="role">角色管理内容</el-tab-pane>
              </el-tabs>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 7. AppAlert ==================== -->
      <section class="comparison-section">
        <h2>7. AppAlert 警告提示</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppAlert</h3>
            <div class="component-demo">
              <AppAlert type="info">信息提示</AppAlert>
              <AppAlert type="success" style="margin-top:8px">成功提示</AppAlert>
              <AppAlert type="warning" style="margin-top:8px">警告提示</AppAlert>
              <AppAlert type="error" style="margin-top:8px">错误提示</AppAlert>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 4种类型/图标</li>
                <li>[X] 无关闭按钮</li>
                <li>[X] 无居中模式</li>
              </ul>
              <p class="code-lines">代码量: ~100行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Alert</h3>
            <div class="component-demo">
              <el-alert title="信息提示" type="info" show-icon :closable="false" />
              <el-alert title="成功提示" type="success" show-icon style="margin-top:8px" :closable="false" />
              <el-alert title="警告提示" type="warning" show-icon style="margin-top:8px" :closable="false" />
              <el-alert title="错误提示" type="error" show-icon style="margin-top:8px" :closable="false" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 4种类型/图标</li>
                <li>[OK] 关闭按钮</li>
                <li>[OK] 居中模式</li>
                <li>[OK] 描述文字</li>
                <li>[OK] 关闭动画</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-alert title="成功提示" type="success" show-icon class="ep-rounded" :closable="false" />
              <el-alert title="警告提示" type="warning" show-icon class="ep-rounded" style="margin-top: 8px" :closable="false" />
              <el-alert title="错误提示" type="error" show-icon class="ep-rounded" style="margin-top: 8px" :closable="false" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 8. AppCard ==================== -->
      <section class="comparison-section">
        <h2>8. AppCard 卡片</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppCard</h3>
            <div class="component-demo">
              <AppCard title="卡片标题" subtitle="副标题">
                <p>卡片内容</p>
              </AppCard>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/副标题/插槽</li>
                <li>[X] 无阴影配置</li>
                <li>[X] 无图片插槽</li>
              </ul>
              <p class="code-lines">代码量: ~150行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Card</h3>
            <div class="component-demo">
              <el-card shadow="hover">
                <template #header>卡片标题</template>
                <p>卡片内容</p>
              </el-card>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/插槽</li>
                <li>[OK] 阴影配置（always/hover/never）</li>
                <li>[OK] 图片插槽</li>
                <li>[OK] 身体样式自定义</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-card class="ep-rounded-card">
                <template #header>
                  <div>卡片标题</div>
                </template>
                <p>卡片内容</p>
              </el-card>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（8px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 9. AppCollapse ==================== -->
      <section class="comparison-section">
        <h2>9. AppCollapse 折叠面板</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppCollapse</h3>
            <div class="component-demo">
              <AppCollapse title="折叠面板" :expanded="true">
                <p>折叠内容</p>
              </AppCollapse>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 展开/折叠</li>
                <li>[OK] 图标/禁用</li>
                <li>[X] 无手风琴模式</li>
                <li>[X] 无多面板组合</li>
              </ul>
              <p class="code-lines">代码量: ~200行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Collapse</h3>
            <div class="component-demo">
              <el-collapse v-model="elementCollapse">
                <el-collapse-item title="折叠面板1" name="1">折叠内容1</el-collapse-item>
                <el-collapse-item title="折叠面板2" name="2">折叠内容2</el-collapse-item>
              </el-collapse>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 展开/折叠</li>
                <li>[OK] 手风琴模式</li>
                <li>[OK] 多面板组合</li>
                <li>[OK] 自定义标题</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-collapse>
                <el-collapse-item title="折叠面板1" name="1">折叠内容1</el-collapse-item>
                <el-collapse-item title="折叠面板2" name="2">折叠内容2</el-collapse-item>
              </el-collapse>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 10. AppIcon ==================== -->
      <section class="comparison-section">
        <h2>10. AppIcon 图标</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppIcon</h3>
            <div class="component-demo">
              <div class="icon-row">
                <AppIcon name="arrow-right" :size="20" />
                <AppIcon name="check" :size="20" />
                <AppIcon name="close" :size="20" />
                <AppIcon name="chevron-right" :size="20" />
                <AppIcon name="search" :size="20" />
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] ~15个基础图标</li>
                <li>[X] 图标数量少</li>
                <li>[X] 无图标集合</li>
              </ul>
              <p class="code-lines">代码量: ~100行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Icon</h3>
            <div class="component-demo">
              <div class="icon-row">
                <el-icon :size="20"><ArrowRight /></el-icon>
                <el-icon :size="20"><Check /></el-icon>
                <el-icon :size="20"><Close /></el-icon>
                <el-icon :size="20"><ArrowRight /></el-icon>
                <el-icon :size="20"><Search /></el-icon>
                <el-icon :size="20"><Edit /></el-icon>
                <el-icon :size="20"><Delete /></el-icon>
                <el-icon :size="20"><Plus /></el-icon>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 287+个图标</li>
                <li>[OK] 完整图标集合</li>
                <li>[OK] 按需引入</li>
                <li>[OK] SVG图标</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <div class="icon-row">
                <el-icon :size="20" color="var(--el-color-primary)"><ArrowRight /></el-icon>
                <el-icon :size="20" color="var(--el-color-success)"><Check /></el-icon>
                <el-icon :size="20" color="var(--el-color-danger)"><Close /></el-icon>
                <el-icon :size="20" color="var(--el-color-primary)"><Search /></el-icon>
                <el-icon :size="20" color="var(--el-color-warning)"><Edit /></el-icon>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有图标</li>
                <li>[OK] YonDesign 主题色图标</li>
                <li>[OK] 颜色统一</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 11. Pagination ==================== -->
      <section class="comparison-section">
        <h2>11. Pagination 分页</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 Pagination</h3>
            <div class="component-demo">
              <Pagination :current="customPage" :total="100" :page-size="10" @update:current="customPage = $event" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 页码/页大小/总数</li>
                <li>[X] 无快速跳转</li>
                <li>[X] 无简洁模式</li>
              </ul>
              <p class="code-lines">代码量: ~300行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Pagination</h3>
            <div class="component-demo">
              <el-pagination v-model:current-page="elementPage" v-model:page-size="elementPageSize" :total="100" layout="total, prev, pager, next, sizes, jumper" :page-sizes="[10, 20, 50, 100]" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 页码/页大小/总数</li>
                <li>[OK] 快速跳转</li>
                <li>[OK] 简洁模式</li>
                <li>[OK] 自定义布局</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-pagination v-model:current-page="elementPage" v-model:page-size="elementPageSize" :total="100" layout="total, prev, pager, next, sizes, jumper" :page-sizes="[10, 20, 50, 100]" class="ep-rounded-pagination" small />
              <p style="margin-top: 8px; font-size: 11px; color: var(--el-color-primary)">[DECORATIVE] 圆润圆角 4px + YonDesign 主题色</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（4px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 12. Drawer ==================== -->
      <section class="comparison-section">
        <h2>12. Drawer 抽屉</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 Drawer</h3>
            <div class="component-demo">
              <AppButton @click="showCustomDrawer = true">打开抽屉</AppButton>
              <Drawer v-model="showCustomDrawer" title="自建抽屉" width="400px">
                <p>抽屉内容</p>
              </Drawer>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/宽度/遮罩</li>
                <li>[X] 仅右侧方向</li>
                <li>[X] 无自定义头部</li>
              </ul>
              <p class="code-lines">代码量: ~200行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Drawer</h3>
            <div class="component-demo">
              <el-button @click="showElementDrawer = true">打开抽屉</el-button>
              <el-drawer v-model="showElementDrawer" title="Element Plus 抽屉" size="400px" direction="rtl">
                <p>抽屉内容，支持多方向</p>
              </el-drawer>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/宽度/遮罩</li>
                <li>[OK] 四个方向（上下左右）</li>
                <li>[OK] 自定义头部</li>
                <li>[OK] 嵌套抽屉</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-button @click="drawerYonDesign = true" class="ep-rounded">打开抽屉</el-button>
              <el-drawer v-model="drawerYonDesign" title="抽屉标题" size="300px" direction="rtl" class="ep-rounded-drawer">
                <p>YonDesign 风格的抽屉内容</p>
                <template #footer>
                  <el-button class="ep-rounded" @click="drawerYonDesign = false">取消</el-button>
                  <el-button type="primary" class="ep-rounded">确定</el-button>
                </template>
              </el-drawer>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色按钮</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 13. AppSideNav ==================== -->
      <section class="comparison-section">
        <h2>13. AppSideNav 侧边导航</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppSideNav</h3>
            <div class="component-demo">
              <div style="height:200px;overflow:hidden">
                <AppSideNav v-model="customNav" :items="navItems" :collapsible="true" />
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 导航项/折叠/徽章</li>
                <li>[X] 无子菜单</li>
                <li>[X] 无分组</li>
              </ul>
              <p class="code-lines">代码量: ~300行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Menu</h3>
            <div class="component-demo">
              <div style="height:200px;overflow:hidden">
                <el-menu default-active="1" :collapse="true">
                  <el-menu-item index="1">首页</el-menu-item>
                  <el-menu-item index="2">用户</el-menu-item>
                  <el-sub-menu index="3">
                    <template #title>系统</template>
                    <el-menu-item index="3-1">日志</el-menu-item>
                    <el-menu-item index="3-2">权限</el-menu-item>
                  </el-sub-menu>
                </el-menu>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 导航项/折叠</li>
                <li>[OK] 子菜单</li>
                <li>[OK] 分组</li>
                <li>[OK] 水平/垂直模式</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <div style="height:150px;overflow:hidden">
                <el-menu default-active="1" :collapse="true" class="ep-rounded-menu">
                  <el-menu-item index="1">首页</el-menu-item>
                  <el-menu-item index="2">用户</el-menu-item>
                  <el-menu-item index="3">设置</el-menu-item>
                </el-menu>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 14. EmptyState ==================== -->
      <section class="comparison-section">
        <h2>14. EmptyState 空状态</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 EmptyState</h3>
            <div class="component-demo">
              <EmptyState type="box" title="暂无数据" description="请先添加数据" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 5种图标类型</li>
                <li>[OK] 标题/描述</li>
                <li>[X] 无自定义图片</li>
              </ul>
              <p class="code-lines">代码量: ~100行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Empty</h3>
            <div class="component-demo">
              <el-empty description="暂无数据" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 自定义图片</li>
                <li>[OK] 描述文字</li>
                <li>[OK] 底部插槽</li>
                <li>[OK] 图片大小配置</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-empty description="暂无数据" class="ep-rounded-empty" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（8px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 15. ConfirmDialog ==================== -->
      <section class="comparison-section">
        <h2>15. ConfirmDialog 确认对话框</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 ConfirmDialog</h3>
            <div class="component-demo">
              <AppButton @click="showCustomConfirm = true">确认删除</AppButton>
              <ConfirmDialog v-model="showCustomConfirm" title="确认" message="确定要删除吗？" type="danger" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 确认/取消</li>
                <li>[OK] 类型图标</li>
                <li>[X] 无输入框模式</li>
                <li>[X] 无命令式调用</li>
              </ul>
              <p class="code-lines">代码量: ~150行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus MessageBox</h3>
            <div class="component-demo">
              <el-button @click="openElMessageBox">确认删除</el-button>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 确认/取消</li>
                <li>[OK] 类型图标</li>
                <li>[OK] 输入框模式</li>
                <li>[OK] 命令式调用</li>
                <li>[OK] 自定义按钮文字</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-button @click="openElMessageBox" class="ep-rounded">确认删除</el-button>
              <!-- EP+YonDesign Dialog 预览 -->
              <el-dialog
                v-model="dialogYonDesign"
                title="确认操作"
                width="300px"
                class="ep-rounded-dialog"
              >
                <p style="text-align:center">确定要删除此项吗？</p>
                <template #footer>
                  <el-button class="ep-rounded" @click="dialogYonDesign = false">取消</el-button>
                  <el-button type="primary" class="ep-rounded">确定</el-button>
                </template>
              </el-dialog>
              <el-button @click="dialogYonDesign = true" size="small" class="ep-rounded" style="margin-left:8px">预览弹窗</el-button>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP MessageBox 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色按钮</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 16. EnumSelect ==================== -->
      <section class="comparison-section">
        <h2>16. EnumSelect 枚举选择</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 EnumSelect</h3>
            <div class="component-demo">
              <EnumSelect v-model="customEnum" :options="enumOptions" placeholder="选择状态" />
              <p class="value-display">值: {{ customEnum || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 枚举选择/颜色标签</li>
                <li>[X] 无搜索</li>
                <li>[X] 无分组</li>
              </ul>
              <p class="code-lines">代码量: ~200行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Select（自定义模板）</h3>
            <div class="component-demo">
              <el-select v-model="elementEnum" placeholder="选择状态" clearable>
                <el-option v-for="item in enumOptions" :key="item.value" :label="item.label" :value="item.value">
                  <span :style="{color: item.color}">●</span> {{ item.label }}
                </el-option>
              </el-select>
              <p class="value-display">值: {{ elementEnum || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 枚举选择/颜色标签</li>
                <li>[OK] 搜索</li>
                <li>[OK] 分组</li>
                <li>[OK] 自定义模板</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-select v-model="elementEnum" placeholder="选择状态" clearable class="ep-rounded" style="width: 100%">
                <el-option v-for="item in enumOptions" :key="item.value" :label="item.label" :value="item.value">
                  <span :style="{color: item.color}">●</span> {{ item.label }}
                </el-option>
              </el-select>
              <p class="value-display">值: {{ elementEnum || '未选择' }}</p>
              <p style="margin-top: 8px; font-size: 11px; color: var(--el-color-primary)">[DECORATIVE] 圆润圆角 6px + YonDesign 主题色</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 17. EnumSearchHelp ==================== -->
      <section class="comparison-section">
        <h2>17. EnumSearchHelp 枚举搜索帮助</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 EnumSearchHelp</h3>
            <div class="component-demo">
              <EnumSearchHelp v-model="customSearchHelp" :options="searchHelpOptions" title="选择项目" />
              <p class="value-display">值: {{ customSearchHelp || '未选择' }}</p>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 搜索帮助弹窗</li>
                <li>[OK] 过滤搜索</li>
                <li>[X] 无分页</li>
                <li>[X] 无多选</li>
              </ul>
              <p class="code-lines">代码量: ~250行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Dialog + Table</h3>
            <div class="component-demo">
              <el-button @click="showSearchHelpDialog = true">搜索帮助</el-button>
              <el-dialog v-model="showSearchHelpDialog" title="选择项目" width="500px">
                <el-input v-model="searchHelpFilter" placeholder="搜索..." prefix-icon="Search" style="margin-bottom:12px" />
                <el-table :data="filteredSearchHelp" highlight-current-row @current-change="handleSearchHelpSelect" max-height="300">
                  <el-table-column prop="label" label="名称" />
                  <el-table-column prop="value" label="编码" />
                </el-table>
              </el-dialog>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 搜索帮助弹窗</li>
                <li>[OK] 过滤搜索</li>
                <li>[OK] 分页</li>
                <li>[OK] 多选</li>
                <li>[OK] 表格排序</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-button @click="showSearchHelpDialog = true" class="ep-rounded">搜索帮助</el-button>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP Dialog+Table 组合</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色按钮</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 18. FilterBar ==================== -->
      <section class="comparison-section">
        <h2>18. FilterBar 过滤器栏</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 FilterBar</h3>
            <div class="component-demo">
              <FilterBar :fields="filterFields" @search="handleFilterSearch" @reset="handleFilterReset" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 多种字段类型</li>
                <li>[OK] 日期时间范围</li>
                <li>[OK] 搜索/重置</li>
                <li>[X] 无折叠展开</li>
              </ul>
              <p class="code-lines">代码量: ~400行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Form 组合</h3>
            <div class="component-demo">
              <el-form :inline="true" :model="elementFilterForm">
                <el-form-item label="操作类型">
                  <el-select v-model="elementFilterForm.type" placeholder="全部" clearable>
                    <el-option label="创建" value="create" />
                    <el-option label="更新" value="update" />
                    <el-option label="删除" value="delete" />
                  </el-select>
                </el-form-item>
                <el-form-item label="时间范围">
                  <el-date-picker v-model="elementFilterForm.dateRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary">查询</el-button>
                  <el-button>重置</el-button>
                </el-form-item>
              </el-form>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 多种字段类型</li>
                <li>[OK] 日期时间范围</li>
                <li>[OK] 搜索/重置</li>
                <li>[OK] 折叠展开</li>
                <li>[OK] 表单验证</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-form :inline="true" :model="elementFilterForm">
                <el-form-item label="操作类型">
                  <el-select v-model="elementFilterForm.type" placeholder="全部" clearable class="ep-rounded">
                    <el-option label="创建" value="create" />
                    <el-option label="更新" value="update" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" class="ep-rounded">查询</el-button>
                  <el-button class="ep-rounded">重置</el-button>
                </el-form-item>
              </el-form>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 19. MetaTable ==================== -->
      <section class="comparison-section">
        <h2>19. MetaTable 元数据表格</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 MetaTable</h3>
            <div class="component-demo">
              <MetaTable :columns="metaTableColumns" :data="metaTableData" :show-header="true" search-placeholder="搜索..." />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 列定义/数据/搜索</li>
                <li>[X] 无排序</li>
                <li>[X] 无筛选</li>
                <li>[X] 无固定列</li>
                <li>[X] 无虚拟滚动</li>
              </ul>
              <p class="code-lines">代码量: ~500行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Table</h3>
            <div class="component-demo">
              <el-table :data="metaTableData" stripe border style="width:100%">
                <el-table-column prop="name" label="名称" sortable />
                <el-table-column prop="status" label="状态" />
                <el-table-column prop="date" label="日期" sortable />
              </el-table>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 列定义/数据</li>
                <li>[OK] 排序</li>
                <li>[OK] 筛选</li>
                <li>[OK] 固定列</li>
                <li>[OK] 虚拟滚动</li>
                <li>[OK] 树形数据</li>
                <li>[OK] 可编辑单元格</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-table :data="metaTableData" style="width: 100%" size="small" class="ep-rounded-table">
                <el-table-column prop="name" label="名称" />
                <el-table-column prop="type" label="类型" />
              </el-table>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 20. MetaForm ==================== -->
      <section class="comparison-section">
        <h2>20. MetaForm 元数据表单</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 MetaForm</h3>
            <div class="component-demo">
              <MetaForm :fields="metaFormFields" :model-value="metaFormData" layout="horizontal" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 元数据驱动表单</li>
                <li>[OK] 多种字段类型</li>
                <li>[X] 无验证规则</li>
                <li>[X] 无动态表单</li>
              </ul>
              <p class="code-lines">代码量: ~400行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Form</h3>
            <div class="component-demo">
              <el-form :model="elementForm" label-width="80px" :rules="elementFormRules" ref="formRef">
                <el-form-item label="名称" prop="name">
                  <el-input v-model="elementForm.name" />
                </el-form-item>
                <el-form-item label="类型" prop="type">
                  <el-select v-model="elementForm.type">
                    <el-option label="类型A" value="a" />
                    <el-option label="类型B" value="b" />
                  </el-select>
                </el-form-item>
              </el-form>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 元数据驱动表单</li>
                <li>[OK] 多种字段类型</li>
                <li>[OK] 验证规则</li>
                <li>[OK] 动态表单</li>
                <li>[OK] 自定义验证</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-form :model="elementForm" label-width="80px" class="ep-rounded-form">
                <el-form-item label="名称">
                  <el-input v-model="elementForm.name" class="ep-rounded" />
                </el-form-item>
                <el-form-item label="类型">
                  <el-select v-model="elementForm.type" class="ep-rounded" style="width: 100%">
                    <el-option label="类型A" value="a" />
                    <el-option label="类型B" value="b" />
                  </el-select>
                </el-form-item>
              </el-form>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 21. MetaDialog ==================== -->
      <section class="comparison-section">
        <h2>21. MetaDialog 元数据对话框</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 MetaDialog</h3>
            <div class="component-demo">
              <AppButton @click="showCustomMetaDialog = true">打开元数据对话框</AppButton>
              <MetaDialog v-model="showCustomMetaDialog" title="新建对象" :fields="metaFormFields" :model-value="metaFormData" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] Dialog+Form组合</li>
                <li>[OK] 保存/取消</li>
                <li>[X] 无验证</li>
              </ul>
              <p class="code-lines">代码量: ~300行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Dialog+Form</h3>
            <div class="component-demo">
              <el-button @click="showElementMetaDialog = true">打开元数据对话框</el-button>
              <el-dialog v-model="showElementMetaDialog" title="新建对象" width="500px">
                <el-form :model="elementForm" label-width="80px" :rules="elementFormRules">
                  <el-form-item label="名称" prop="name"><el-input v-model="elementForm.name" /></el-form-item>
                  <el-form-item label="类型" prop="type"><el-select v-model="elementForm.type"><el-option label="类型A" value="a" /><el-option label="类型B" value="b" /></el-select></el-form-item>
                </el-form>
                <template #footer>
                  <el-button @click="showElementMetaDialog = false">取消</el-button>
                  <el-button type="primary">保存</el-button>
                </template>
              </el-dialog>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] Dialog+Form组合</li>
                <li>[OK] 保存/取消</li>
                <li>[OK] 验证规则</li>
                <li>[OK] 拖拽/全屏</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-button @click="dialogYonDesign = true" class="ep-rounded">打开对话框</el-button>
              <!-- EP+YonDesign Dialog 预览 -->
              <el-dialog
                v-model="dialogYonDesign"
                title="新建对象"
                width="400px"
                class="ep-rounded-dialog"
              >
                <el-form label-width="80px">
                  <el-form-item label="名称">
                    <el-input class="ep-rounded" placeholder="请输入名称" />
                  </el-form-item>
                  <el-form-item label="类型">
                    <el-select class="ep-rounded" placeholder="请选择类型" style="width: 100%">
                      <el-option label="类型A" value="a" />
                      <el-option label="类型B" value="b" />
                    </el-select>
                  </el-form-item>
                </el-form>
                <template #footer>
                  <el-button class="ep-rounded" @click="dialogYonDesign = false">取消</el-button>
                  <el-button type="primary" class="ep-rounded">保存</el-button>
                </template>
              </el-dialog>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP Dialog+Form 组合</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色按钮</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 22. AppHeader ==================== -->
      <section class="comparison-section">
        <h2>22. AppHeader 页面头部</h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AppHeader</h3>
            <div class="component-demo">
              <AppHeader title="页面标题" :show-back="true" back-text="返回" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/返回/插槽</li>
                <li>[X] 无面包屑</li>
              </ul>
              <p class="code-lines">代码量: ~100行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus PageHeader</h3>
            <div class="component-demo">
              <el-page-header @back="() => {}" content="页面标题" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 标题/返回</li>
                <li>[OK] 面包屑</li>
                <li>[OK] 自定义内容</li>
                <li>[OK] 图标插槽</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-page-header @back="() => {}" content="页面标题" class="ep-rounded" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP PageHeader 所有功能</li>
                <li>[OK] 圆润圆角（6px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 0行</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 23. AuditLog ==================== -->
      <section class="comparison-section">
        <h2>23. AuditLog 审计日志 <span class="badge-business">业务组件</span></h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 AuditLog</h3>
            <div class="component-demo">
              <AuditLog :logs="auditLogs" />
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 日志列表/时间线</li>
                <li>[OK] 字段变更展示</li>
                <li>[WARNING] 业务组件，无直接替代</li>
              </ul>
              <p class="code-lines">代码量: ~400行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Timeline 组合</h3>
            <div class="component-demo">
              <el-timeline>
                <el-timeline-item v-for="log in auditLogs" :key="log.id" :timestamp="log.created_at" placement="top">
                  <el-card>
                    <p>{{ log.user_name }} {{ log.action }} {{ log.field_name }}</p>
                  </el-card>
                </el-timeline-item>
              </el-timeline>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 时间线组件</li>
                <li>[OK] 自定义节点</li>
                <li>[WARNING] 需要组合Timeline+Card</li>
              </ul>
              <p class="code-lines">代码量: 少量模板代码</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-timeline class="ep-rounded-timeline">
                <el-timeline-item v-for="log in auditLogs" :key="log.id" :timestamp="log.created_at" placement="top">
                  <el-card class="ep-rounded-card" style="font-size: 12px">
                    <p>{{ log.user_name }} {{ log.action }}</p>
                  </el-card>
                </el-timeline-item>
              </el-timeline>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP Timeline+Card 组合</li>
                <li>[OK] 圆润圆角（6px/8px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 少量模板代码</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 24. MasterDetailLayout ==================== -->
      <section class="comparison-section">
        <h2>24. MasterDetailLayout 主从布局 <span class="badge-business">布局组件</span></h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 MasterDetailLayout</h3>
            <div class="component-demo">
              <div style="height:150px;border:1px dashed var(--color-border);border-radius:6px;overflow:hidden">
                <MasterDetailLayout :sidebar-width="200" sidebar-collapsible>
                  <template #master><div style="padding:12px">主列表</div></template>
                  <template #detail><div style="padding:12px">详情内容</div></template>
                </MasterDetailLayout>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 主从布局/折叠</li>
                <li>[WARNING] 布局组件，无直接替代</li>
              </ul>
              <p class="code-lines">代码量: ~300行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus Container 组合</h3>
            <div class="component-demo">
              <el-container style="height:150px;border:1px solid var(--el-border-color);border-radius:6px">
                <el-aside width="200px">主列表</el-aside>
                <el-main>详情内容</el-main>
              </el-container>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 容器布局</li>
                <li>[OK] 侧边栏/头部/主体</li>
                <li>[WARNING] 需要组合Container+Aside</li>
              </ul>
              <p class="code-lines">代码量: 少量模板代码</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <el-container style="height:150px;border:1px solid var(--el-border-color);border-radius:8px" class="ep-rounded-container">
                <el-aside width="200px" style="border-right: 1px solid var(--el-border-color)">主列表</el-aside>
                <el-main>详情内容</el-main>
              </el-container>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP Container 组合</li>
                <li>[OK] 圆润圆角（8px）</li>
                <li>[OK] YonDesign 主题色边框</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 少量模板代码</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ==================== 25. ObjectPage ==================== -->
      <section class="comparison-section">
        <h2>25. ObjectPage 对象页面 <span class="badge-business">业务组件</span></h2>
        <div class="comparison-grid">
          <div class="comparison-item">
            <h3>自建组件 ObjectPage</h3>
            <div class="component-demo">
              <div style="height:200px;border:1px dashed var(--color-border);border-radius:6px;overflow:hidden">
                <ObjectPage title="产品详情" status="已发布" status-type="success" :breadcrumbs="[{label:'首页'},{label:'产品'}]">
                  <template #default><div style="padding:16px">对象页面内容区域</div></template>
                </ObjectPage>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] 面包屑/标题/状态</li>
                <li>[OK] 操作按钮/标签页</li>
                <li>[WARNING] 业务组件，无直接替代</li>
              </ul>
              <p class="code-lines">代码量: ~400行</p>
            </div>
          </div>
          <div class="comparison-item">
            <h3>Element Plus 组合实现</h3>
            <div class="component-demo">
              <div style="height:200px;border:1px solid var(--el-border-color);border-radius:6px;overflow:hidden">
                <el-breadcrumb separator="/"><el-breadcrumb-item>首页</el-breadcrumb-item><el-breadcrumb-item>产品</el-breadcrumb-item></el-breadcrumb>
                <div style="padding:12px 16px;display:flex;align-items:center;gap:8px">
                  <h3 style="margin:0">产品详情</h3>
                  <el-tag type="success">已发布</el-tag>
                </div>
                <el-tabs style="padding:0 16px"><el-tab-pane label="基本信息">对象页面内容区域</el-tab-pane></el-tabs>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] Breadcrumb+Tag+Tabs</li>
                <li>[OK] 所有子组件成熟</li>
                <li>[WARNING] 需要组合多个组件</li>
              </ul>
              <p class="code-lines">代码量: 少量模板代码</p>
            </div>
          </div>
          <div class="comparison-item ep-yondesign-item">
            <h3>Element Plus + YonDesign</h3>
            <div class="component-demo">
              <div style="height:120px;border:1px solid var(--el-border-color);border-radius:8px;overflow:hidden">
                <div style="padding:12px 16px;border-bottom:1px solid var(--el-border-color);display:flex;align-items:center;justify-content:space-between">
                  <div style="display:flex;align-items:center;gap:8px">
                    <el-breadcrumb :separator-icon="ArrowRight">
                      <el-breadcrumb-item>首页</el-breadcrumb-item>
                      <el-breadcrumb-item>产品</el-breadcrumb-item>
                    </el-breadcrumb>
                  </div>
                  <el-tag type="success" class="ep-rounded-tag">已发布</el-tag>
                </div>
                <el-tabs style="padding:0 16px" class="ep-rounded-tabs"><el-tab-pane label="基本信息">内容</el-tab-pane></el-tabs>
              </div>
            </div>
            <div class="component-info">
              <ul>
                <li>[OK] EP 组合所有组件</li>
                <li>[OK] 圆润圆角（6px/8px）</li>
                <li>[OK] YonDesign 主题色</li>
                <li>[OK] 整体风格统一</li>
              </ul>
              <p class="code-lines">代码量: 少量模板代码</p>
            </div>
          </div>
        </div>
      </section>

    </div>

    <!-- ==================== Element Plus 有但我们没有 ==================== -->
    <div class="missing-section">
      <h2>[DECORATIVE] Element Plus 有但我们没有的组件（51个）</h2>
      <p class="section-desc">以下组件是 Element Plus 提供但我们项目目前完全没有的，引入后可免费获得（基于 Element Plus 2.14 完整组件列表）</p>

      <div class="missing-grid">
        <div class="missing-category">
          <h3>[DECORATIVE] 表单类（17个）</h3>
          <div class="missing-items">
            <div class="missing-item" v-for="c in missingForm" :key="c.name">
              <div class="missing-item-header">
                <span class="missing-name">{{ c.name }}</span>
                <span class="missing-tag">{{ c.tag }}</span>
                <span v-if="c.new" class="missing-tag-new">NEW</span>
              </div>
              <p class="missing-desc">{{ c.desc }}</p>
              <div class="missing-demo">
                <span class="demo-placeholder">{{ c.demoText }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="missing-category">
          <h3>[DECORATIVE] 数据展示类（19个）</h3>
          <div class="missing-items">
            <div class="missing-item" v-for="c in missingData" :key="c.name">
              <div class="missing-item-header">
                <span class="missing-name">{{ c.name }}</span>
                <span class="missing-tag">{{ c.tag }}</span>
                <span v-if="c.new" class="missing-tag-new">NEW</span>
              </div>
              <p class="missing-desc">{{ c.desc }}</p>
              <div class="missing-demo">
                <span class="demo-placeholder">{{ c.demoText }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="missing-category">
          <h3>[SYMBOL] 导航类（6个）</h3>
          <div class="missing-items">
            <div class="missing-item" v-for="c in missingNav" :key="c.name">
              <div class="missing-item-header">
                <span class="missing-name">{{ c.name }}</span>
                <span class="missing-tag">{{ c.tag }}</span>
                <span v-if="c.new" class="missing-tag-new">NEW</span>
              </div>
              <p class="missing-desc">{{ c.desc }}</p>
              <div class="missing-demo">
                <span class="demo-placeholder">{{ c.demoText }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="missing-category">
          <h3>[SYMBOL] 反馈类（6个）</h3>
          <div class="missing-items">
            <div class="missing-item" v-for="c in missingFeedback" :key="c.name">
              <div class="missing-item-header">
                <span class="missing-name">{{ c.name }}</span>
                <span class="missing-tag">{{ c.tag }}</span>
                <span v-if="c.new" class="missing-tag-new">NEW</span>
              </div>
              <p class="missing-desc">{{ c.desc }}</p>
              <div class="missing-demo">
                <span class="demo-placeholder">{{ c.demoText }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="missing-category">
          <h3>[SYMBOL] 基础/其他类（3个）</h3>
          <div class="missing-items">
            <div class="missing-item" v-for="c in missingOther" :key="c.name">
              <div class="missing-item-header">
                <span class="missing-name">{{ c.name }}</span>
                <span class="missing-tag">{{ c.tag }}</span>
                <span v-if="c.new" class="missing-tag-new">NEW</span>
              </div>
              <p class="missing-desc">{{ c.desc }}</p>
              <div class="missing-demo">
                <span class="demo-placeholder">{{ c.demoText }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== 总结 ==================== -->
    <div class="summary-section">
      <h2>[DECORATIVE] 全量总结对比</h2>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>#</th>
            <th>组件</th>
            <th>自建代码量</th>
            <th>EP对应组件</th>
            <th>功能对比</th>
            <th>迁移难度</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in summaryData" :key="idx">
            <td>{{ idx + 1 }}</td>
            <td>{{ row.name }}</td>
            <td>{{ row.lines }}</td>
            <td>{{ row.epComponent }}</td>
            <td :class="row.level === 'superior' ? 'text-green' : row.level === 'equal' ? 'text-yellow' : 'text-red'">{{ row.compare }}</td>
            <td>{{ row.difficulty }}</td>
          </tr>
          <tr class="total-row">
            <td></td>
            <td><strong>合计</strong></td>
            <td><strong>~6,050行</strong></td>
            <td>-</td>
            <td class="text-green"><strong>EP全面超越</strong></td>
            <td>-</td>
          </tr>
        </tbody>
      </table>
    </div>
    </div>

    <!-- ==================== 页面组件模式 Tab ==================== -->
    <div v-show="activeTab === 'page'" class="tab-content">
      <section class="page-patterns-section">
        <h2>页面组件模式研究</h2>
        <p class="preview-intro">
          基于 <code>docs/architecture/03-page-patterns.md</code> 的研究成果，
          提供<strong>实际可交互的组件演示</strong>。
        </p>

        <!-- 实际组件演示一：树形-列表-详情 -->
        <div class="pattern-group">
          <h3>场景一：产品与版本管理（Tree-Master-Detail 模式）</h3>
          <div class="live-demo-container">
            <div class="demo-layout">
              <!-- 左侧：树形导航 -->
              <div class="demo-tree-panel">
                <div class="panel-header">
                  <span>产品列表</span>
                  <AppButton variant="text" size="small" @click="showProductDialog = true">
                    <AppIcon name="plus" :size="14" />
                  </AppButton>
                </div>
                <div class="panel-content scrollable">
                  <div
                    v-for="product in demoProducts"
                    :key="product.id"
                    class="tree-node"
                    :class="{ active: selectedProduct?.id === product.id }"
                    @click="selectedProduct = product; selectedVersion = null"
                  >
                    <AppIcon name="folder" />
                    <span class="tree-node-name">{{ product.name }}</span>
                    <div class="tree-node-actions" @click.stop>
                      <AppButton variant="text" size="small" @click.stop="editProduct(product)">
                        <AppIcon name="edit" :size="12" />
                      </AppButton>
                      <AppButton variant="text" size="small" @click.stop="deleteProduct(product)">
                        <AppIcon name="delete" :size="12" />
                      </AppButton>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 中间：版本列表 -->
              <div class="demo-master-panel">
                <div class="panel-header">
                  <span>版本列表</span>
                  <AppButton variant="text" size="small" @click="showVersionDialog = true">
                    <AppIcon name="plus" :size="14" />
                  </AppButton>
                </div>
                <div class="panel-content scrollable">
                  <div v-if="!selectedProduct" class="empty-state">
                    <el-empty description="请选择产品" :image-size="60" />
                  </div>
                  <div v-else-if="selectedProduct.versions.length === 0" class="empty-state">
                    <el-empty description="暂无版本" :image-size="60" />
                  </div>
                  <table v-else class="demo-table">
                    <thead>
                      <tr>
                        <th>版本号</th>
                        <th>状态</th>
                        <th>创建时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="version in selectedProduct.versions"
                        :key="version.id"
                        :class="{ active: selectedVersion?.id === version.id }"
                        @click="selectedVersion = version"
                      >
                        <td>{{ version.name }}</td>
                        <td>
                          <el-tag size="small" :type="version.status === 'active' ? 'success' : 'info'">
                            {{ version.status === 'active' ? '活跃' : '停用' }}
                          </el-tag>
                        </td>
                        <td>{{ version.created }}</td>
                        <td>
                          <AppButton variant="text" size="small" @click.stop="editVersion(version)">
                            <AppIcon name="edit" :size="12" />
                          </AppButton>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- 右侧：版本详情 -->
              <div class="demo-detail-panel">
                <div class="panel-header">版本详情</div>
                <div class="panel-content" v-if="selectedVersion">
                  <div class="detail-row">
                    <span class="detail-label">版本号：</span>
                    <span class="detail-value">{{ selectedVersion.name }}</span>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">产品：</span>
                    <span class="detail-value">{{ selectedProduct?.name }}</span>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">状态：</span>
                    <el-tag size="small" :type="selectedVersion.status === 'active' ? 'success' : 'info'">
                      {{ selectedVersion.status === 'active' ? '活跃' : '停用' }}
                    </el-tag>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">创建时间：</span>
                    <span class="detail-value">{{ selectedVersion.created }}</span>
                  </div>
                  <div class="detail-actions">
                    <AppButton size="small" variant="primary" @click="editVersion(selectedVersion)">编辑</AppButton>
                    <AppButton size="small" variant="danger" @click="deleteVersion(selectedVersion)">删除</AppButton>
                  </div>
                </div>
                <div class="panel-content empty" v-else-if="selectedProduct">
                  <el-empty description="请选择版本查看详情" :image-size="60" />
                </div>
                <div class="panel-content empty" v-else>
                  <el-empty description="请选择产品和版本" :image-size="60" />
                </div>
              </div>
            </div>
          </div>

          <!-- 产品编辑弹窗 -->
          <AppModal
            v-model="showProductDialog"
            :title="editingProduct?.id ? '编辑产品' : '新建产品'"
            width="400px"
          >
            <el-form label-width="80px" :model="productForm">
              <el-form-item label="产品名称">
                <el-input v-model="productForm.name" placeholder="请输入产品名称" />
              </el-form-item>
              <el-form-item label="产品编码">
                <el-input v-model="productForm.code" placeholder="请输入产品编码" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="productForm.description" type="textarea" rows="3" placeholder="请输入描述" />
              </el-form-item>
            </el-form>
            <template #footer>
              <AppButton variant="secondary" @click="showProductDialog = false">取消</AppButton>
              <AppButton variant="primary" @click="saveProduct">确定</AppButton>
            </template>
          </AppModal>

          <!-- 版本编辑弹窗 -->
          <AppModal
            v-model="showVersionDialog"
            :title="editingVersion?.id ? '编辑版本' : '新建版本'"
            width="400px"
          >
            <el-form label-width="80px" :model="versionForm">
              <el-form-item label="版本号">
                <el-input v-model="versionForm.name" placeholder="如 V1.0" />
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="versionForm.status" style="width: 100%">
                  <el-option label="活跃" value="active" />
                  <el-option label="停用" value="inactive" />
                </el-select>
              </el-form-item>
              <el-form-item label="创建时间">
                <el-date-picker
                  v-model="versionForm.created"
                  type="date"
                  placeholder="选择日期"
                  style="width: 100%"
                />
              </el-form-item>
            </el-form>
            <template #footer>
              <AppButton variant="secondary" @click="showVersionDialog = false">取消</AppButton>
              <AppButton variant="primary" @click="saveVersion">确定</AppButton>
            </template>
          </AppModal>

          <div class="pattern-note">
            <AppIcon name="info-filled" />
            <span><strong>组件设计：</strong>MetaTreePage - 树形导航 + 列表 + 详情 + CRUD，YAML 驱动，自动处理父子关系</span>
          </div>
        </div>

        <!-- 实际组件演示二：关联关系 -->
        <div class="pattern-group">
          <h3>场景二：用户组-角色关联（Association Manager 模式）</h3>
          <div class="live-demo-container">
            <div class="demo-association">
              <!-- 左侧：已选角色 -->
              <div class="association-panel">
                <div class="panel-header">已选角色 ({{ selectedRoles.length }})</div>
                <div class="panel-content">
                  <div v-if="selectedRoles.length === 0" class="empty-hint">
                    暂未分配角色
                  </div>
                  <div
                    v-for="role in selectedRoles"
                    :key="role.id"
                    class="association-item"
                  >
                    <div class="association-info">
                      <span class="association-name">{{ role.name }}</span>
                      <span class="association-code">{{ role.code }}</span>
                    </div>
                    <AppButton variant="text" size="small" @click="removeRole(role)">
                      <AppIcon name="delete" :size="14" />
                    </AppButton>
                  </div>
                </div>
              </div>

              <!-- 中间：操作按钮 -->
              <div class="association-actions">
                <AppButton variant="primary" @click="showRoleDialog = true">
                  <AppIcon name="plus" :size="14" />
                  添加角色
                </AppButton>
              </div>

              <!-- 右侧：可选项 -->
              <div class="association-panel available">
                <div class="panel-header">可添加角色</div>
                <div class="panel-content">
                  <div
                    v-for="role in availableRoles"
                    :key="role.id"
                    class="association-item"
                  >
                    <el-checkbox
                      :value="selectedRoleIds.includes(role.id)"
                      @change="toggleRole(role, $event)"
                    />
                    <div class="association-info">
                      <span class="association-name">{{ role.name }}</span>
                      <span class="association-code">{{ role.code }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 弹窗演示 -->
            <AppModal
              v-model="showRoleDialog"
              title="添加角色"
              width="500px"
            >
              <div class="role-dialog-content">
                <el-input
                  v-model="roleSearchQuery"
                  placeholder="搜索角色..."
                  clearable
                  style="margin-bottom: 16px"
                />
                <div class="role-list">
                  <div
                    v-for="role in filteredAllRoles"
                    :key="role.id"
                    class="role-dialog-item"
                    :class="{ selected: selectedRoleIds.includes(role.id) }"
                    @click="toggleRole(role, !selectedRoleIds.includes(role.id))"
                  >
                    <el-checkbox
                      :value="selectedRoleIds.includes(role.id)"
                    />
                    <div class="association-info">
                      <span class="association-name">{{ role.name }}</span>
                      <span class="association-code">{{ role.code }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <template #footer>
                <AppButton variant="secondary" @click="showRoleDialog = false">取消</AppButton>
                <AppButton variant="primary" @click="saveRoles">确认添加</AppButton>
              </template>
            </AppModal>
          </div>
          <div class="pattern-note">
            <AppIcon name="info-filled" />
            <span><strong>组件设计：</strong>AssociationManager - 支持 Transfer/Table/Panel 三种显示模式，YAML 驱动</span>
          </div>
        </div>

        <!-- 组件分层架构（简化版） -->
        <div class="pattern-group">
          <h3>组件分层架构</h3>
          <div class="layer-demo">
            <div class="layer-row layer-page">
              <div class="layer-label">页面组件层</div>
              <div class="layer-components">
                <el-tag type="danger" size="large">MetaListPage</el-tag>
                <el-tag type="danger" size="large">MetaTreePage</el-tag>
                <el-tag type="danger" size="large">MetaDetailPage</el-tag>
              </div>
              <div class="layer-desc">YAML 驱动，面向业务对象</div>
            </div>
            <div class="layer-row layer-business">
              <div class="layer-label">业务组件层</div>
              <div class="layer-components">
                <el-tag type="warning" size="large">MetaTable</el-tag>
                <el-tag type="warning" size="large">MetaForm</el-tag>
                <el-tag type="warning" size="large">AssociationManager</el-tag>
              </div>
              <div class="layer-desc">封装业务逻辑</div>
            </div>
            <div class="layer-row layer-base">
              <div class="layer-label">基础组件层</div>
              <div class="layer-components">
                <el-tag type="" size="large">AppButton</el-tag>
                <el-tag type="" size="large">AppModal</el-tag>
                <el-tag type="" size="large">AppInput</el-tag>
                <span class="more-tags">+ 11个 YonDesign 组件</span>
              </div>
              <div class="layer-desc">纯 UI，遵循 YonDesign</div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ==================== 复杂对象表单 Tab ==================== -->
    <div v-show="activeTab === 'complex-form'" class="tab-content">
      <section class="complex-form-section">
        <h2>复杂对象表单方案 — 20+ 属性处理</h2>
        <p class="preview-intro">
          基于 <strong>SAP Fiori Object Page</strong> 和 <strong>Salesforce Dynamic Forms</strong> 的行业最佳实践，
          演示 <strong>Tab 分组 + FieldGroup 容器 + 渐进式披露 + 条件可见性 + Custom Slot</strong> 五大核心能力。
          参考文档：<code>docs/architecture/03-page-patterns.md</code>
        </p>

        <!-- ===== Schema 定义展示 ===== -->
        <div class="schema-panel">
          <div class="schema-header">
            <AppIcon name="layers" :size="16" />
            <span>单一事实来源：Schema 层（object-definitions/product.yaml）</span>
            <el-tag size="small" type="warning">字段唯一定义处</el-tag>
          </div>
          <div class="schema-body">
            <div class="schema-stats">
              <span><strong>24</strong> 个字段</span>
              <span class="stat-divider">|</span>
              <span><strong>5</strong> 个 Tab/Section</span>
              <span class="stat-divider">|</span>
              <span><strong>6</strong> 个 FieldGroup</span>
              <span class="stat-divider">|</span>
              <span><strong>2</strong> 个条件可见字段</span>
              <span class="stat-divider">|</span>
              <span><strong>1</strong> 个 Custom Slot</span>
            </div>
            <div class="schema-grid">
              <div class="schema-col" v-for="col in schemaColumns" :key="col.label">
                <div class="schema-col-title">{{ col.label }}</div>
                <div class="schema-field" v-for="f in col.fields" :key="f.key">
                  <span class="sf-name">{{ f.key }}</span>
                  <span class="sf-type">{{ f.type }}</span>
                  <span v-if="f.required" class="sf-required">*</span>
                  <span v-if="f.conditional" class="sf-conditional" title="条件可见">[cond]</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== 实际交互演示 ===== -->
        <div class="pattern-group">
          <h3>交互演示：产品详情（24个属性）</h3>

          <div class="live-demo-container">
            <!-- Tab 导航栏 -->
            <el-tabs v-model="activeDetailTab" class="detail-demo-tabs">
              <el-tab-pane
                v-for="tab in detailTabs"
                :key="tab.key"
                :label="tab.label"
                :name="tab.key"
                :disabled="!isTabVisible(tab)"
              >
                <template #label>
                  <span>{{ tab.label }}</span>
                  <el-tag v-if="tab.type === 'custom'" size="small" type="primary" style="margin-left:6px">Custom</el-tag>
                  <el-tooltip v-else-if="tab.visibleWhen" content="条件可见：仅当风险等级=高时显示" placement="top">
                    <AppIcon name="eye" :size="12" style="color:#f59e0b;vertical-align:middle;margin-left:4px;cursor:help" />
                  </el-tooltip>
                </template>
              </el-tab-pane>
            </el-tabs>

            <!-- Tab 内容区 -->
            <div class="detail-tabs-content">

              <!-- ===== 基本信息 Tab ===== -->
              <div v-show="activeDetailTab === 'basic'" class="detail-tab-panel">
                <!-- FieldGroup: 标识信息 -->
                <AppCard title="标识信息" size="sm">
                  <template #header>
                    <AppIcon name="info" :size="14" />
                    <span>标识信息</span>
                    <el-tag size="small" type="warning" style="margin-left:auto">含条件控制字段</el-tag>
                  </template>
                  <div class="fg-body fg-grid-4">
                    <div class="fg-field">
                      <label>产品名称 <span class="required-mark">*</span></label>
                      <el-input v-model="productData.name" placeholder="请输入产品名称" />
                    </div>
                    <div class="fg-field">
                      <label>产品编码 <span class="required-mark">*</span></label>
                      <el-input v-model="productData.code" placeholder="请输入产品编码" />
                    </div>
                    <div class="fg-field">
                      <label>产品类型</label>
                      <el-select v-model="productData.type" style="width:100%">
                        <el-option label="标准产品" value="standard" />
                        <el-option label="定制产品" value="custom" />
                        <el-option label="服务产品" value="service" />
                      </el-select>
                    </div>
                    <div class="fg-field">
                      <label>状态</label>
                      <el-select v-model="productData.status" style="width:100%">
                        <el-option label="活跃" value="active" />
                        <el-option label="停用" value="inactive" />
                        <el-option label="草稿" value="draft" />
                      </el-select>
                    </div>
                    <div class="fg-field fg-field-highlight">
                      <label>风险等级
                        <el-tooltip content="切换此字段观察「合规审查」Tab 的显示/隐藏" placement="top">
                          <AppIcon name="tip" :size="12" style="color:#f59e0b;cursor:help;vertical-align:middle" />
                        </el-tooltip>
                      </label>
                      <el-select v-model="productData.riskLevel" style="width:100%">
                        <el-option label="高（显示合规审查Tab）" value="high" />
                        <el-option label="中" value="medium" />
                        <el-option label="低" value="low" />
                      </el-select>
                    </div>
                  </div>
                </AppCard>

                <!-- FieldGroup: 组织信息 -->
                <AppCard size="sm">
                  <template #header>
                    <AppIcon name="user" :size="14" />
                    <span>组织信息</span>
                  </template>
                  <div class="fg-body fg-grid-4">
                    <div class="fg-field">
                      <label>所属部门</label>
                      <el-select v-model="productData.department" style="width:100%">
                        <el-option label="研发部" value="rd" />
                        <el-option label="产品部" value="product" />
                        <el-option label="销售部" value="sales" />
                      </el-select>
                    </div>
                    <div class="fg-field">
                      <label>负责人</label>
                      <el-input v-model="productData.manager" placeholder="请输入负责人" />
                    </div>
                    <div class="fg-field">
                      <label>创建时间</label>
                      <el-input :model-value="productData.createdAt" disabled />
                    </div>
                    <div class="fg-field">
                      <label>生效日期</label>
                      <el-date-picker v-model="productData.effectiveDate" type="date" style="width:100%" />
                    </div>
                  </div>
                </AppCard>

                <!-- FieldGroup: 扩展属性（渐进式披露） -->
                <div class="collapsible-group">
                  <AppCard size="sm" :class="{ 'app-card--dashed': !showMoreBasic }">
                    <template #header>
                      <span class="collapse-trigger" @click="showMoreBasic = !showMoreBasic">
                        <AppIcon :name="showMoreBasic ? 'chevron-down' : 'chevron-right'" :size="14" />
                        <span>扩展属性</span>
                        <el-tag size="small" type="info" style="margin-left:8px">6个字段</el-tag>
                      </span>
                      <span class="collapse-hint" @click="showMoreBasic = !showMoreBasic">{{ showMoreBasic ? 'Show Less' : 'Show All' }}</span>
                    </template>
                    <div v-show="showMoreBasic" class="fg-body fg-grid-4">
                      <div class="fg-field">
                        <label>产品描述</label>
                        <el-input v-model="productData.description" type="textarea" rows="2" placeholder="产品描述" />
                      </div>
                      <div class="fg-field">
                        <label>版本号</label>
                        <el-input v-model="productData.version" placeholder="如 V3.0" />
                      </div>
                      <div class="fg-field">
                        <label>标签</label>
                        <el-input v-model="productData.tags" placeholder="逗号分隔" />
                      </div>
                      <div class="fg-field">
                        <label>优先级</label>
                        <el-select v-model="productData.priority" style="width:100%">
                          <el-option label="高" value="high" />
                          <el-option label="中" value="medium" />
                          <el-option label="低" value="low" />
                        </el-select>
                      </div>
                      <div class="fg-field">
                        <label>审批人</label>
                        <el-input v-model="productData.approver" placeholder="请输入审批人" />
                      </div>
                      <div class="fg-field">
                        <label>来源</label>
                        <el-input v-model="productData.source" placeholder="如：内部研发" />
                      </div>
                    </div>
                  </AppCard>
                </div>
              </div>

              <!-- ===== 技术参数 Tab ===== -->
              <div v-show="activeDetailTab === 'tech'" class="detail-tab-panel">
                <AppCard size="sm">
                  <template #header>
                    <AppIcon name="settings" :size="14" />
                    <span>技术规格</span>
                  </template>
                  <div class="fg-body fg-grid-4">
                    <div class="fg-field">
                      <label>技术栈</label>
                      <el-input v-model="productData.techStack" placeholder="如 Java, Vue" />
                    </div>
                    <div class="fg-field">
                      <label>数据库</label>
                      <el-select v-model="productData.database" style="width:100%">
                        <el-option label="MySQL" value="mysql" />
                        <el-option label="PostgreSQL" value="postgresql" />
                        <el-option label="Oracle" value="oracle" />
                      </el-select>
                    </div>
                    <div class="fg-field">
                      <label>部署方式</label>
                      <el-select v-model="productData.deployMode" style="width:100%">
                        <el-option label="云部署" value="cloud" />
                        <el-option label="本地部署" value="onprem" />
                        <el-option label="混合部署" value="hybrid" />
                      </el-select>
                    </div>
                    <div class="fg-field">
                      <label>并发用户数</label>
                      <el-input-number v-model="productData.concurrentUsers" :min="0" style="width:100%" />
                    </div>
                  </div>
                </AppCard>

                <AppCard size="sm">
                  <template #header>
                    <AppIcon name="chart-bar" :size="14" />
                    <span>性能指标</span>
                  </template>
                  <div class="fg-body fg-grid-3">
                    <div class="fg-field">
                      <label>响应时间(ms)</label>
                      <el-input-number v-model="productData.responseTime" :min="0" style="width:100%" />
                    </div>
                    <div class="fg-field">
                      <label>可用性(%)</label>
                      <el-input-number v-model="productData.availability" :min="0" :max="100" :precision="2" style="width:100%" />
                    </div>
                    <div class="fg-field">
                      <label>数据量(TB)</label>
                      <el-input-number v-model="productData.dataVolume" :min="0" :precision="1" style="width:100%" />
                    </div>
                  </div>
                </AppCard>
              </div>

              <!-- ===== 商务条款 Tab ===== -->
              <div v-show="activeDetailTab === 'commercial'" class="detail-tab-panel">
                <AppCard size="sm">
                  <template #header>
                    <AppIcon name="chart" :size="14" />
                    <span>价格信息</span>
                  </template>
                  <div class="fg-body fg-grid-3">
                    <div class="fg-field">
                      <label>基准价格(CNY)</label>
                      <el-input-number v-model="productData.basePrice" :min="0" :precision="2" style="width:100%" />
                    </div>
                    <div class="fg-field">
                      <label>折扣率(%)</label>
                      <el-input-number v-model="productData.discountRate" :min="0" :max="100" style="width:100%" />
                    </div>
                    <div class="fg-field">
                      <label>税率(%)</label>
                      <el-input-number v-model="productData.taxRate" :min="0" :max="100" style="width:100%" />
                    </div>
                  </div>
                  <div class="fg-computed-row">
                    <span class="computed-label">实际价格：</span>
                    <span class="computed-value">{{ computedPrice }}</span>
                    <span class="computed-note">（基准价 * (1 - 折扣率) * (1 + 税率)）</span>
                  </div>
                </AppCard>

                <AppCard size="sm">
                  <template #header>
                    <AppIcon name="file" :size="14" />
                    <span>合同信息</span>
                  </template>
                  <div class="fg-body fg-grid-3">
                    <div class="fg-field">
                      <label>合同编号</label>
                      <el-input v-model="productData.contractNo" placeholder="合同编号" />
                    </div>
                    <div class="fg-field">
                      <label>合同期限(月)</label>
                      <el-input-number v-model="productData.contractTerm" :min="1" style="width:100%" />
                    </div>
                    <div class="fg-field">
                      <label>续约方式</label>
                      <el-select v-model="productData.renewalType" style="width:100%">
                        <el-option label="自动续约" value="auto" />
                        <el-option label="手动续约" value="manual" />
                      </el-select>
                    </div>
                  </div>
                </AppCard>
              </div>

              <!-- ===== 合规审查 Tab（条件可见） ===== -->
              <div v-show="activeDetailTab === 'compliance'" class="detail-tab-panel">
                <div class="conditional-banner">
                  <AppIcon name="warning" :size="16" />
                  <span>此 Tab 仅在<strong>风险等级 = "高"</strong>时可见。当前风险等级：
                    <el-tag :type="productData.riskLevel === 'high' ? 'danger' : 'success'" size="small">
                      {{ riskLevelLabel }}
                    </el-tag>
                  </span>
                </div>

                <AppCard size="sm">
                  <template #header>
                    <AppIcon name="check-square" :size="14" />
                    <span>审查信息</span>
                  </template>
                  <div class="fg-body fg-grid-3">
                    <div class="fg-field">
                      <label>审查员</label>
                      <el-input v-model="productData.reviewer" placeholder="审查员姓名" />
                    </div>
                    <div class="fg-field">
                      <label>审查日期</label>
                      <el-date-picker v-model="productData.reviewDate" type="date" style="width:100%" />
                    </div>
                    <div class="fg-field">
                      <label>审查结果</label>
                      <el-select v-model="productData.reviewResult" style="width:100%">
                        <el-option label="通过" value="pass" />
                        <el-option label="不通过" value="fail" />
                        <el-option label="待整改" value="pending" />
                      </el-select>
                    </div>
                    <div class="fg-field fg-span-2">
                      <label>整改期限</label>
                      <el-date-picker v-model="productData.rectifyDeadline" type="date" style="width:100%" />
                    </div>
                  </div>
                </AppCard>
              </div>

              <!-- ===== Custom Slot：价格计算器 ===== -->
              <div v-show="activeDetailTab === 'custom'" class="detail-tab-panel">
                <div class="custom-slot-banner">
                  <AppIcon name="bulb" :size="16" />
                  <span>此 Tab 为<strong> Custom Slot（自定义组件）</strong>，不受 YAML 标准渲染引擎控制</span>
                </div>

                <div class="custom-slot-demo">
                  <h4>价格模拟计算器（Custom Component: PricingSimulator）</h4>
                  <p class="custom-slot-desc">
                    此区域由独立的 Vue 组件渲染，接收统一的 formData context，
                    但拥有完全自由的 UI 布局和交互逻辑。
                  </p>

                  <div class="simulator-grid">
                    <div class="sim-card">
                      <div class="sim-card-title">基础配置</div>
                      <div class="sim-card-body">
                        <div class="sim-row">
                          <span>许可用户数</span>
                          <el-input-number v-model="simulator.licenseCount" :min="1" :max="10000" size="small" />
                        </div>
                        <div class="sim-row">
                          <span>实施天数</span>
                          <el-input-number v-model="simulator.implDays" :min="1" :max="365" size="small" />
                        </div>
                        <div class="sim-row">
                          <span>培训人数</span>
                          <el-input-number v-model="simulator.trainCount" :min="0" :max="500" size="small" />
                        </div>
                      </div>
                    </div>

                    <div class="sim-card">
                      <div class="sim-card-title">费用明细</div>
                      <div class="sim-card-body">
                        <div class="sim-row">
                          <span>许可费</span>
                          <span class="sim-value">{{ formatMoney(simulator.licenseCount * 500) }}</span>
                        </div>
                        <div class="sim-row">
                          <span>实施费</span>
                          <span class="sim-value">{{ formatMoney(simulator.implDays * 3000) }}</span>
                        </div>
                        <div class="sim-row">
                          <span>培训费</span>
                          <span class="sim-value">{{ formatMoney(simulator.trainCount * 2000) }}</span>
                        </div>
                        <div class="sim-row sim-total">
                          <span>预估总价</span>
                          <span class="sim-value total">{{ formatMoney(simTotal) }}</span>
                        </div>
                      </div>
                    </div>

                    <div class="sim-card sim-chart-card">
                      <div class="sim-card-title">费用占比</div>
                      <div class="sim-card-body">
                        <div class="sim-bar-chart">
                          <div class="sim-bar-row">
                            <span class="sim-bar-label">许可费</span>
                            <div class="sim-bar-track">
                              <div class="sim-bar-fill license" :style="{ width: simLicensePercent + '%' }"></div>
                            </div>
                            <span class="sim-bar-pct">{{ simLicensePercent }}%</span>
                          </div>
                          <div class="sim-bar-row">
                            <span class="sim-bar-label">实施费</span>
                            <div class="sim-bar-track">
                              <div class="sim-bar-fill impl" :style="{ width: simImplPercent + '%' }"></div>
                            </div>
                            <span class="sim-bar-pct">{{ simImplPercent }}%</span>
                          </div>
                          <div class="sim-bar-row">
                            <span class="sim-bar-label">培训费</span>
                            <div class="sim-bar-track">
                              <div class="sim-bar-fill train" :style="{ width: simTrainPercent + '%' }"></div>
                            </div>
                            <span class="sim-bar-pct">{{ simTrainPercent }}%</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== YAML 配置展示 ===== -->
        <div class="pattern-group">
          <h3>对应的 YAML 配置（页面层仅声明展示行为）</h3>
          <div class="yaml-display">
            <pre><code>{{ yamlConfigText }}</code></pre>
          </div>
        </div>

        <!-- ===== 设计要点总结 ===== -->
        <div class="pattern-group">
          <h3>设计要点</h3>
          <div class="design-points">
            <div class="design-point">
              <AppIcon name="layers" :size="16" />
              <div>
                <strong>三级容器体系</strong>
                <p>Tab（Section） > FieldGroup（字段分组） > Field（字段），按业务语义组织</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="eye" :size="16" />
              <div>
                <strong>渐进式披露</strong>
                <p>核心字段默认展示，"扩展属性"通过 Show All/Show Less 折叠，避免用户认知负担</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="filter" :size="16" />
              <div>
                <strong>条件可见性</strong>
                <p>"合规审查"Tab 仅在风险等级=高时出现，基于 Salesforce Visibility Rules 模式</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="bulb" :size="16" />
              <div>
                <strong>Custom Slot 插槽</strong>
                <p>"价格模拟器"Tab 为完全自定义组件，接收统一数据 Context，80% YAML + 20% 定制</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="check-square" :size="16" />
              <div>
                <strong>单一事实来源</strong>
                <p>24个字段在 Schema 层唯一定义（type/validation/options），页面配置层仅声明展示行为</p>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== ObjectPage 组件实际应用示例 ===== -->
        <div class="pattern-group">
          <h3>ObjectPage 组件实际应用（YAML 驱动模式）</h3>
          <p class="preview-intro">
            下方展示使用增强后的 <code>&lt;ObjectPage&gt;</code> 组件渲染的枚举类型详情页。
            该组件已应用于 <strong>EnumTypeDetail.vue</strong>，支持：
            <br>- Tab 导航 + 条件可见性
            <br>- FieldGroup 渲染 + 渐进式披露
            <br>- Custom Slot 机制
            <br>- 响应式栅格布局
          </p>

          <div class="objectpage-demo-container">
            <ObjectPage
              title="枚举类型：用户状态"
              subtitle="ENUM_USER_STATUS"
              status="业务定义"
              status-type="success"
              :show-back-button="false"
              :sections="enumSectionsConfig"
              :form-data="enumFormData"
              :field-definitions="enumFieldDefinitions"
              size="md"
              @tab-change="handleEnumTabChange"
              @field-update="handleEnumFieldUpdate"
            />
          </div>

          <div class="yaml-display" style="margin-top: 20px;">
            <h4 style="margin: 0 0 12px; font-size: 14px; color: #666;">对应的 Sections 配置：</h4>
            <pre><code>{{ enumYamlConfig }}</code></pre>
          </div>
        </div>

        <!-- ===== 权限配置页面演示原型（基于 ObjectPage） ===== -->
        <div class="pattern-group" style="margin-top: 32px;">
          <h3>权限配置页面原型（ObjectPage + Custom Slot 混合模式）</h3>
          <p class="preview-intro">
            基于 <strong>统一 ObjectPage 容器</strong> 构建的权限配置页面原型。
            该方案将权限配置的复杂 UI 封装在 <code>Custom Slot</code> 中，
            实现 <strong>80% 标准化（基本信息、Tab 导航）+ 20% 定制化（权限矩阵、条件规则）</strong>。
          </p>

          <div class="objectpage-demo-container permission-demo">
            <ObjectPage
              :title="`角色权限配置：${permissionDemo.role.name}`"
              :subtitle="permissionDemo.role.code"
              status="启用中"
              status-type="success"
              :show-back-button="false"
              :sections="permissionSectionsConfig"
              :form-data="permissionDemo.role"
              :field-definitions="permissionFieldDefs"
              size="md"
              @tab-change="handlePermissionTabChange"
            >
              <!-- 自定义插槽：权限配置面板 -->
              <template #section-permissions>
                <div class="permission-config-panel">
                  <!-- 菜单与功能权限 -->
                  <section class="perm-section">
                    <div class="perm-header">
                      <h4>
                        <AppIcon name="menu" :size="14" />
                        菜单与功能权限
                      </h4>
                      <div class="header-summary">
                        <span class="summary-item assigned">
                          {{ permissionDemo.assignedMenuCount }}/{{ permissionDemo.totalMenuCount }} 菜单已分配
                        </span>
                        <span class="summary-item func-perm">
                          {{ permissionDemo.totalFuncPermissions }} 项功能权限
                        </span>
                      </div>
                    </div>

                    <p class="perm-guide">
                      勾选菜单即授予入口和对应的功能权限（自动同步）。取消菜单不影响已授予权限。
                    </p>

                    <!-- 菜单权限列表 -->
                    <div class="menu-list">
                      <div
                        v-for="menu in permissionDemo.menus"
                        :key="menu.menu_code"
                        :class="['menu-card', { 'is-assigned': menu.assigned }]"
                      >
                        <div class="menu-card-header">
                          <input
                            type="checkbox"
                            :checked="menu.assigned"
                            @change="toggleMenuPermission(menu)"
                          />
                          <div class="menu-title-area" @click="toggleMenuExpand(menu)">
                            <span class="menu-name">{{ menu.display_name }}</span>
                            <span class="menu-path">{{ menu.menu_path }}</span>
                            <span
                              class="expand-icon"
                              :class="{ expanded: expandedMenus.has(menu.menu_code) }"
                            >&#9654;</span>
                          </div>

                          <div class="menu-badges">
                            <span
                              v-if="menu.required_permissions?.length"
                              :class="['badge', 'badge-capability', { 'badge-all-granted': allCapsGranted(menu) }]"
                            >
                              {{ grantedCapCount(menu) }}/{{ menu.required_permissions.length }} 权限
                            </span>
                            <span v-if="menu.has_data_scope" class="badge badge-scope">有数据范围</span>
                          </div>
                        </div>

                        <div v-if="expandedMenus.has(menu.menu_code)" class="menu-card-body">
                          <div v-if="menu.required_permissions?.length" class="capability-list">
                            <div class="capability-label">
                              <AppIcon name="key" :size="12" />
                              <span v-if="menu.assigned">已关联功能权限（随菜单自动授予）</span>
                              <span v-else>关联功能权限（勾选菜单后自动授予）</span>
                            </div>
                            <div class="capability-matrix">
                              <div
                                v-for="rp in menu.required_permissions"
                                :key="rp.code"
                                :class="['cap-item', {
                                  'cap-granted': rp.granted,
                                  'cap-pending': !rp.granted && menu.assigned,
                                  'cap-inactive': !rp.granted && !menu.assigned
                                }]"
                              >
                                <span class="cap-status">
                                  <AppIcon v-if="rp.granted" name="check-circle" :size="10" />
                                  <span v-else-if="menu.assigned" class="status-icon status-pending">&#9678;</span>
                                  <span v-else class="status-icon status-idle">&#9711;</span>
                                </span>
                                <span class="cap-label">{{ rp.label }}</span>
                                <span class="cap-code">{{ rp.code }}</span>
                                <!-- [OK] 新增：来源标签系统（与 RoleDetailDrawer.vue 一致） -->
                                <span
                                  :class="['cap-source-tag', rp.granted ? (rp.source === 'auto' ? 'source-auto' : 'source-manual') : 'source-pending']"
                                >
                                  {{ rp.granted ? (rp.source === 'auto' ? '自动' : '手动') : '待授予' }}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div v-if="menu.has_data_scope" class="data-scope-inline">
                            <div class="scope-label">
                              <AppIcon name="edit" :size="12" /> 数据约束（此菜单的数据访问范围）
                            </div>
                            <div v-for="scope in menu.data_scopes" :key="scope.resource_type" class="scope-item">
                              <span class="scope-type">{{ scope.resource_type }}</span>
                              <span class="scope-detail">
                                {{ scope.permissions.length }} 条规则 ({{ scope.permissions.map(p => p.level).join(', ') }})
                              </span>
                              <button class="btn-link btn-xs" @click="showScopeConfigTip(menu, scope)">配置</button>
                            </div>
                          </div>

                          <!-- [OK] 新增：数据范围建议提示（与 RoleDetailDrawer.vue 一致） -->
                          <div
                            v-if="menu.assigned && !menu.has_data_scope && menu.data_permission_hint?.resource_types?.length"
                            class="data-scope-hint"
                          >
                            <span class="hint-icon"><AppIcon name="tip" :size="14" /></span>
                            建议为此菜单配置
                            <button class="btn-link btn-xs" @click="openDataScopeForMenu(menu)">数据权限</button>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div class="menu-actions-bar">
                      <button class="btn btn-ghost" @click="selectAllMenus">全选菜单</button>
                      <button class="btn btn-ghost" @click="clearAllMenus">清空</button>
                      <div class="actions-spacer"></div>
                      <button
                        class="btn btn-primary"
                        @click="savePermissions"
                        :disabled="permissionDemo.saving"
                      >
                        {{ permissionDemo.saving ? '保存中...' : '保存全部权限' }}
                      </button>
                    </div>
                  </section>

                  <!-- 条件型权限 -->
                  <section class="perm-section condition-section">
                    <h4>
                      <AppIcon name="filter" :size="14" />
                      条件型权限
                    </h4>
                    <p class="section-desc">(基于条件表达式，新增资源自动继承)</p>

                    <button class="btn btn-ghost" @click="showAddConditionDialog = true">
                      + 添加条件规则
                    </button>

                    <div v-if="permissionDemo.conditionRules.length === 0" class="empty-tip">
                      暂无条件型权限规则
                    </div>
                    <div v-else class="perm-list">
                      <div
                        v-for="rule in permissionDemo.conditionRules"
                        :key="rule.id"
                        class="perm-item"
                        :class="{ 'is-denied': rule.is_denied }"
                      >
                        <div class="perm-main">
                          <span v-if="rule.is_denied" class="denied-badge">禁止</span>
                          <span class="perm-name">{{ rule.resource_type }}</span>
                          <code class="perm-condition">{{ rule.condition }}</code>
                        </div>
                        <!-- [OK] 新增：友好条件表达式（与 RoleDetailDrawer.vue 一致） -->
                        <div v-if="rule.friendly_condition" class="perm-friendly">
                          {{ rule.friendly_condition }}
                        </div>
                        <div class="perm-meta">
                          <span class="perm-level" :class="'level-' + (rule.permission_level || 'read')">
                            {{ getPermLevelLabel(rule.permission_level) }}
                          </span>
                          <span v-if="rule.inherit_to_children" class="inherit-badge">继承</span>
                          <button class="btn-link danger" @click="removeConditionRule(rule)">删除</button>
                        </div>
                      </div>
                    </div>
                  </section>
                </div>
              </template>

              <!-- 自定义插槽：操作日志 -->
              <template #section-audit-log>
                <AuditLog
                  :logs="permissionDemo.auditLogs"
                  :loading="false"
                  :display-limit="5"
                />
              </template>
            </ObjectPage>
          </div>

          <!-- 方案说明 -->
          <div class="design-points" style="margin-top: 24px;">
            <div class="design-point">
              <AppIcon name="layout" :size="16" />
              <div>
                <strong>统一的页面容器（ObjectPage）</strong>
                <p>提供 Sticky Header、Tab 导航、响应式布局等通用能力，保证与其他详情页的一致性</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="lock" :size="16" />
              <div>
                <strong>Custom Slot 处理特殊逻辑</strong>
                <p>权限配置的复杂 UI（菜单矩阵、条件规则）封装在独立区域，不影响 ObjectPage 通用性</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="layers" :size="16" />
              <div>
                <strong>清晰的分层架构</strong>
                <p>容器层(ObjectPage) → 业务层(PermissionConfigPanel) → 组件层(MenuMatrix, ConditionList)</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="check-square" :size="16" />
              <div>
                <strong>符合架构原则</strong>
                <p>YAML 单一事实原则（基本信息）、元数据驱动架构、页面组件单一引用原则</p>
              </div>
            </div>
          </div>

          <!-- YAML 配置展示 -->
          <div class="yaml-display" style="margin-top: 20px;">
            <h4 style="margin: 0 0 12px; font-size: 14px; color: #666;">权限配置页面的 Sections 配置：</h4>
            <pre><code>{{ permissionYamlConfig }}</code></pre>
          </div>
        </div>
      </section>
    </div>

    <!-- ==================== Inline Edit Tab ==================== -->
    <div v-show="activeTab === 'inline-edit'" class="tab-content">
      <section class="inline-edit-section">
        <h2>Inline Edit 单元格编辑模式</h2>
        <p class="preview-intro">
          基于 <strong>MetaListPage</strong> 的 Inline Edit 模式，支持<strong>快速编辑</strong>和<strong>直接录入</strong>两种交互方式。
        </p>

        <!-- 两种编辑模式对比 -->
        <div class="pattern-group">
          <h3>编辑模式对比</h3>
          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>Quick Edit 模式（悬停编辑）</h4>
              <div class="rounded-demo">
                <div class="quick-edit-demo">
                  <div class="demo-cell">
                    <span class="cell-label">产品名称</span>
                    <span class="cell-value">企业版 ERP</span>
                    <el-icon class="edit-icon"><Edit /></el-icon>
                  </div>
                </div>
                <div class="mode-description">
                  <p><strong>交互</strong>：悬停 → 编辑图标 → 点击编辑 → 保存</p>
                </div>
              </div>
            </div>

            <div class="rounded-item rounded">
              <h4>Direct Entry 模式（直接录入）</h4>
              <div class="rounded-demo">
                <div class="direct-edit-demo">
                  <div class="demo-cell direct">
                    <span class="cell-label">用户名</span>
                    <el-input size="small" placeholder="直接输入" />
                  </div>
                </div>
                <div class="mode-description">
                  <p><strong>交互</strong>：直接显示输入框 → 随时可输入</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 状态反馈 -->
        <div class="pattern-group">
          <h3>状态反馈系统</h3>
          <div class="status-demo">
            <div class="status-row">
              <span class="status-label">默认</span>
              <div class="inline-edit-cell is-default">
                <span class="cell-value">正常显示的值</span>
              </div>
            </div>
            <div class="status-row">
              <span class="status-label">悬停</span>
              <div class="inline-edit-cell is-hovered">
                <span class="cell-value">鼠标悬停时</span>
                <el-icon class="edit-icon-visible"><Edit /></el-icon>
              </div>
            </div>
            <div class="status-row">
              <span class="status-label">编辑中</span>
              <div class="inline-edit-cell is-editing">
                <el-input size="small" model-value="正在编辑" />
              </div>
            </div>
            <div class="status-row">
              <span class="status-label">已修改</span>
              <div class="inline-edit-cell is-modified">
                <span class="cell-value">修改后的值</span>
              </div>
            </div>
            <div class="status-row">
              <span class="status-label">不可编辑</span>
              <div class="inline-edit-cell is-immutable">
                <span class="cell-value">系统生成，不可编辑</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 快捷键 -->
        <div class="pattern-group">
          <h3>键盘快捷键</h3>
          <div class="shortcuts-grid">
            <div class="shortcut-item">
              <kbd>Enter</kbd>
              <span>保存编辑</span>
            </div>
            <div class="shortcut-item">
              <kbd>Escape</kbd>
              <span>取消编辑</span>
            </div>
            <div class="shortcut-item">
              <kbd>Tab</kbd>
              <span>下一个单元格</span>
            </div>
          </div>
        </div>

        <!-- 设计要点 -->
        <div class="pattern-group">
          <h3>设计要点</h3>
          <div class="design-points">
            <div class="design-point">
              <AppIcon name="check-square" :size="16" />
              <div>
                <strong>渐进式交互</strong>
                <p>悬停提示编辑能力，不打断工作流</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="layers" :size="16" />
              <div>
                <strong>批量操作</strong>
                <p>支持多行修改后统一保存</p>
              </div>
            </div>
            <div class="design-point">
              <AppIcon name="check-square" :size="16" />
              <div>
                <strong>视觉反馈</strong>
                <p>颜色编码区分状态</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ==================== 顶部导航系统 Tab [NEW] ==================== -->
    <div v-show="activeTab === 'navigation'" class="tab-content">
      <section class="navigation-section">
        <h2>[DECORATIVE] 顶部导航系统组件 (Navigation System)</h2>
        <p class="preview-intro">
          参考 <strong>SAP Fiori / Salesforce Lightning Console / Microsoft Dynamics 365</strong> 设计模式构建的企业级全局导航系统。
          包含 <strong>6 个核心组件</strong>，支持多页面管理、面包屑导航、用户菜单、全局搜索等功能。
        </p>

        <!-- 统计卡片 -->
        <div class="stats-bar" style="margin-bottom: 24px;">
          <div class="stat-item">
            <span class="stat-number">6</span>
            <span class="stat-label">导航组件数</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">~2,500</span>
            <span class="stat-label">代码行数</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">100%</span>
            <span class="stat-label">YonDesign 规范遵循</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">A11y</span>
            <span class="stat-label">无障碍支持</span>
          </div>
        </div>

        <!-- ====== 1. AppShell 全局容器 ====== -->
        <div class="pattern-group">
          <h3>1️⃣ AppShell - 全局应用容器</h3>
          <p class="pattern-desc">
            应用的最外层容器，提供统一的布局结构：<strong>Header + Tabs + Sidebar + Content</strong><br>
            支持 Slot 化设计，灵活组合各个区域。
          </p>

          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>最小化用法（仅 Header）</h4>
              <div class="rounded-demo" style="min-height: 200px; background: #f5f7fa; border-radius: 8px; padding: 16px;">
                <AppShell :show-sidebar="false">
                  <template #header-left>
                    <strong style="color: var(--yonyou-orange-600);">ArchData Platform</strong>
                  </template>

                  <template #header-right>
                    <GlobalSearch placeholder="搜索..." style="width: 200px;" />
                    <UserMenu :user="demoUser" :show-name="true" />
                  </template>

                  <div style="padding: 20px; background: white; border-radius: 6px; text-align: center; color: #666;">
                    页面内容区域
                  </div>
                </AppShell>
              </div>
              <pre class="code-block">&lt;AppShell :show-sidebar="false"&gt;
  &lt;template #header-left&gt;
    &lt;strong&gt;Logo&lt;/strong&gt;
  &lt;/template&gt;
  &lt;template #header-right&gt;
    &lt;GlobalSearch /&gt;
    &lt;UserMenu /&gt;
  &lt;/template&gt;
  &lt;!-- Content --&gt;
&lt;/AppShell&gt;</pre>
            </div>

            <div class="rounded-item rounded">
              <h4>完整布局（Header + Tabs + Sidebar）</h4>
              <div class="rounded-demo" style="min-height: 300px; background: #f5f7fa; border-radius: 8px; overflow: hidden;">
                <AppShell :show-tabs="true" :sidebar-width="200">
                  <template #header-left>
                    <strong style="color: var(--yonyou-orange-600); font-size: 14px;">[DECORATIVE] ArchData</strong>
                  </template>

                  <template #header-center>
                    <BreadcrumbNav :items="demoBreadcrumbs" />
                  </template>

                  <template #header-right>
                    <UserMenu :user="demoUser" />
                  </template>

                  <template #tabs>
                    <AppTabs v-model="demoActiveTab" :tabs="demoTabs" />
                  </template>

                  <template #sidebar>
                    <div style="padding: 12px; font-size: 12px; color: #666;">
                      <div style="margin-bottom: 8px; font-weight: bold;">导航菜单</div>
                      <div style="padding: 4px 0; cursor: pointer;">[SYMBOL] 首页</div>
                      <div style="padding: 4px 0; cursor: pointer; color: var(--yonyou-orange-600);">[SYMBOL] 用户管理</div>
                      <div style="padding: 4px 0; cursor: pointer;">[SYMBOL]️ 系统设置</div>
                    </div>
                  </template>

                  <div style="padding: 20px; background: white; margin: 12px; border-radius: 6px;">
                    <strong>主内容区 - 用户管理页面</strong>
                  </div>
                </AppShell>
              </div>
              <pre class="code-block">&lt;AppShell :show-tabs="true"&gt;
  &lt;template #header-center&gt;
    &lt;BreadcrumbNav /&gt;
  &lt;/template&gt;
  &lt;template #tabs&gt;
    &lt;AppTabs v-model="tab" :tabs="tabs" /&gt;
  &lt;/template&gt;
  &lt;template #sidebar&gt;
    &lt;AppSideNav /&gt;
  &lt;/template&gt;
  &lt;router-view /&gt;
&lt;/AppShell&gt;</pre>
            </div>
          </div>
        </div>

        <!-- ====== 2. AppTabs 多页面Tab ====== -->
        <div class="pattern-group">
          <h3>2️⃣ AppTabs - 多页面 Tab 管理</h3>
          <p class="pattern-desc">
            参考 <strong>Salesforce Console Primary Tabs</strong> 设计，支持同时打开多个页面并快速切换。<br>
            特性：最多显示 8-10 个、溢出菜单、固定 Tab、关闭按钮。
          </p>

          <div class="component-showcase">
            <h4>功能演示</h4>
            <div class="showcase-demo" style="background: white; padding: 16px; border-radius: 8px; border: 1px solid #e5e6eb;">
              <AppTabs
                v-model="demoActiveTab"
                :tabs="demoTabs"
                :max-tabs="8"
                @tab-close="handleDemoTabClose"
              />
            </div>

            <div class="feature-list" style="margin-top: 16px;">
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>固定 Tab</strong>: 首页 Tab 不可关闭（pinned: true）</span>
              </div>
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>徽章支持</strong>: 显示未读数或状态</span>
              </div>
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>溢出菜单</strong>: 超过 maxTabs 自动折叠到"更多"</span>
              </div>
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>v-model 双向绑定</strong>: 支持响应式切换</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ====== 3. BreadcrumbNav 面包屑 ====== -->
        <div class="pattern-group">
          <h3>3️⃣ BreadcrumbNav - 面包屑导航</h3>
          <p class="pattern-desc">
            清晰的路径导航，支持<strong>路由跳转</strong>、<strong>省略号折叠</strong>、<strong>自定义分隔符</strong>。
          </p>

          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>基础用法</h4>
              <div class="rounded-demo" style="padding: 16px; background: white; border-radius: 6px;">
                <BreadcrumbNav :items="demoBreadcrumbs" />
              </div>
              <pre class="code-block">&lt;BreadcrumbNav
  :items="[
    { label: '首页', to: '/' },
    { label: '系统管理', to: '/system' },
    { label: '用户管理' }
  ]
/&gt;</pre>
            </div>

            <div class="rounded-item rounded">
              <h4>自定义分隔符 + 首页图标</h4>
              <div class="rounded-demo" style="padding: 16px; background: white; border-radius: 6px;">
                <BreadcrumbNav
                  :items="demoBreadcrumbs"
                  separator="/"
                  :home-item="{ label: 'Home', to: '/' }"
                />
              </div>
              <pre class="code-block">&lt;BreadcrumbNav
  separator="/"
  :home-item="{ label: 'Home' }"
  :max-items="3"
/&gt;</pre>
            </div>
          </div>
        </div>

        <!-- ====== 4. UserMenu 用户菜单 ====== -->
        <div class="pattern-group">
          <h3>4️⃣ UserMenu - 用户下拉菜单</h3>
          <p class="pattern-desc">
            展示用户信息（头像、姓名、角色）和操作菜单。<br>
            支持<strong>头部信息卡片</strong>、<strong>分割线</strong>、<strong>危险操作标识</strong>。
          </p>

          <div class="component-showcase">
            <h4>样式变体</h4>
            <div class="showcase-demo" style="display: flex; gap: 24px; padding: 20px; background: white; border-radius: 8px;">
              <div style="text-align: center;">
                <p style="font-size: 12px; color: #999; margin-bottom: 8px;">仅头像</p>
                <UserMenu :user="demoUser" />
              </div>
              <div style="text-align: center;">
                <p style="font-size: 12px; color: #999; margin-bottom: 8px;">头像 + 姓名</p>
                <UserMenu :user="demoUser" :show-name="true" />
              </div>
              <div style="text-align: center;">
                <p style="font-size: 12px; color: #999; margin-bottom: 8px;">完整版（带头像卡片）</p>
                <UserMenu :user="demoUser" :show-name="true" :show-header="true" />
              </div>
            </div>
          </div>
        </div>

        <!-- ====== 5. GlobalSearch 全局搜索 ====== -->
        <div class="pattern-group">
          <h3>5️⃣ GlobalSearch - 全局搜索</h3>
          <p class="pattern-desc">
            全局搜索入口，支持 <strong>Ctrl+K 快捷键唤起</strong>、<strong>搜索建议</strong>、<strong>最近搜索历史</strong>。
          </p>

          <div class="component-showcase">
            <h4>功能演示（点击输入框体验）</h4>
            <div class="showcase-demo" style="padding: 20px; background: white; border-radius: 8px;">
              <GlobalSearch
                placeholder="搜索功能、页面、用户... (Ctrl+K)"
                hotkey="Ctrl+K"
                :recent-searches="['用户管理', '角色配置', '审计日志']"
                :suggestions="searchSuggestions"
                @search="handleDemoSearch"
                style="max-width: 400px;"
              />
            </div>

            <div class="feature-list" style="margin-top: 16px;">
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>快捷键</strong>: Ctrl+K 或 Cmd+K 全局唤起</span>
              </div>
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>建议列表</strong>: 按类型分类（页面/用户/设置）</span>
              </div>
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>最近搜索</strong>: 本地存储搜索历史</span>
              </div>
              <div class="feature-item">
                <AppIcon name="check" :size="16" style="color: #22c55e;" />
                <span><strong>TypeScript 类型</strong>: 完整的类型定义</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ====== 6. PageHeader 页面标题栏 ====== -->
        <div class="pattern-group">
          <h3>6️⃣ PageHeader (AppHeader) - 页面标题栏</h3>
          <p class="pattern-desc">
            子页面级标题栏，包含<strong>返回按钮</strong>、<strong>页面标题</strong>、<strong>操作按钮区</strong>。
          </p>

          <div class="rounded-grid">
            <div class="rounded-item">
              <h4>标准用法（返回 + 标题）</h4>
              <div class="rounded-demo" style="padding: 16px; background: white; border-radius: 6px;">
                <PageHeader title="用户详情" :show-back="true" />
              </div>
              <pre class="code-block">&lt;PageHeader
  title="用户详情"
  :show-back="true"
  @back="$router.back()"
/&gt;</pre>
            </div>

            <div class="rounded-item rounded">
              <h4>带操作按钮</h4>
              <div class="rounded-demo" style="padding: 16px; background: white; border-radius: 6px;">
                <PageHeader title="编辑用户" :show-back="true">
                  <template #right>
                    <el-button size="small">取消</el-button>
                    <el-button size="small" type="primary">保存</el-button>
                  </template>
                </PageHeader>
              </div>
              <pre class="code-block">&lt;PageHeader title="编辑" :show-back="true"&gt;
  &lt;template #right&gt;
    &lt;el-button&gt;取消&lt;/el-button&gt;
    &lt;el-button type="primary"&gt;保存&lt;/el-button&gt;
  &lt;/template&gt;
&lt;/PageHeader&gt;</pre>
            </div>
          </div>
        </div>

        <!-- 架构总结 -->
        <div class="summary-section" style="margin-top: 32px; padding: 24px; background: linear-gradient(135deg, #ffedd5 0%, #fed7aa 100%); border-radius: 12px;">
          <h2 style="margin: 0 0 16px 0; color: #9a3412;">[SYMBOL] 组件架构关系图</h2>
          <div style="background: white; padding: 20px; border-radius: 8px; font-family: monospace; font-size: 13px; line-height: 1.8;">
<pre style="margin: 0; color: #374151;">
AppShell (全局容器)
├── Header (56px)
│   ├── header-left:     [Logo]
│   ├── header-center:   [BreadcrumbNav] [GlobalSearch]
│   └── header-right:    [通知] [UserMenu]
│
├── Tabs Bar (44px)
│   └── AppTabs:  [Page1] [Page2] [Page3] ... [更多 ▼]
│
├── Sidebar (240px, 可选)
│   └── AppSideNav: [导航菜单]
│
└── Content Area
    ├── PageHeader (子页面标题)
    └── [业务内容]
</pre>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Check, Close, Search, Edit, Delete, Plus } from '@element-plus/icons-vue'
import {
  DateTimePicker, AppButton, AppInput, AppSelect, AppModal, AppTabs,
  AppAlert, AppCard, AppCollapse, AppIcon, AppSideNav, Pagination,
  Drawer, EmptyState, ConfirmDialog, EnumSelect, EnumSearchHelp,
  FilterBar, MetaTable, MetaForm, MetaDialog, AppHeader,
  AuditLog, MasterDetailLayout, ObjectPage,
  // 顶部导航系统组件 [NEW]
  AppShell
} from '@/components/common'
import InlineEditCell from '@/components/common/MetaListPage/InlineEditCell.vue'
import InlineEditToolbar from '@/components/common/MetaListPage/InlineEditToolbar.vue'
import { useMessage } from '@/composables/useMessage'

const message = useMessage()

// Tab 导航
const tabs = [
  { key: 'basic', label: '基础组件对比' },
  { key: 'page', label: '页面组件模式' },
  { key: 'complex-form', label: '复杂对象表单' },
  { key: 'inline-edit', label: 'Inline Edit' },
  { key: 'navigation', label: '[DECORATIVE] 顶部导航系统 [NEW]' }  // 新增
]
const activeTab = ref('basic')

// ====== 顶部导航系统演示数据 [NEW] ======
const demoUser = ref({
  name: '张三',
  email: 'zhangsan@example.com',
  role: '系统管理员'
})

const demoBreadcrumbs = ref([
  { label: '首页', to: '/' },
  { label: '系统管理', to: '/system' },
  { label: '用户管理' }
])

const demoActiveTab = ref('users')
const demoTabs = ref([
  { id: 'home', label: '首页', icon: 'Odometer', pinned: true },
  { id: 'users', label: '用户管理', badge: 5, closable: true },
  { id: 'roles', label: '角色管理', closable: true },
  { id: 'settings', label: '系统设置', closable: true }
])

const searchSuggestions = ref([
  { id: 1, title: '用户管理', subtitle: '系统管理 > 用户管理', type: 'page' },
  { id: 2, title: '张三', subtitle: '系统管理员', type: 'user' },
  { id: 3, title: '全局设置', subtitle: '配置中心', type: 'setting' }
])

// 顶部导航事件处理
function handleDemoTabClose(tabId) {
  const index = demoTabs.value.findIndex(t => t.id === tabId)
  if (index > -1 && !demoTabs.value[index].pinned) {
    demoTabs.value.splice(index, 1)
  }
}

function handleDemoSearch(keyword) {
  console.log('搜索:', keyword)
}

// 页面组件模式演示数据
const demoProducts = ref([
  {
    id: 1,
    name: '企业版 ERP',
    code: 'ERP_ENTERPRISE',
    description: '面向大型企业的综合管理系统',
    versions: [
      { id: 11, name: 'V3.0', status: 'active', created: '2024-01-15' },
      { id: 12, name: 'V2.5', status: 'inactive', created: '2023-08-20' },
      { id: 13, name: 'V2.0', status: 'inactive', created: '2023-03-10' },
      { id: 14, name: 'V1.5', status: 'inactive', created: '2022-11-05' }
    ]
  },
  {
    id: 2,
    name: '轻量版 CRM',
    code: 'CRM_LITE',
    description: '面向中小企业的客户关系管理',
    versions: [
      { id: 21, name: 'V2.0', status: 'active', created: '2024-02-10' },
      { id: 22, name: 'V1.8', status: 'inactive', created: '2023-11-05' },
      { id: 23, name: 'V1.5', status: 'inactive', created: '2023-06-15' }
    ]
  },
  {
    id: 3,
    name: '财务管理系统',
    code: 'FINANCE',
    description: '企业级财务管理解决方案',
    versions: [
      { id: 31, name: 'V1.5', status: 'active', created: '2024-03-01' },
      { id: 32, name: 'V1.0', status: 'inactive', created: '2023-09-20' }
    ]
  },
  {
    id: 4,
    name: '人力资源系统',
    code: 'HR_SYSTEM',
    description: '企业人力资源管理平台',
    versions: [
      { id: 41, name: 'V2.2', status: 'active', created: '2024-02-28' },
      { id: 42, name: 'V2.1', status: 'inactive', created: '2023-12-15' },
      { id: 43, name: 'V2.0', status: 'inactive', created: '2023-08-01' },
      { id: 44, name: 'V1.5', status: 'inactive', created: '2023-04-10' },
      { id: 45, name: 'V1.0', status: 'inactive', created: '2022-12-20' }
    ]
  },
  {
    id: 5,
    name: '供应链管理系统',
    code: 'SCM',
    description: '供应链协同管理平台',
    versions: [
      { id: 51, name: 'V1.8', status: 'active', created: '2024-01-20' },
      { id: 52, name: 'V1.5', status: 'inactive', created: '2023-10-05' }
    ]
  },
  {
    id: 6,
    name: '客户服务中心',
    code: 'CALL_CENTER',
    description: '全渠道客户服务平台',
    versions: [
      { id: 61, name: 'V3.0', status: 'active', created: '2024-03-15' },
      { id: 62, name: 'V2.8', status: 'inactive', created: '2024-01-10' },
      { id: 63, name: 'V2.5', status: 'inactive', created: '2023-09-25' }
    ]
  }
])
const selectedProduct = ref(demoProducts.value[0])
const selectedVersion = ref(demoProducts.value[0].versions[0])

// 关联关系演示数据
const allRoles = ref([
  { id: 'r1', name: '系统管理员', code: 'sys_admin' },
  { id: 'r2', name: '业务管理员', code: 'biz_admin' },
  { id: 'r3', name: '普通用户', code: 'user' },
  { id: 'r4', name: '访客', code: 'guest' },
  { id: 'r5', name: '审计员', code: 'auditor' }
])
const selectedRoleIds = ref(['r1', 'r2'])
const selectedRoles = computed(() => allRoles.value.filter(r => selectedRoleIds.value.includes(r.id)))
const availableRoles = computed(() => allRoles.value.filter(r => !selectedRoleIds.value.includes(r.id)))
const roleSearchQuery = ref('')
const showRoleDialog = ref(false)

const filteredAllRoles = computed(() => {
  if (!roleSearchQuery.value) return allRoles.value
  const query = roleSearchQuery.value.toLowerCase()
  return allRoles.value.filter(r =>
    r.name.toLowerCase().includes(query) ||
    r.code.toLowerCase().includes(query)
  )
})

// ==================== 复杂对象表单演示数据 ====================

const schemaColumns = [
  {
    label: '标识信息',
    fields: [
      { key: 'name', type: 'text', required: true },
      { key: 'code', type: 'text', required: true },
      { key: 'type', type: 'select' },
      { key: 'status', type: 'select' }
    ]
  },
  {
    label: '组织信息',
    fields: [
      { key: 'department', type: 'select' },
      { key: 'manager', type: 'text' },
      { key: 'createdAt', type: 'datetime' },
      { key: 'effectiveDate', type: 'date' }
    ]
  },
  {
    label: '扩展属性',
    fields: [
      { key: 'description', type: 'textarea' },
      { key: 'version', type: 'text' },
      { key: 'tags', type: 'text' },
      { key: 'priority', type: 'select' },
      { key: 'approver', type: 'text' },
      { key: 'source', type: 'text' }
    ]
  },
  {
    label: '技术参数',
    fields: [
      { key: 'techStack', type: 'text' },
      { key: 'database', type: 'select' },
      { key: 'deployMode', type: 'select' },
      { key: 'concurrentUsers', type: 'number' },
      { key: 'responseTime', type: 'number' },
      { key: 'availability', type: 'number' },
      { key: 'dataVolume', type: 'number' }
    ]
  },
  {
    label: '商务条款',
    fields: [
      { key: 'basePrice', type: 'number' },
      { key: 'discountRate', type: 'number' },
      { key: 'taxRate', type: 'number' },
      { key: 'contractNo', type: 'text' },
      { key: 'contractTerm', type: 'number' },
      { key: 'renewalType', type: 'select' }
    ]
  },
  {
    label: '合规审查 (条件)',
    fields: [
      { key: 'riskLevel', type: 'select', conditional: true },
      { key: 'reviewer', type: 'text', conditional: true },
      { key: 'reviewDate', type: 'date', conditional: true },
      { key: 'reviewResult', type: 'select', conditional: true },
      { key: 'rectifyDeadline', type: 'date', conditional: true }
    ]
  }
]

const productData = ref({
  name: '企业版 ERP',
  code: 'ERP-001',
  type: 'standard',
  status: 'active',
  department: 'rd',
  manager: '张三',
  createdAt: '2024-03-15',
  effectiveDate: '2024-04-01',
  description: '面向大型企业的综合管理系统',
  version: 'V3.0',
  tags: 'ERP, 企业管理, 大型企业',
  priority: 'high',
  approver: '李四',
  source: '内部研发',
  techStack: 'Java, Vue3, PostgreSQL',
  database: 'postgresql',
  deployMode: 'cloud',
  concurrentUsers: 500,
  responseTime: 200,
  availability: 99.95,
  dataVolume: 2.5,
  basePrice: 500000,
  discountRate: 10,
  taxRate: 6,
  contractNo: 'CT-2024-001',
  contractTerm: 36,
  renewalType: 'auto',
  riskLevel: 'high',
  reviewer: '王五',
  reviewDate: '2024-05-10',
  reviewResult: 'pass',
  rectifyDeadline: '2024-06-01'
})

const detailTabs = [
  { key: 'basic', label: '基本信息', type: 'standard', visible: true },
  { key: 'tech', label: '技术参数', type: 'standard', visible: true },
  { key: 'commercial', label: '商务条款', type: 'standard', visible: true },
  { key: 'compliance', label: '合规审查', type: 'standard', visibleWhen: { field: 'riskLevel', operator: 'equals', value: 'high' } },
  { key: 'custom', label: '价格模拟器', type: 'custom', component: 'PricingSimulator', visible: true }
]

const activeDetailTab = ref('basic')
const showMoreBasic = ref(false)

function isTabVisible(tab) {
  if (!tab.visibleWhen) return true
  const { field, operator, value } = tab.visibleWhen
  if (operator === 'equals') {
    return productData.value[field] === value
  }
  return true
}

const riskLevelLabel = computed(() => {
  const map = { high: '高', medium: '中', low: '低' }
  return map[productData.value.riskLevel] || productData.value.riskLevel
})

const computedPrice = computed(() => {
  const base = productData.value.basePrice || 0
  const discount = (productData.value.discountRate || 0) / 100
  const tax = (productData.value.taxRate || 0) / 100
  const price = base * (1 - discount) * (1 + tax)
  return 'CNY ' + price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})

const simulator = ref({
  licenseCount: 100,
  implDays: 30,
  trainCount: 20
})

const simLicenseFee = computed(() => simulator.value.licenseCount * 500)
const simImplFee = computed(() => simulator.value.implDays * 3000)
const simTrainFee = computed(() => simulator.value.trainCount * 2000)
const simTotal = computed(() => simLicenseFee.value + simImplFee.value + simTrainFee.value)

const simLicensePercent = computed(() => {
  if (simTotal.value === 0) return 0
  return Math.round((simLicenseFee.value / simTotal.value) * 100)
})
const simImplPercent = computed(() => {
  if (simTotal.value === 0) return 0
  return Math.round((simImplFee.value / simTotal.value) * 100)
})
const simTrainPercent = computed(() => {
  if (simTotal.value === 0) return 0
  return Math.round((simTrainFee.value / simTotal.value) * 100)
})

function formatMoney(val) {
  return 'CNY ' + val.toLocaleString('zh-CN', { minimumFractionDigits: 0 })
}

// ==================== ObjectPage 组件演示数据（枚举类型） ====================

const enumFormData = ref({
  id: 'ENUM_USER_STATUS',
  name: '用户状态',
  category: 'business',
  mutability: 'business',
  description: '定义系统中用户的各种状态，包括活跃、禁用、锁定等'
})

const enumFieldDefinitions = computed(() => ({
  id: {
    label: '编码',
    type: 'text',
    editable: false,
    required: true
  },
  name: {
    label: '名称',
    type: 'text',
    editable: true,
    required: true,
    placeholder: '请输入枚举类型名称'
  },
  category: {
    label: '分类',
    type: 'select',
    options: [
      { label: '系统', value: 'system' },
      { label: '业务', value: 'business' },
      { label: '用户', value: 'user' }
    ],
    editable: true,
    placeholder: '请选择分类'
  },
  mutability: {
    label: '可维护性',
    type: 'select',
    options: [
      { label: '系统定义（不可修改）', value: 'system' },
      { label: '业务定义（可修改）', value: 'business' },
      { label: '用户定义（可修改）', value: 'user' }
    ],
    editable: false
  },
  description: {
    label: '描述',
    type: 'textarea',
    editable: true,
    placeholder: '请输入描述信息'
  }
}))

const enumSectionsConfig = computed(() => [
  {
    key: 'basic',
    label: '基本信息',
    icon: 'info',
    type: 'standard',
    fieldGroups: [
      {
        title: '标识信息',
        icon: 'tag',
        layout: 'grid-2',
        fields: ['id', 'name']
      },
      {
        title: '分类与权限',
        icon: 'settings',
        layout: 'grid-2',
        fields: ['category', 'mutability']
      },
      {
        title: '详细描述',
        icon: 'file-text',
        layout: 'grid-1',
        collapsed: true,
        fields: ['description']
      }
    ]
  },
  {
    key: 'values',
    label: '枚举值列表',
    icon: 'list',
    type: 'custom',
    component: null  // Stub removed in PR 8 - use MetaListPage directly with object-type='enum_value'
  },
  {
    key: 'history',
    label: '变更历史',
    icon: 'clock',
    type: 'custom',
    component: 'SystemManagement/ChangeHistory'
  }
])

const enumYamlConfig = `# enum_type.yaml (Schema层 - 字段唯一定义)
enum_type:
  label: "枚举类型"
  fields:
    id:
      label: "编码"
      type: "text"
      required: true
      editable: false
    name:
      label: "名称"
      type: "text"
      required: true
      editable: true
    category:
      label: "分类"
      type: "select"
      options: [system, business, user]
      editable: true
    mutability:
      label: "可维护性"
      type: "select"
      options: [system, business, user]
      editable: false
    description:
      label: "描述"
      type: "textarea"
      editable: true

# page-definitions/enum-type-detail.yaml (页面配置层)
detailPage:
  objectType: "enum_type"
  
  sections:
    - key: "basic"
      label: "基本信息"
      icon: "info"
      fieldGroups:
        - title: "标识信息"
          layout: "grid-2"
          fields: [id, name]
        - title: "分类与权限"
          layout: "grid-2"
          fields: [category, mutability]
        - title: "详细描述"
          layout: "grid-1"
          collapsed: true
          fields: [description]

    - key: "values"
      label: "枚举值列表"
      icon: "list"
      type: "custom"
      component: "SystemManagement/EnumValueList"

    - key: "history"
      label: "变更历史"
      icon: "clock"
      type: "custom"
      component: "SystemManagement/ChangeHistory"`

function handleEnumTabChange(tabKey) {
  console.log('[ObjectPage Demo] Tab 切换:', tabKey)
}

function handleEnumFieldUpdate(updateData) {
  console.log('[ObjectPage Demo] 字段更新:', updateData)
  Object.assign(enumFormData.value, updateData)
}

// ==================== 权限配置页面演示数据（基于 ObjectPage + Custom Slot） ====================

const permissionDemo = ref({
  role: {
    name: '系统管理员',
    code: 'ROLE_ADMIN',
    description: '拥有系统全部权限的管理员角色'
  },
  saving: false,
  menus: [
    {
      menu_code: 'user_management',
      display_name: '用户管理',
      menu_path: '/system/users',
      assigned: true,
      has_data_scope: true,
      data_scopes: [
        { resource_type: '业务对象', permissions: [{ level: 'read' }, { level: 'write' }, { level: 'manage' }] }
      ],
      required_permissions: [
        { code: 'user:create', label: '创建用户', granted: true, source: 'auto' },
        { code: 'user:read', label: '查看用户', granted: true, source: 'auto' },
        { code: 'user:update', label: '编辑用户', granted: true, source: 'auto' },
        { code: 'user:delete', label: '删除用户', granted: true, source: 'manual' }
      ]
    },
    {
      menu_code: 'role_management',
      display_name: '角色管理',
      menu_path: '/system/roles',
      assigned: true,
      has_data_scope: false,
      data_permission_hint: { resource_types: ['角色', '权限分配'] },
      required_permissions: [
        { code: 'role:create', label: '创建角色', granted: true, source: 'auto' },
        { code: 'role:read', label: '查看角色', granted: true, source: 'auto' },
        { code: 'role:update', label: '编辑角色', granted: false, source: 'manual' }
      ]
    },
    {
      menu_code: 'config_management',
      display_name: '系统配置',
      menu_path: '/system/config',
      assigned: false,
      has_data_scope: false,
      data_permission_hint: { resource_types: ['系统参数'] },
      required_permissions: [
        { code: 'config:read', label: '查看配置', granted: false, source: '' },
        { code: 'config:update', label: '修改配置', granted: false, source: '' }
      ]
    },
    {
      menu_code: 'audit_log',
      display_name: '审计日志',
      menu_path: '/system/audit',
      assigned: false,
      has_data_scope: false,
      required_permissions: [
        { code: 'audit:read', label: '查看日志', granted: false, source: '' }
      ]
    }
  ],
  conditionRules: [
    {
      id: 1,
      resource_type: 'business_object',
      condition: 'domain_id = 5 AND status = "active"',
      friendly_condition: '仅允许访问"产品研发"领域下的活跃业务对象',
      permission_level: 'read',
      inherit_to_children: true,
      is_denied: false
    },
    {
      id: 2,
      resource_type: 'annotation',
      condition: 'created_by = current_user()',
      friendly_condition: '仅允许访问自己创建的备注/标注（完全管理权限）',
      permission_level: 'manage',
      inherit_to_children: false,
      is_denied: false
    },
    {
      id: 3,
      resource_type: 'sensitive_config',
      condition: 'classification = "confidential"',
      friendly_condition: '禁止访问机密级别的敏感配置项',
      permission_level: 'none',
      inherit_to_children: false,
      is_denied: true
    }
  ],
  auditLogs: [
    { id: 1, action: 'UPDATE', entity_type: 'role', user_name: '张三', created_at: '2026-05-13 10:30:00', detail: '修改了权限配置' },
    { id: 2, action: 'ASSIGN', entity_type: 'role', user_name: '李四', created_at: '2026-05-12 14:20:00', detail: '分配了菜单权限' },
    { id: 3, action: 'CREATE', entity_type: 'role', user_name: '王五', created_at: '2026-05-11 09:15:00', detail: '创建了条件规则' }
  ]
})

const expandedMenus = ref(new Set(['user_management']))
const showAddConditionDialog = ref(false)

const permissionFieldDefs = computed(() => ({
  name: { label: '角色名称', type: 'text', editable: false },
  code: { label: '角色编码', type: 'text', editable: false },
  description: { label: '描述', type: 'textarea', editable: false }
}))

const permissionSectionsConfig = [
  {
    key: 'basic',
    label: '基本信息',
    icon: 'info',
    type: 'standard',
    fieldGroups: [
      {
        title: '角色标识',
        icon: 'tag',
        layout: 'grid-2',
        fields: ['name', 'code']
      },
      {
        title: '描述信息',
        icon: 'file-text',
        layout: 'grid-1',
        fields: ['description']
      }
    ]
  },
  {
    key: 'permissions',
    label: '权限配置',
    icon: 'lock',
    type: 'custom'
  },
  {
    key: 'audit-log',
    label: '操作日志',
    icon: 'history',
    type: 'custom'
  }
]

// 计算属性：统计信息
const permissionDemoComputed = computed(() => ({
  totalMenuCount: permissionDemo.value.menus.length,
  assignedMenuCount: permissionDemo.value.menus.filter(m => m.assigned).length,
  totalFuncPermissions: permissionDemo.value.menus.reduce((sum, m) =>
    sum + (m.required_permissions?.length || 0), 0)
}))

Object.assign(permissionDemo.value, permissionDemoComputed.value)

// 权限配置相关方法
function toggleMenuPermission(menu) {
  menu.assigned = !menu.assigned
  if (menu.assigned) {
    expandedMenus.value.add(menu.menu_code)
    menu.required_permissions?.forEach(p => {
      p.granted = true
      p.source = 'auto'
    })
  } else {
    menu.required_permissions?.forEach(p => {
      p.granted = false
      p.source = ''
    })
  }
}

function toggleMenuExpand(menu) {
  if (expandedMenus.value.has(menu.menu_code)) {
    expandedMenus.value.delete(menu.menu_code)
  } else {
    expandedMenus.value.add(menu.menu_code)
  }
  expandedMenus.value = new Set(expandedMenus.value)
}

function selectAllMenus() {
  permissionDemo.value.menus.forEach(m => {
    m.assigned = true
    m.required_permissions?.forEach(p => {
      p.granted = true
      p.source = 'auto'
    })
  })
}

function clearAllMenus() {
  permissionDemo.value.menus.forEach(m => {
    m.assigned = false
    m.required_permissions?.forEach(p => {
      p.granted = false
      p.source = ''
    })
  })
  expandedMenus.value.clear()
}

async function savePermissions() {
  permissionDemo.value.saving = true
  setTimeout(() => {
    const count = permissionDemo.value.menus.filter(m => m.assigned).length
    message.success(`权限保存成功！已分配 ${count} 个菜单`)
    permissionDemo.value.saving = false
  }, 1000)
}

function allCapsGranted(menu) {
  return menu.required_permissions?.every(p => p.granted)
}

function grantedCapCount(menu) {
  if (!menu.required_permissions) return 0
  return menu.required_permissions.filter(p => p.granted).length
}

function getPermLevelLabel(level) {
  const labels = { none: '无权限', read: '只读', write: '可编辑', manage: '完全管理' }
  return labels[level] || level
}

async function removeConditionRule(rule) {
  const confirmed = await message.confirm({ title: '确认删除', message: `确定要删除条件规则 "${rule.condition}" 吗？`, type: 'danger' });
  if (!confirmed) return;
  const idx = permissionDemo.value.conditionRules.indexOf(rule)
  if (idx > -1) {
    permissionDemo.value.conditionRules.splice(idx, 1)
  }
}

// [OK] 新增：数据范围配置（与 RoleDetailDrawer.vue 一致）
function showScopeConfigTip(menu, scope) {
  message.info(`配置 ${menu.display_name} 的 ${scope.resource_type} 数据范围`)
}

// [OK] 新增：数据权限建议提示（与 RoleDetailDrawer.vue 一致）
function openDataScopeForMenu(menu) {
  const hintTypes = menu.data_permission_hint?.resource_types || []
  message.info(`为 ${menu.display_name} 配置数据权限：${hintTypes.join(', ')}`)
}

function handlePermissionTabChange(tabKey) {
  console.log('[Permission Demo] Tab 切换:', tabKey)
  if (tabKey === 'audit-log') {
    console.log('[Permission Demo] 加载操作日志...')
  }
}

const permissionYamlConfig = `# role-permission-detail.yaml (页面配置层 - 声明式定义)
detailPage:
  objectType: "role"
  
  sections:
    - key: "basic"
      label: "基本信息"
      icon: "info"
      fieldGroups:
        - title: "角色标识"
          layout: "grid-2"
          fields: [name, code]
        - title: "描述信息"
          layout: "grid-1"
          fields: [description]
    
    - key: "permissions"
      label: "权限配置"
      icon: "lock"
      type: "custom"                    # Custom Slot 模式
    
    - key: "audit-log"
      label: "操作日志"
      icon: "history"
      type: "custom"                    # Custom Slot 模式

# 架构说明：
# - 基本信息：使用 YAML 驱动的 FieldGroup 渲染器（80% 标准化）
# - 权限配置：使用 Custom Slot 渲染 PermissionConfigPanel（20% 定制化）
# - 操作日志：使用 Custom Slot 复用 AuditLog 通用组件`

const yamlConfigText = `# object-definitions/product.yaml (Schema层 - 单一定义)
product:
  label: "产品"
  fields:
    name:       { label: "产品名称", type: "text", required: true }
    code:       { label: "产品编码", type: "text", required: true }
    type:       { label: "产品类型", type: "select", options: [...] }
    status:     { label: "状态", type: "select", options: [...] }
    # ... 共24个字段，此处省略 ...

# page-definitions/product-detail.yaml (页面配置层 - 只声明展示行为)
detailPage:
  objectType: "product"
  navigation: "tabs"

  tabs:
    - key: "basic"
      label: "基本信息"
      fieldGroups:
        - title: "标识信息"
          layout: "grid-4"
          fields: [name, code, type, status]
        - title: "组织信息"
          layout: "grid-4"
          fields: [department, manager, createdAt, effectiveDate]
        - title: "扩展属性"
          collapsed: true               # 渐进式披露
          layout: "grid-4"
          fields: [description, version, tags, priority, approver, source]

    - key: "tech"
      label: "技术参数"
      fieldGroups:
        - title: "技术规格"
          layout: "grid-4"
          fields: [techStack, database, deployMode, concurrentUsers]
        - title: "性能指标"
          layout: "grid-3"
          fields: [responseTime, availability, dataVolume]

    - key: "commercial"
      label: "商务条款"
      fieldGroups:
        - title: "价格信息"
          layout: "grid-3"
          fields: [basePrice, discountRate, taxRate]
        - title: "合同信息"
          layout: "grid-3"
          fields: [contractNo, contractTerm, renewalType]

    - key: "compliance"
      label: "合规审查"
      visibleWhen:                      # 条件可见性
        field: "riskLevel"
        operator: "equals"
        value: "high"
      fieldGroups:
        - title: "审查信息"
          layout: "grid-3"
          fields: [reviewer, reviewDate, reviewResult, rectifyDeadline]

    - key: "custom"
      label: "价格模拟器"
      type: "custom"                    # Custom Slot
      component: "PricingSimulator"`

function toggleRole(role, selected) {
  if (selected) {
    if (!selectedRoleIds.value.includes(role.id)) {
      selectedRoleIds.value.push(role.id)
    }
  } else {
    selectedRoleIds.value = selectedRoleIds.value.filter(id => id !== role.id)
  }
}

function removeRole(role) {
  selectedRoleIds.value = selectedRoleIds.value.filter(id => id !== role.id)
}

function saveRoles() {
  ElMessage.success(`已保存 ${selectedRoleIds.value.length} 个角色`)
  showRoleDialog.value = false
}

// 产品-版本 CRUD 方法
const showProductDialog = ref(false)
const editingProduct = ref(null)
const productForm = ref({ name: '', code: '', description: '' })

function editProduct(product) {
  editingProduct.value = product
  productForm.value = {
    name: product.name,
    code: product.code || '',
    description: product.description || ''
  }
  showProductDialog.value = true
}

function saveProduct() {
  if (!productForm.value.name) {
    ElMessage.warning('请输入产品名称')
    return
  }
  if (editingProduct.value) {
    // 编辑模式
    editingProduct.value.name = productForm.value.name
    ElMessage.success('产品已更新')
  } else {
    // 新建模式
    const newProduct = {
      id: Date.now(),
      name: productForm.value.name,
      versions: []
    }
    demoProducts.value.push(newProduct)
    ElMessage.success('产品已创建')
  }
  showProductDialog.value = false
  editingProduct.value = null
}

const showVersionDialog = ref(false)
const editingVersion = ref(null)
const versionForm = ref({ name: '', status: 'active', created: '' })

function editVersion(version) {
  editingVersion.value = version
  versionForm.value = {
    name: version.name,
    status: version.status,
    created: version.created
  }
  showVersionDialog.value = true
}

function saveVersion() {
  if (!versionForm.value.name) {
    ElMessage.warning('请输入版本号')
    return
  }
  if (editingVersion.value) {
    // 编辑模式
    editingVersion.value.name = versionForm.value.name
    editingVersion.value.status = versionForm.value.status
    editingVersion.value.created = versionForm.value.created
    ElMessage.success('版本已更新')
  } else {
    // 新建模式
    const newVersion = {
      id: Date.now(),
      name: versionForm.value.name,
      status: versionForm.value.status,
      created: versionForm.value.created || new Date().toISOString().split('T')[0]
    }
    selectedProduct.value?.versions.push(newVersion)
    ElMessage.success('版本已创建')
  }
  showVersionDialog.value = false
  editingVersion.value = null
}

function deleteVersion(version) {
  ElMessageBox.confirm('确定要删除该版本吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    const versions = selectedProduct.value?.versions || []
    const index = versions.findIndex(v => v.id === version.id)
    if (index > -1) {
      versions.splice(index, 1)
      if (selectedVersion.value?.id === version.id) {
        selectedVersion.value = null
      }
      ElMessage.success('版本已删除')
    }
  }).catch(() => {})
}

function deleteProduct(product) {
  ElMessageBox.confirm(`确定要删除产品"${product.name}"吗？该操作将同时删除所有版本。`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    const index = demoProducts.value.findIndex(p => p.id === product.id)
    if (index > -1) {
      demoProducts.value.splice(index, 1)
      if (selectedProduct.value?.id === product.id) {
        selectedProduct.value = null
        selectedVersion.value = null
      }
      ElMessage.success('产品已删除')
    }
  }).catch(() => {})
}

const customDatetime = ref('')
const elementDatetime = ref('')
const customInput = ref('')
const elementInput = ref('')
const customPassword = ref('')
const elementPassword = ref('')
const customSelect = ref('')
const elementSelect = ref('')
const customPage = ref(1)
const elementPage = ref(1)
const elementPageSize = ref(10)
const showCustomModal = ref(false)
const showElementDialog = ref(false)
const customTab = ref('user')
const elementTab = ref('user')
const elementCollapse = ref(['1'])
const showCustomDrawer = ref(false)
const showElementDrawer = ref(false)
const customNav = ref('home')
const showCustomConfirm = ref(false)
const customEnum = ref('')
const elementEnum = ref('')
const customSearchHelp = ref('')
const searchHelpFilter = ref('')
const showSearchHelpDialog = ref(false)
const showCustomMetaDialog = ref(false)
const showElementMetaDialog = ref(false)
const showCustomDrawer2 = ref(false)
const customDateRange = ref(['', ''])
const elementDateRange = ref([])
const metaFormData = ref({ name: '', type: '' })
const elementForm = ref({ name: '', type: '' })
const elementFilterForm = ref({ type: '', dateRange: [] })

// 未使用组件的响应式变量
const switchValue1 = ref(true)
const switchValue2 = ref(false)
const sliderValue = ref(40)
const radioValue = ref('1')
const checkboxValue = ref([])
const inputNumberValue = ref(1)
const dateValue = ref('')
const timeValue = ref('')
const cascaderValue = ref('')
const transferValue = ref([])
const rateValue = ref(3)
const colorValue = ref('#ea580c')
const dialogVisible = ref(false)
const dialogYonDesign = ref(false)
const drawerYonDesign = ref(false)
const drawerVisible = ref(false)
const tabValue = ref('1')
const segmentValue = ref('选项1')

// 级联选择器选项
const cascaderOptions = [
  {
    value: 'zhejiang',
    label: '浙江',
    children: [
      { value: 'hangzhou', label: '杭州' },
      { value: 'ningbo', label: '宁波' }
    ]
  }
]

// 穿梭框数据
const transferData = ref([
  { key: 1, label: '选项1' },
  { key: 2, label: '选项2' },
  { key: 3, label: '选项3' },
  { key: 4, label: '选项4' },
  { key: 5, label: '选项5' }
])

// 树形数据
const treeData = ref([
  {
    label: '根节点',
    children: [
      { label: '子节点1' },
      { label: '子节点2' }
    ]
  }
])

const selectOptions = [
  { label: '选项一', value: '1' },
  { label: '选项二', value: '2' },
  { label: '选项三', value: '3' },
]

const tabsOptions = [
  { key: 'user', label: '用户管理' },
  { key: 'config', label: '配置管理' },
  { key: 'role', label: '角色管理' },
]

const navItems = [
  { key: 'home', label: '首页', icon: 'search' },
  { key: 'users', label: '用户', icon: 'arrow-right' },
  { key: 'settings', label: '设置', icon: 'close' },
]

const enumOptions = [
  { label: '活跃', value: 'active', color: '#67c23a' },
  { label: '停用', value: 'inactive', color: '#f56c6c' },
  { label: '待审', value: 'pending', color: '#e6a23c' },
]

const searchHelpOptions = [
  { label: '项目A', value: 'a' },
  { label: '项目B', value: 'b' },
  { label: '项目C', value: 'c' },
]

const filterFields = [
  { key: 'type', label: '类型', type: 'select', options: [{ label: '创建', value: 'create' }, { label: '更新', value: 'update' }] },
  { key: 'date_range', label: '时间范围', type: 'datetime-range', placeholder: ['开始', '结束'] },
]

const metaTableColumns = [
  { key: 'name', label: '名称' },
  { key: 'status', label: '状态' },
  { key: 'date', label: '日期' },
]

const metaTableData = [
  { name: '对象A', status: '活跃', date: '2025-01-01' },
  { name: '对象B', status: '停用', date: '2025-02-01' },
]

const metaFormFields = [
  { key: 'name', label: '名称', type: 'text', required: true },
  { key: 'type', label: '类型', type: 'select', options: [{ label: '类型A', value: 'a' }, { label: '类型B', value: 'b' }] },
]

const auditLogs = [
  { id: 1, created_at: '2025-05-09 10:00', user_name: '管理员', action: 'update', field_name: '名称', old_value: '旧值', new_value: '新值' },
  { id: 2, created_at: '2025-05-09 09:00', user_name: '管理员', action: 'create', field_name: null, old_value: null, new_value: null },
]

const datetimeShortcuts = [
  { text: '今天', value: new Date() },
  { text: '昨天', value: () => { const d = new Date(); d.setTime(d.getTime() - 3600 * 1000 * 24); return d } },
  { text: '一周前', value: () => { const d = new Date(); d.setTime(d.getTime() - 3600 * 1000 * 24 * 7); return d } },
]

// Message 函数
function showMessage(type) {
  ElMessage({
    message: '这是一条' + (type === 'success' ? '成功' : type === 'warning' ? '警告' : '信息') + '消息',
    type: type,
  })
}

// MessageBox 函数
function showConfirm() {
  ElMessageBox.confirm('确定要执行此操作吗？', '确认', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => {
    ElMessage({ message: '操作已确认', type: 'success' })
  }).catch(() => {
    ElMessage({ message: '操作已取消', type: 'info' })
  })
}

// Notification 函数
function showNotification(type) {
  ElNotification({
    title: '通知标题',
    message: '这是一条通知消息内容',
    type: type,
  })
}

const tableDataPreview = [
  { name: '张三', status: '活跃' },
  { name: '李四', status: '停用' },
]

const elementFormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

const filteredSearchHelp = computed(() => {
  if (!searchHelpFilter.value) return searchHelpOptions
  return searchHelpOptions.filter(o => o.label.includes(searchHelpFilter.value))
})

const handleSearchHelpSelect = (row) => {
  if (row) { customSearchHelp.value = row.value; showSearchHelpDialog.value = false }
}

const handleFilterSearch = () => {}
const handleFilterReset = () => {}

const openElMessageBox = () => {
  ElMessageBox.confirm('确定要删除吗？', '确认', { type: 'warning' })
}

const summaryData = [
  { name: 'DateTimePicker', lines: '~600行', epComponent: 'el-date-picker', compare: 'EP远超', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'AppButton', lines: '~200行', epComponent: 'el-button', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppInput', lines: '~300行', epComponent: 'el-input', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppSelect', lines: '~500行', epComponent: 'el-select', compare: 'EP远超', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'AppModal', lines: '~250行', epComponent: 'el-dialog', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppTabs', lines: '~400行', epComponent: 'el-tabs', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppAlert', lines: '~100行', epComponent: 'el-alert', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppCard', lines: '~150行', epComponent: 'el-card', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppCollapse', lines: '~200行', epComponent: 'el-collapse', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppIcon', lines: '~100行', epComponent: '@element-plus/icons-vue', compare: 'EP远超(287+图标)', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'Pagination', lines: '~300行', epComponent: 'el-pagination', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'Drawer', lines: '~200行', epComponent: 'el-drawer', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AppSideNav', lines: '~300行', epComponent: 'el-menu', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'EmptyState', lines: '~100行', epComponent: 'el-empty', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'ConfirmDialog', lines: '~150行', epComponent: 'ElMessageBox', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'EnumSelect', lines: '~200行', epComponent: 'el-select(自定义模板)', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'EnumSearchHelp', lines: '~250行', epComponent: 'el-dialog+el-table', compare: 'EP组合更强', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'FilterBar', lines: '~400行', epComponent: 'el-form(行内)', compare: 'EP组合更强', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE][DECORATIVE]' },
  { name: 'MetaTable', lines: '~500行', epComponent: 'el-table', compare: 'EP远超', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'MetaForm', lines: '~400行', epComponent: 'el-form', compare: 'EP远超', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'MetaDialog', lines: '~300行', epComponent: 'el-dialog+el-form', compare: 'EP更强', level: 'superior', difficulty: '[DECORATIVE][DECORATIVE]' },
  { name: 'AppHeader', lines: '~100行', epComponent: 'el-page-header', compare: 'EP更完善', level: 'superior', difficulty: '[DECORATIVE]' },
  { name: 'AuditLog', lines: '~400行', epComponent: 'el-timeline(组合)', compare: '业务组件，需组合', level: 'equal', difficulty: '[DECORATIVE][DECORATIVE][DECORATIVE]' },
  { name: 'MasterDetailLayout', lines: '~300行', epComponent: 'el-container(组合)', compare: '布局组件，需组合', level: 'equal', difficulty: '[DECORATIVE][DECORATIVE][DECORATIVE]' },
  { name: 'ObjectPage', lines: '~400行', epComponent: '多组件组合', compare: '业务组件，需组合', level: 'equal', difficulty: '[DECORATIVE][DECORATIVE][DECORATIVE]' },
]

const missingForm = [
  { name: 'Checkbox', tag: '复选框', desc: '多选框，支持全选、半选、禁用', demoText: '[DECORATIVE] [DECORATIVE] [DECORATIVE]' },
  { name: 'Radio', tag: '单选框', desc: '单选框，支持按钮样式、边框', demoText: '◉ ○ ○' },
  { name: 'Switch', tag: '开关', desc: '开关选择器，支持文字、颜色自定义', demoText: 'ON/OFF' },
  { name: 'Slider', tag: '滑块', desc: '滑块选择器，支持范围选择、标记', demoText: '━━━●━━━━' },
  { name: 'TimePicker', tag: '时间选择器', desc: '时间选择，支持固定/任意时间', demoText: '12:30:00' },
  { name: 'TimeSelect', tag: '时间选择', desc: '固定时间点选择', demoText: '08:00 / 09:00 / 10:00' },
  { name: 'Cascader', tag: '级联选择', desc: '级联选择器，支持多选、搜索', demoText: '省 > 市 > 区' },
  { name: 'Transfer', tag: '穿梭框', desc: '双栏穿梭选择框', demoText: '[左侧] ↔ [右侧]' },
  { name: 'InputNumber', tag: '数字输入', desc: '数字输入框，支持步进、精度', demoText: '[-] 100 [+]' },
  { name: 'Rate', tag: '评分', desc: '评分组件，支持半选、自定义图标', demoText: '[DECORATIVE][DECORATIVE][DECORATIVE][DECORATIVE][SYMBOL]' },
  { name: 'ColorPicker', tag: '颜色选择', desc: '颜色选择器，支持透明度、预设色', demoText: '[DESIGN]' },
  { name: 'Upload', tag: '上传', desc: '文件上传，支持拖拽、多文件、裁剪', demoText: '[SYMBOL] 点击或拖拽上传' },
  { name: 'Autocomplete', tag: '自动补全', desc: '输入建议，支持远程搜索、自定义模板', demoText: '输入 → 建议列表', new: true },
  { name: 'InputTag', tag: '标签输入', desc: '标签输入框，支持回车创建标签', demoText: '标签1 × | 标签2 × |', new: true },
  { name: 'Mention', tag: '提及', desc: '@提及功能，支持自定义建议、快捷键', demoText: '@用户 输入@触发', new: true },
  { name: 'InputOTP', tag: '验证码输入', desc: '验证码/OTP输入，支持粘贴、自动聚焦', demoText: '[6][_][_][_][_][_]', new: true },
  { name: 'VirtualizedSelect', tag: '虚拟选择', desc: '大数据量虚拟滚动选择器，万级数据流畅', demoText: '10,000+ 选项...', new: true },
]

const missingData = [
  { name: 'Tag', tag: '标签', desc: '标签，支持关闭、动态编辑、不同类型', demoText: '标签1 ×  标签2 ×' },
  { name: 'Badge', tag: '徽章', desc: '徽章数字/小红点，支持最大值、自定义', demoText: '消息 [CRITICAL]5' },
  { name: 'Avatar', tag: '头像', desc: '头像，支持图片、图标、文字', demoText: '[SYMBOL]' },
  { name: 'Progress', tag: '进度条', desc: '进度条，支持环形、仪表盘、自定义', demoText: '██████░░ 75%' },
  { name: 'Skeleton', tag: '骨架屏', desc: '骨架屏加载占位，支持动画、组合', demoText: '▓▓▓▓░░░░' },
  { name: 'Timeline', tag: '时间线', desc: '时间线，支持自定义节点、时间戳', demoText: '●───●───●' },
  { name: 'Tree', tag: '树形控件', desc: '树形控件，支持搜索、拖拽、虚拟滚动', demoText: '├─ 节点1\n├─ 节点2\n│  └─ 子节点' },
  { name: 'TreeSelect', tag: '树选择', desc: '树形选择器，支持搜索、多选', demoText: '▼ 选择节点...' },
  { name: 'Statistic', tag: '统计数值', desc: '统计数值展示，支持动画、前缀后缀', demoText: '¥ 128,900' },
  { name: 'Descriptions', tag: '描述列表', desc: '列表描述信息，支持边框、对齐', demoText: '名称: xxx\n状态: 活跃' },
  { name: 'Result', tag: '结果页', desc: '操作结果反馈，支持图标、子标题', demoText: '[OK] 提交成功' },
  { name: 'Calendar', tag: '日历', desc: '日历组件，支持自定义内容、范围', demoText: '[SYMBOL] 2025年5月', new: true },
  { name: 'Carousel', tag: '轮播', desc: '走马灯/轮播，支持指示器、自动播放', demoText: '◀ [幻灯片1] ▶', new: true },
  { name: 'Image', tag: '图片', desc: '图片预览，支持大图查看、懒加载', demoText: '[SYMBOL]️ 点击查看大图', new: true },
  { name: 'Tour', tag: '漫游引导', desc: '新手引导，高亮元素+步骤说明', demoText: '① 点击这里 → ② 然后...', new: true },
  { name: 'Segmented', tag: '分段控制器', desc: '分段选择器，类似iOS分段控件', demoText: '日 | 周 | 月', new: true },
  { name: 'VirtualizedTable', tag: '虚拟表格', desc: '大数据量虚拟滚动表格，万行流畅', demoText: '10,000+ 行数据...', new: true },
  { name: 'VirtualizedTree', tag: '虚拟树', desc: '大数据量虚拟滚动树，万节点流畅', demoText: '10,000+ 节点...', new: true },
  { name: 'InfiniteScroll', tag: '无限滚动', desc: '列表无限滚动加载指令', demoText: '↓ 滚动加载更多...', new: true },
]

const missingNav = [
  { name: 'Breadcrumb', tag: '面包屑', desc: '面包屑导航，支持分隔符自定义', demoText: '首页 / 产品 / 详情' },
  { name: 'Dropdown', tag: '下拉菜单', desc: '下拉菜单，支持指令式、分割按钮', demoText: '更多操作 ▼' },
  { name: 'Steps', tag: '步骤条', desc: '步骤条，支持描述、图标、竖向', demoText: '①→②→③' },
  { name: 'Affix', tag: '固钉', desc: '固定在页面指定位置', demoText: '[固定元素]' },
  { name: 'Anchor', tag: '锚点', desc: '锚点导航，支持滚动高亮', demoText: '目录1 → 目录2 → 目录3' },
  { name: 'Backtop', tag: '回到顶部', desc: '回到顶部按钮，支持自定义图标、阈值', demoText: '⬆ 回到顶部', new: true },
]

const missingFeedback = [
  { name: 'Message', tag: '消息提示', desc: '轻量级全局提示，支持多种类型', demoText: 'ℹ️ 操作成功' },
  { name: 'Notification', tag: '通知', desc: '通知提醒框，支持位置、HTML', demoText: '[SYMBOL] 您有新消息' },
  { name: 'Popover', tag: '弹出框', desc: '弹出信息框，支持触发方式、内容', demoText: '[悬停弹出]' },
  { name: 'Tooltip', tag: '文字提示', desc: '文字提示，支持主题、位置', demoText: '[悬停提示]' },
  { name: 'Popconfirm', tag: '确认弹出', desc: '气泡确认框，轻量级确认', demoText: '[点击确认删除?]' },
  { name: 'Loading', tag: '加载', desc: '加载指令/服务，支持全屏、区域、自定义', demoText: '⏳ 加载中...', new: true },
]

const missingOther = [
  { name: 'Divider', tag: '分割线', desc: '分割线，支持文字、垂直', demoText: '───── 分割 ─────' },
  { name: 'Watermark', tag: '水印', desc: '页面水印，支持文字、图片、角度', demoText: 'CONFIDENTIAL' },
  { name: 'Splitter', tag: '分割面板', desc: '可拖拽分割面板，支持多区域、折叠', demoText: '左面板 | 右面板', new: true },
]
</script>

<style scoped>
.component-comparison {
  max-width: 1400px;
  margin: 0 auto;
  padding: 40px 20px;
  padding-bottom: 100px;
  background: var(--color-bg-layout, #f5f7fa);
}
.page-header { text-align: center; margin-bottom: 32px; }
.page-header h1 { font-size: 32px; color: var(--color-text-primary, #1d2129); margin-bottom: 8px; }
.subtitle { font-size: 18px; color: var(--color-text-secondary, #86909c); }

/* Tab 导航样式 */
.comparison-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 32px;
  padding: 16px 24px;
  background: var(--color-bg-container, #fff);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.tab-btn {
  padding: 10px 24px;
  font-size: 15px;
  font-weight: 500;
  border: 2px solid var(--el-border-color, #e5e6eb);
  background: white;
  color: var(--color-text-secondary, #86909c);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.tab-btn:hover {
  border-color: var(--el-color-primary-light-5, #fdba74);
  color: var(--el-color-primary, #ea580c);
}
.tab-btn.active {
  background: var(--el-color-primary, #ea580c);
  border-color: var(--el-color-primary, #ea580c);
  color: white;
}
.tab-content {
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.stats-bar {
  display: flex; justify-content: center; gap: 40px; margin-bottom: 40px;
  padding: 24px; background: var(--color-bg-container, #fff);
  border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.stat-item { text-align: center; }
.stat-number { display: block; font-size: 28px; font-weight: 700; color: var(--color-primary, #165dff); }
.stat-label { font-size: 13px; color: var(--color-text-secondary, #86909c); }
.comparison-section {
  margin-bottom: 48px; background: var(--color-bg-container, #fff);
  border-radius: 8px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.comparison-section h2 {
  font-size: 20px; color: var(--color-text-primary, #1d2129);
  margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid var(--color-border, #e5e6eb);
}
.comparison-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
.comparison-item {
  border: 1px solid var(--color-border, #e5e6eb); border-radius: 8px;
  padding: 20px; background: var(--color-bg-primary, #fff);
}
.ep-yondesign-item {
  border: 2px solid var(--el-color-primary-light-5);
  background: linear-gradient(135deg, #fff7ed 0%, #fff 100%);
  position: relative;
}
.ep-yondesign-item::before {
  content: '[DECORATIVE] YonDesign';
  position: absolute;
  top: -10px;
  right: 12px;
  font-size: 10px;
  padding: 2px 8px;
  background: var(--el-color-primary);
  color: white;
  border-radius: 4px;
}
.ep-yondesign-item h3 {
  color: var(--el-color-primary);
}
.comparison-item h3 {
  font-size: 16px; color: var(--color-text-primary, #1d2129);
  margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--color-border-light, #f2f3f5);
}
.component-demo {
  margin-bottom: 16px; padding: 16px; background: var(--color-bg-secondary, #f7f8fa);
  border-radius: 6px; min-height: 60px;
}
.value-display {
  margin-top: 8px; padding: 6px 10px; background: var(--color-bg-primary, #fff);
  border-radius: 4px; font-size: 13px; color: var(--color-text-secondary, #86909c); font-family: monospace;
}
.component-info { font-size: 13px; color: var(--color-text-secondary, #86909c); }
.component-info ul { list-style: none; padding: 0; margin: 6px 0; }
.component-info li { padding: 2px 0; }
.code-lines { margin-top: 8px; font-weight: 600; color: var(--color-text-primary, #1d2129); }
.btn-row { display: flex; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.icon-row { display: flex; gap: 16px; align-items: center; }
.badge-business {
  font-size: 12px; padding: 2px 8px; border-radius: 4px;
  background: #e8f3ff; color: #165dff; vertical-align: middle; margin-left: 8px;
}
.badge-deprecated {
  font-size: 12px; padding: 2px 8px; border-radius: 4px;
  background: #fff3e8; color: #ff7d00; vertical-align: middle; margin-left: 8px;
}
.summary-section {
  background: var(--color-bg-container, #fff); border-radius: 8px;
  padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.summary-section h2 { font-size: 20px; color: var(--color-text-primary, #1d2129); margin-bottom: 20px; }
.comparison-table { width: 100%; border-collapse: collapse; }
.comparison-table th, .comparison-table td {
  padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--color-border, #e5e6eb); font-size: 13px;
}
.comparison-table th { background: var(--color-bg-secondary, #f7f8fa); font-weight: 600; color: var(--color-text-primary, #1d2129); }
.comparison-table td { color: var(--color-text-secondary, #86909c); }
.total-row { background: var(--color-bg-secondary, #f7f8fa); }
.text-green { color: #00b42a !important; font-weight: 600; }
.text-yellow { color: #ff7d00 !important; }
.text-red { color: #f53f3f !important; }
.missing-section {
  background: var(--color-bg-container, #fff); border-radius: 8px;
  padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 48px;
}
.missing-section h2 { font-size: 20px; color: var(--color-text-primary, #1d2129); margin-bottom: 8px; }
.section-desc { font-size: 14px; color: var(--color-text-secondary, #86909c); margin-bottom: 24px; }
.missing-grid { display: flex; flex-direction: column; gap: 24px; }
.missing-category h3 { font-size: 16px; color: var(--color-text-primary, #1d2129); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border, #e5e6eb); }
.missing-items { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.missing-item {
  border: 1px solid var(--color-border, #e5e6eb); border-radius: 6px;
  padding: 12px; background: var(--color-bg-primary, #fff); transition: box-shadow 0.2s;
}
.missing-item:hover { box-shadow: 0 2px 12px rgba(22,93,255,0.12); }
.missing-item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.missing-name { font-size: 14px; font-weight: 600; color: var(--color-text-primary, #1d2129); }
.missing-tag { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: #e8f3ff; color: #165dff; }
.missing-tag-new { font-size: 10px; padding: 1px 5px; border-radius: 3px; background: #fff3e8; color: #ff7d00; font-weight: 600; }
.missing-desc { font-size: 12px; color: var(--color-text-secondary, #86909c); margin-bottom: 8px; line-height: 1.4; }
.missing-demo { padding: 8px; background: var(--color-bg-secondary, #f7f8fa); border-radius: 4px; text-align: center; }
.demo-placeholder { font-size: 12px; color: var(--color-text-tertiary, #c9cdd4); font-family: monospace; white-space: pre-line; }
@media (max-width: 1200px) { .comparison-grid { grid-template-columns: 1fr 1fr; } .stats-bar { flex-wrap: wrap; gap: 20px; } .missing-items { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); } }
@media (max-width: 768px) { .comparison-grid { grid-template-columns: 1fr; } }

/* ==================== 圆润风格预览样式 ==================== */
.rounded-preview-section {
  margin-bottom: 48px;
  background: linear-gradient(135deg, #fff7ed 0%, #fff 50%, #fff7ed 100%);
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 4px 16px rgba(234, 88, 12, 0.08);
  border: 2px solid var(--el-color-primary-light-5);
}

.rounded-preview-section > h2 {
  font-size: 24px;
  color: var(--el-color-primary);
  margin-bottom: 16px;
}

.preview-intro {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  margin-bottom: 24px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border-left: 4px solid var(--el-color-primary);
  line-height: 1.6;
}

.rounded-comparison {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.rounded-group {
  background: rgba(255, 255, 255, 0.6);
  border-radius: 8px;
  padding: 20px;
  border: 1px solid var(--el-border-color-lighter);
}

.rounded-group h3 {
  font-size: 16px;
  color: var(--el-text-color-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--el-border-color-light);
}

.rounded-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.rounded-item {
  padding: 16px;
  background: var(--el-bg-color);
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.rounded-item h4 {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  font-weight: 500;
}

.rounded-demo {
  padding: 16px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  min-height: 50px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.rounded-info {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-tertiary);
  font-weight: 600;
}

/* ==================== Link 按钮 (Material Design) 样式 ==================== */
.link-button-section {
  background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%);
  border: 2px solid #fb923c;
  border-radius: 8px;
  padding: 24px;
  margin-top: 24px;
}

.link-intro {
  background: white;
  padding: 16px;
  border-radius: 6px;
  border-left: 4px solid #ea580c;
  margin-bottom: 20px;
  line-height: 1.8;
  font-size: 14px;
}

.link-intro strong {
  color: #ea580c;
  font-size: 15px;
}

.link-demo-container {
  margin-top: 16px;
}

.link-states-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.link-state-item {
  background: white;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  transition: box-shadow 0.2s ease;
}

.link-state-item:hover {
  box-shadow: 0 4px 12px rgba(234, 88, 12, 0.1);
}

.link-state-item h4 {
  color: #ea580c;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #fef3c7;
}

.link-state-demo {
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  min-height: 44px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

/* 模拟 Hover 状态 */
.hover-simulation .simulated-hover,
.simulated-hover {
  background: rgba(234, 88, 12, 0.06) !important;
}

/* 模拟 Focus 状态 */
.focus-simulation .simulated-focus,
.simulated-focus {
  background: rgba(234, 88, 12, 0.12) !important;
  outline: 2px dashed #ea580c;
  outline-offset: 2px;
}

/* 模拟 Active 状态 */
.active-simulation .simulated-active,
.simulated-active {
  background: rgba(234, 88, 12, 0.16) !important;
  transform: scale(0.98);
  transition: all 0.1s ease;
}

.state-specs {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
}

.spec-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.spec-label {
  color: #6b7280;
  font-weight: 500;
  min-width: 60px;
}

.spec-value {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f3f4f6;
}

.color-orange {
  color: #ea580c;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.bg-opacity-6 {
  color: #92400e;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.bg-opacity-12 {
  color: #92400e;
  background: #ffedd5;
  border: 1px solid #fdba74;
}

.bg-opacity-16 {
  color: #7c2d12;
  background: #fed7aa;
  border: 1px solid #fb923c;
}

.opacity-highlight {
  color: #ea580c;
  font-weight: 700;
  font-size: 13px;
}

.spec-remark {
  color: #059669;
  font-size: 11px;
  font-style: italic;
}

/* 核心优势说明 */
.link-advantages {
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border: 2px solid #10b981;
  border-radius: 8px;
  padding: 20px;
  margin-top: 24px;
}

.link-advantages h4 {
  color: #047857;
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 12px;
}

.advantages-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px;
}

.advantages-list li {
  padding: 10px 12px;
  background: white;
  border-radius: 6px;
  border-left: 3px solid #10b981;
  font-size: 13px;
  line-height: 1.6;
}

.advantages-list li strong {
  color: #047857;
}

/* 实际应用场景示例 */
.link-real-world-example {
  background: white;
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 20px;
  margin-top: 24px;
}

.link-real-world-example h4 {
  color: #374151;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.mini-table th,
.mini-table td {
  padding: 10px 12px;
  text-align: left;
  border: 1px solid #e5e7eb;
}

.mini-table th {
  background: #f9fafb;
  font-weight: 600;
  color: #374151;
}

.mini-table tbody tr:hover {
  background: #fef3c7;
}

.action-cell {
  display: flex;
  gap: 4px;
  align-items: center;
}

.example-note {
  margin-top: 12px;
  padding: 10px;
  background: #fef3c7;
  border-left: 3px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  font-style: italic;
}

/* ==================== Filled 按钮（实心按钮）样式 ==================== */
.filled-button-section {
  background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%);
  border: 2px solid #ea580c;
  border-radius: 8px;
  padding: 24px;
  margin-top: 24px;
}

.filled-intro {
  background: white;
  padding: 16px;
  border-radius: 6px;
  border-left: 4px solid #ea580c;
  margin-bottom: 20px;
  line-height: 1.8;
  font-size: 14px;
}

.filled-intro strong {
  color: #ea580c;
  font-size: 15px;
}

.filled-demo-container {
  margin-top: 16px;
}

.filled-type-group {
  background: white;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  border: 1px solid #e5e7eb;
}

.filled-type-group h4 {
  color: #ea580c;
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid #fef3c7;
}

.filled-states-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.filled-state-item {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  transition: box-shadow 0.2s ease;
}

.filled-state-item:hover {
  box-shadow: 0 4px 12px rgba(234, 88, 12, 0.08);
}

.filled-state-item h5 {
  color: #374151;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px dashed #d1d5db;
}

.filled-state-demo {
  padding: 16px;
  background: white;
  border-radius: 6px;
  min-height: 50px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
}

/* 模拟 Primary 按钮 Hover 状态 */
.simulated-hover-primary {
  background-color: #fb923c !important;
  border-color: #fb923c !important;
  color: #ffffff !important;
}

/* 模拟 Primary 按钮 Active 状态 */
.simulated-active-primary {
  background-color: #c2410c !important;
  border-color: #c2410c !important;
  color: #ffffff !important;
  transform: scale(0.98);
  transition: all 0.1s ease;
}

.filled-other-types {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.type-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.type-label {
  font-weight: 600;
  color: #374151;
  min-width: 70px;
  font-size: 13px;
}

.type-spec {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 4px 8px;
  border-radius: 4px;
}

/* 颜色标记类 */
.color-white {
  color: #374151;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
}

.color-light-orange {
  color: #c2410c;
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.color-dark-orange {
  color: #ffffff;
  background: #c2410c;
  border: 1px solid #9a3412;
}

.contrast-good {
  color: #059669;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.contrast-excellent {
  color: #047857;
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  font-weight: 700;
}

/* 核心优势说明 */
.filled-advantages {
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border: 2px solid #10b981;
  border-radius: 8px;
  padding: 20px;
  margin-top: 24px;
}

.filled-advantages h4 {
  color: #047857;
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 12px;
}

/* 圆润风格改造效果 */
.rounded-item.rounded {
  position: relative;
}

.rounded-item.rounded::before {
  content: '[DECORATIVE] 圆润';
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 10px;
  padding: 2px 6px;
  background: var(--el-color-primary);
  color: white;
  border-radius: 4px;
  z-index: 1;
}

/* 按钮圆润化 */
.rounded-item.rounded .el-button {
  border-radius: 6px !important;
}

.rounded-item.rounded .el-button--primary,
.rounded-item.rounded .el-button--success,
.rounded-item.rounded .el-button--danger,
.rounded-item.rounded .el-button--warning {
  border-radius: 6px !important;
}

/* 输入框圆润化 */
.rounded-item.rounded .el-input__wrapper {
  border-radius: 6px !important;
}

/* 选择器圆润化 */
.rounded-item.rounded .el-select__wrapper {
  border-radius: 6px !important;
}

/* 标签圆润化 */
.rounded-item.rounded .el-tag {
  border-radius: 4px !important;
}

/* 卡片圆润化 */
.rounded-item.rounded .el-card {
  border-radius: 8px !important;
}

/* 分页圆润化 */
.rounded-item.rounded .el-pager li {
  border-radius: 4px !important;
}

.rounded-item.rounded .el-pagination button {
  border-radius: 4px !important;
}

/* 表格圆润化 */
.rounded-item.rounded .el-table {
  border-radius: 6px !important;
  overflow: hidden;
}

.rounded-item.rounded .el-table__header th.el-table__cell {
  background-color: var(--el-color-primary-light-9) !important;
  border-radius: 0 !important;
}

/* 表格内按钮也圆润 */
.rounded-item.rounded .el-table .el-button {
  border-radius: 4px !important;
}

/* 改造说明样式 */
.rounded-summary {
  margin-top: 24px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border: 1px dashed var(--el-color-primary-light-5);
}

.rounded-summary h3 {
  font-size: 16px;
  color: var(--el-color-primary);
  margin-bottom: 12px;
}

.rounded-summary p {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
}

.rounded-summary code {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.rounded-vars {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.var-item {
  background: var(--el-bg-color);
  padding: 12px 16px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-light);
}

.var-item code {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.var-item strong {
  color: var(--el-color-primary);
  font-size: 14px;
}

/* ==================== 未使用组件预览样式 ==================== */
.unused-preview-section {
  margin-top: 32px;
  background: linear-gradient(135deg, #f0fdf4 0%, #fff 50%, #f0fdf4 100%);
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 4px 16px rgba(22, 163, 74, 0.08);
  border: 2px solid #86efac;
}

.unused-preview-section > h2 {
  font-size: 24px;
  color: #16a34a;
  margin-bottom: 16px;
}

.unused-preview-section .preview-intro {
  border-left-color: #16a34a;
  background: rgba(22, 163, 74, 0.05);
}

.unused-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
  margin-top: 24px;
}

.unused-item {
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 20px;
  border: 1px solid var(--el-border-color-lighter);
  transition: all 0.2s ease;
}

.unused-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.unused-item h3 {
  font-size: 16px;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.unused-item .component-showcase {
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  min-height: 80px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: center;
}

.unused-item .component-showcase .el-button {
  border-radius: 6px;
}

.unused-item .component-showcase .el-input__wrapper {
  border-radius: 6px;
}

.unused-item .component-showcase .el-tag {
  border-radius: 4px;
}

.unused-item .component-showcase .el-switch {
  border-radius: 12px;
}

.unused-item .component-desc {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

/* ==================== Element Plus 对比表格样式 ==================== */
.ep-comparison-table {
  margin-top: 24px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.ep-comparison-header {
  display: grid;
  grid-template-columns: 200px 1fr 1fr;
  gap: 1px;
  background: var(--el-border-color-lighter);
  font-weight: 600;
  font-size: 14px;
}

.ep-comparison-header > div {
  padding: 14px 16px;
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-primary);
}

.ep-col-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ep-col-name strong {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.ep-col-name span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ep-col-standard,
.ep-col-yondesign {
  background: var(--el-bg-color);
  padding: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-start;
}

.ep-col-standard {
  background: #fafafa;
}

.ep-col-yondesign {
  background: linear-gradient(135deg, #fff7ed 0%, #fff 100%);
  border-left: 2px solid var(--el-color-primary-light-5);
}

.ep-comparison-row {
  display: grid;
  grid-template-columns: 200px 1fr 1fr;
  gap: 1px;
  background: var(--el-border-color-lighter);
  border-top: 1px solid var(--el-border-color-lighter);
}

.ep-comparison-row:first-of-type {
  border-top: none;
}

.ep-comparison-row > div {
  background: var(--el-bg-color);
  padding: 12px 16px;
}

/* ==================== 圆润+yondesign 样式类 ==================== */

/* 基础圆润 */
.ep-rounded {
  border-radius: 6px !important;
}

/* 按钮圆润 */
.ep-rounded.el-button {
  border-radius: 6px !important;
}

/* 标签圆润 */
.ep-rounded-tag {
  border-radius: 4px !important;
}

/* 卡片圆润 */
.ep-rounded-card {
  border-radius: 8px !important;
}

/* 进度条 - 使用主题色 */
.ep-progress {
  --el-progress-primary-color: var(--el-color-primary) !important;
}

/* 头像圆润 */
.ep-rounded-avatar {
  border-radius: var(--el-border-radius-round, 50%) !important;
}

/* 开关圆润 */
.ep-rounded-switch {
  --el-switch-on-color: var(--el-color-primary) !important;
  border-radius: 12px !important;
}

/* 滑块 - 使用主题色 */
.ep-slider {
  --el-slider-main-bg-color: var(--el-color-primary) !important;
}

/* 单选框圆润 */
.ep-rounded-radio {
  border-radius: 4px !important;
}

/* 多选框圆润 */
.ep-rounded-checkbox {
  border-radius: 4px !important;
}

/* 输入框/选择器圆润 */
.ep-rounded.el-input__wrapper,
.ep-rounded.el-select__wrapper {
  border-radius: 6px !important;
}

/* 分页圆润 */
.ep-rounded-pagination .el-pager li {
  border-radius: 4px !important;
}

.ep-rounded-pagination .el-pagination button {
  border-radius: 4px !important;
}

/* 表格圆润 */
.ep-rounded-table {
  border-radius: 6px !important;
  overflow: hidden;
}

.ep-rounded-table .el-table__header th.el-table__cell {
  background-color: var(--el-color-primary-light-9) !important;
}

/* 标签页圆润 */
.ep-rounded-tabs .el-tabs__item {
  border-radius: 6px 6px 0 0 !important;
}

/* 步骤条圆润 */
.ep-rounded-steps .el-step__title {
  border-radius: 4px !important;
}

/* 树形控件圆润 */
.ep-rounded-tree .el-tree-node__content {
  border-radius: 4px !important;
}

/* 导航菜单圆润 */
.ep-rounded-menu .el-menu-item {
  border-radius: 6px !important;
}

/* 下拉菜单圆润 */
.ep-rounded-dropdown {
  border-radius: 6px !important;
}

.ep-rounded-dropdown-item {
  border-radius: 4px !important;
}

/* 骨架屏圆润 */
.ep-rounded-skeleton .el-skeleton__item {
  border-radius: 4px !important;
}

/* 空状态圆润 */
.ep-rounded-empty {
  border-radius: 8px !important;
}

/* 结果页圆润 */
.ep-rounded-result {
  border-radius: 8px !important;
}

/* 时间线圆润 */
.ep-rounded-timeline .el-timeline-item__node {
  border-radius: 50% !important;
}

/* 描述列表圆润 */
.ep-rounded-descriptions {
  border-radius: 6px !important;
  overflow: hidden;
}

/* 日历圆润 */
.ep-rounded-calendar {
  border-radius: 8px !important;
  overflow: hidden;
}

.ep-rounded-calendar .el-calendar-table td.is-today {
  background-color: var(--el-color-primary-light-9) !important;
  color: var(--el-color-primary) !important;
}

/* 图片圆润 */
.ep-rounded-image {
  border-radius: 6px !important;
}

/* 链接圆润 */
.ep-rounded-link {
  border-radius: 4px !important;
}

/* 间距圆润 */
.ep-rounded-space {
  border-radius: 6px !important;
}

/* 统计数值圆润 */
.ep-rounded-statistic {
  border-radius: 8px !important;
  padding: 16px;
  background: var(--el-color-primary-light-9);
}

/* 段落选择圆润 */
.ep-rounded-segment {
  border-radius: 6px !important;
}

/* 二维码圆润 - 需要安装 element-plus qrcode 扩展组件
.ep-rounded-qrcode {
  border-radius: 6px !important;
  padding: 8px;
  background: white;
  border: 1px solid var(--el-color-primary-light-5);
}
*/

/* 弹窗圆润 */
.ep-rounded-dialog {
  border-radius: 8px !important;
}

.ep-rounded-dialog .el-dialog {
  border-radius: 8px !important;
}

.ep-rounded-dialog .el-dialog__header {
  border-radius: 8px 8px 0 0 !important;
}

.ep-rounded-dialog .el-dialog__body {
  border-radius: 0 !important;
}

.ep-rounded-dialog .el-dialog__footer {
  border-radius: 0 0 8px 8px !important;
}

/* 弹窗按钮圆润 */
.ep-rounded-dialog .el-button {
  border-radius: 6px !important;
}

/* 抽屉圆润 */
.ep-rounded-drawer {
  border-radius: 8px 0 0 8px !important;
}

.ep-rounded-drawer .el-drawer {
  border-radius: 8px 0 0 8px !important;
}

.ep-rounded-drawer .el-drawer__header {
  border-radius: 8px 0 0 0 !important;
}

.ep-rounded-drawer .el-drawer__body {
  border-radius: 0 !important;
}

.ep-rounded-drawer .el-drawer__footer {
  border-radius: 0 0 0 8px !important;
}

.ep-rounded-drawer .el-button {
  border-radius: 6px !important;
}

/* ==================== 页面组件模式样式 ==================== */
.page-patterns-section {
  margin-top: 32px;
}

.page-patterns-section h2 {
  font-size: 24px;
  color: var(--el-text-color-primary);
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--el-color-primary);
}

.page-patterns-section .preview-intro {
  background: var(--el-color-primary-light-9);
  padding: 16px;
  border-radius: 6px;
  border-left: 4px solid var(--el-color-primary);
  margin-bottom: 24px;
  line-height: 1.8;
}

.page-patterns-section .preview-intro code {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
  padding: 2px 6px;
  border-radius: 4px;
}

.pattern-group {
  background: var(--el-bg-color-page);
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.pattern-group h3 {
  font-size: 18px;
  color: var(--el-text-color-primary);
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.pattern-diagram {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.diagram-box {
  flex: 1;
  min-width: 300px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 20px;
  border: 2px solid var(--el-border-color-lighter);
}

.diagram-box.recommended {
  border-color: var(--el-color-primary-light-3);
  background: linear-gradient(135deg, #fff7ed 0%, #fff 100%);
}

.diagram-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.recommended .diagram-title {
  color: var(--el-color-primary);
}

.arrow {
  font-size: 24px;
  color: var(--el-color-primary);
  font-weight: bold;
}

.current-implementation {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.impl-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.impl-item span:first-of-type {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  border-radius: 4px;
  margin-left: auto;
}

.badge.success {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.problem-tag {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding: 12px;
  background: #fef2f2;
  border-radius: 6px;
  color: #dc2626;
  font-size: 13px;
  font-weight: 500;
}

.solution-component {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: white;
  border-radius: 6px;
  border: 2px solid var(--el-color-primary-light-3);
  margin-bottom: 16px;
}

.solution-component span:first-of-type {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.solution-features {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.feature {
  padding: 8px 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.solution-modes {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mode-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.mode-label {
  font-weight: 600;
  color: var(--el-color-primary);
  min-width: 80px;
}

.mode-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 组件分层架构样式 */
.layer-architecture {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.layer-item {
  padding: 20px;
  border-radius: 8px;
  border: 2px solid;
}

.layer-page {
  background: linear-gradient(135deg, #fff7ed 0%, #fff 100%);
  border-color: var(--el-color-primary);
}

.layer-business {
  background: linear-gradient(135deg, #ecfdf5 0%, #fff 100%);
  border-color: #10b981;
}

.layer-base {
  background: linear-gradient(135deg, #f0f9ff 0%, #fff 100%);
  border-color: #0ea5e9;
}

.layer-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.layer-page .layer-title { color: var(--el-color-primary); }
.layer-business .layer-title { color: #047857; }
.layer-base .layer-title { color: #0369a1; }

.layer-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}

.layer-components {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.layer-components .more {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.layer-arrow {
  text-align: center;
  font-size: 20px;
  color: var(--el-text-color-secondary);
  padding: 4px 0;
}

/* 实施路线图样式 */
.roadmap {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.roadmap-item {
  padding: 20px;
  border-radius: 8px;
  border-left: 4px solid;
}

.roadmap-item.phase1 {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.roadmap-item.phase2 {
  background: #ecfdf5;
  border-color: #10b981;
}

.roadmap-item.phase3 {
  background: #f0f9ff;
  border-color: #0ea5e9;
}

.phase-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 4px;
  margin-bottom: 12px;
}

.phase1 .phase-badge {
  background: var(--el-color-primary);
  color: white;
}

.phase2 .phase-badge {
  background: #10b981;
  color: white;
}

.phase3 .phase-badge {
  background: #0ea5e9;
  color: white;
}

.phase-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
}

.phase-tasks {
  list-style: none;
  padding: 0;
  margin: 0;
}

.phase-tasks li {
  padding: 6px 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  border-bottom: 1px dashed var(--el-border-color-lighter);
}

.phase-tasks li:last-child {
  border-bottom: none;
}

/* ==================== 页面组件模式 - 实际演示样式 ==================== */
.live-demo-container {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 16px;
}

.demo-layout {
  display: grid;
  grid-template-columns: 200px 1fr 300px;
  gap: 16px;
  min-height: 400px;
  overflow-x: auto;
}

@media (max-width: 1200px) {
  .demo-layout {
    grid-template-columns: 180px 1fr 280px;
  }
}

@media (max-width: 992px) {
  .demo-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
  }

  .demo-tree-panel,
  .demo-master-panel,
  .demo-detail-panel {
    max-height: 300px;
  }
}

.panel-header {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  padding: 12px 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px 6px 0 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.panel-content {
  background: white;
  border-radius: 0 0 6px 6px;
  padding: 12px;
  min-height: 350px;
}

.panel-content.scrollable {
  overflow-y: auto;
  max-height: 500px;
}

.panel-content.empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 树形节点 */
.demo-tree-panel {
  display: flex;
  flex-direction: column;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
  color: var(--el-text-color-regular);
  min-width: 0;
}

.tree-node:hover {
  background: var(--el-fill-color-light);
}

.tree-node.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 500;
}

.tree-node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.tree-node-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.tree-node:hover .tree-node-actions {
  opacity: 1;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

/* 表格 */
.demo-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 300px;
}

.demo-table th,
.demo-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--el-border-color-lighter);
  white-space: nowrap;
}

.demo-table th {
  font-weight: 600;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lightest);
  position: sticky;
  top: 0;
  z-index: 1;
}

.demo-table tbody {
  display: block;
  max-height: 400px;
  overflow-y: auto;
}

.demo-table thead,
.demo-table tbody {
  width: 100%;
}

.demo-table tr {
  display: table;
  width: 100%;
  table-layout: fixed;
  cursor: pointer;
  transition: all 0.2s;
}

.demo-table tbody tr:hover {
  background: var(--el-fill-color-light);
}

.demo-table tr.active {
  background: var(--el-color-primary-light-9);
}

/* 详情面板 */
.demo-detail-panel {
  display: flex;
  flex-direction: column;
}

.detail-row {
  display: flex;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.detail-label {
  min-width: 80px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.detail-value {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

/* 关联关系演示 */
.demo-association {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 20px;
  align-items: start;
  overflow-x: auto;
}

@media (max-width: 768px) {
  .demo-association {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .association-actions {
    padding-top: 0;
    justify-content: center;
  }
}

.association-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.association-panel.available .panel-header {
  background: var(--el-color-success-light-9);
}

.association-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 6px;
  margin-bottom: 8px;
  border: 1px solid var(--el-border-color-lighter);
  min-width: 0;
}

.association-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  overflow: hidden;
}

.association-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.association-code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-hint {
  text-align: center;
  padding: 40px;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

.association-actions {
  display: flex;
  align-items: center;
  padding-top: 80px;
}

/* 弹窗内容 */
.role-dialog-content {
  max-height: 400px;
  overflow-y: auto;
}

.role-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-dialog-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  transition: all 0.2s;
}

.role-dialog-item:hover {
  background: var(--el-fill-color-light);
}

.role-dialog-item.selected {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-3);
}

/* 模式说明 */
.pattern-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  background: var(--el-color-primary-light-9);
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.pattern-note strong {
  color: var(--el-color-primary);
}

/* 简化版分层架构 */
.layer-demo {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.layer-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 8px;
  border: 2px solid;
}

.layer-page {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.layer-business {
  background: #ecfdf5;
  border-color: #10b981;
}

.layer-base {
  background: #f0f9ff;
  border-color: #0ea5e9;
}

.layer-label {
  font-weight: 600;
  font-size: 14px;
  min-width: 100px;
}

.layer-page .layer-label { color: var(--el-color-primary); }
.layer-business .layer-label { color: #047857; }
.layer-base .layer-label { color: #0369a1; }

.layer-components {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  flex: 1;
}

.layer-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 150px;
}

.more-tags {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

/* ==================== 复杂对象表单样式 ==================== */
.complex-form-section {
  margin-bottom: 48px;
}

/* Schema 面板 */
.schema-panel {
  background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
  border: 2px solid #3b82f6;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 32px;
}

.schema-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  background: rgba(59, 130, 246, 0.08);
  border-bottom: 1px solid #bfdbfe;
  font-weight: 600;
  font-size: 14px;
  color: #1e40af;
}

.schema-body {
  padding: 16px 20px;
}

.schema-stats {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #64748b;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.schema-stats strong {
  color: #1e40af;
}

.stat-divider {
  color: #cbd5e1;
}

.schema-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.schema-col {
  background: white;
  border-radius: 6px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
}

.schema-col-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f1f5f9;
}

.schema-field {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 12px;
}

.sf-name {
  font-family: 'Courier New', monospace;
  color: #0f172a;
  font-weight: 500;
}

.sf-type {
  color: #64748b;
  font-size: 11px;
  padding: 1px 5px;
  background: #f1f5f9;
  border-radius: 3px;
}

.sf-required {
  color: #ef4444;
  font-weight: 700;
}

.sf-conditional {
  color: #f59e0b;
  font-size: 10px;
  padding: 1px 4px;
  background: #fef3c7;
  border-radius: 3px;
}

/* Detail Tab 导航栏 (使用 el-tabs 全局组件) */
.detail-demo-tabs {
  margin-bottom: 0;
}

.detail-demo-tabs .el-tabs__header {
  background: var(--el-bg-color);
  border-radius: 8px 8px 0 0;
  padding: 0 16px;
}

.detail-demo-tabs .el-tabs__nav-wrap::after {
  display: none;
}

.detail-tabs-content {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-top: none;
  border-radius: 0 0 8px 8px;
}

.detail-tabs-content {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-top: none;
  border-radius: 0 0 8px 8px;
}

.detail-tab-panel {
  padding: 20px;
}

/* FieldGroup（基于 AppCard 组件） */
.detail-tab-panel .app-card {
  margin-bottom: 16px;
}

.app-card--dashed {
  border-style: dashed !important;
  background: #fafbfc;
}

.collapsible-group .app-card__header {
  cursor: pointer;
  user-select: none;
}

.collapse-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.collapse-hint {
  font-size: 12px;
  color: var(--color-primary);
  font-weight: 500;
  cursor: pointer;
}

.fg-body {
  padding: 16px;
  display: grid;
  gap: 16px;
}

.fg-grid-2 { grid-template-columns: repeat(2, 1fr); }
.fg-grid-3 { grid-template-columns: repeat(3, 1fr); }
.fg-grid-4 { grid-template-columns: repeat(4, 1fr); }

.fg-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fg-field label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.fg-field.fg-span-2 {
  grid-column: span 2;
}

.fg-field-highlight {
  background: #fffbeb;
  padding: 8px;
  border-radius: 6px;
  border: 1px dashed #f59e0b;
}

.required-mark {
  color: #ef4444;
  font-weight: 700;
}

.fg-computed-row {
  padding: 12px 16px;
  background: #fffbeb;
  border-top: 1px solid #fde68a;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.computed-label {
  color: #92400e;
  font-weight: 600;
}

.computed-value {
  color: #ea580c;
  font-weight: 700;
  font-family: 'Courier New', monospace;
  font-size: 16px;
}

.computed-note {
  color: #a8a29e;
  font-size: 12px;
}

/* 条件可见性横幅 */
.conditional-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #92400e;
}

/* Custom Slot */
.custom-slot-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #ecfdf5;
  border: 1px solid #6ee7b7;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #047857;
}

.custom-slot-demo {
  background: white;
  border-radius: 8px;
  padding: 20px;
}

.custom-slot-demo h4 {
  font-size: 16px;
  color: #047857;
  margin-bottom: 8px;
}

.custom-slot-desc {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e5e7eb;
}

/* 模拟器网格 */
.simulator-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1.2fr;
  gap: 16px;
}

.sim-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.sim-card-title {
  padding: 10px 14px;
  background: #f1f5f9;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  border-bottom: 1px solid #e2e8f0;
}

.sim-card-body {
  padding: 14px;
}

.sim-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  font-size: 13px;
  color: #475569;
}

.sim-row + .sim-row {
  border-top: 1px solid #f1f5f9;
}

.sim-row.sim-total {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 2px solid #e2e8f0;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.sim-value {
  font-family: 'Courier New', monospace;
  color: #334155;
  font-weight: 500;
}

.sim-value.total {
  color: #ea580c;
  font-size: 18px;
}

/* 柱状图 */
.sim-bar-chart {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sim-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sim-bar-label {
  font-size: 12px;
  color: #64748b;
  min-width: 45px;
}

.sim-bar-track {
  flex: 1;
  height: 12px;
  background: #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
}

.sim-bar-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.3s ease;
}

.sim-bar-fill.license { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.sim-bar-fill.impl { background: linear-gradient(90deg, #10b981, #34d399); }
.sim-bar-fill.train { background: linear-gradient(90deg, #f59e0b, #fbbf24); }

.sim-bar-pct {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  min-width: 32px;
  text-align: right;
}

/* YAML 展示 */
.yaml-display {
  background: #1e293b;
  border-radius: 8px;
  padding: 20px;
  overflow-x: auto;
}

.yaml-display pre {
  margin: 0;
  padding: 0;
}

.yaml-display code {
  font-family: 'Courier New', Consolas, monospace;
  font-size: 13px;
  line-height: 1.7;
  color: #e2e8f0;
}

/* 设计要点总结 */
.design-points {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.design-point {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  transition: box-shadow 0.2s ease;
}

.design-point:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.design-point strong {
  font-size: 14px;
  color: #0f172a;
  display: block;
  margin-bottom: 4px;
}

.design-point p {
  font-size: 13px;
  color: #64748b;
  margin: 0;
  line-height: 1.5;
}

/* ==================== ObjectPage 演示容器样式 ==================== */
.objectpage-demo-container {
  border: 2px solid #10b981;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.1);
  min-height: 500px;
}

.objectpage-demo-container .object-page {
  height: 100%;
}

@media (max-width: 900px) {
  .fg-grid-4 { grid-template-columns: repeat(2, 1fr); }
  .fg-grid-3 { grid-template-columns: repeat(2, 1fr); }
  .simulator-grid { grid-template-columns: 1fr; }
  .schema-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ==================== 权限配置页面演示样式 ==================== */
.permission-demo {
  border-color: #f59e0b !important;
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.15) !important;
}

.permission-config-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  padding: var(--spacing-md) 0;
}

.perm-section {
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border-light);
}

.perm-section h4 {
  margin: 0 0 var(--spacing-md);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.perm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.header-summary {
  display: flex;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.summary-item {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);

  &.assigned {
    background: var(--color-success-bg);
    color: var(--color-success);
  }

  &.func-perm {
    background: #fff7e6;
    color: #fa8c16;
  }
}

.perm-guide {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--yonyou-orange-600, #ea580c);
  line-height: 1.5;
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.menu-card {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
  overflow: hidden;

  &:hover {
    border-color: var(--color-border);
  }

  &.is-assigned {
    border-left: 3px solid var(--yonyou-orange-600, #ea580c);
    background: rgba(234, 88, 12, 0.02);
  }
}

.menu-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);

  input[type='checkbox'] {
    width: 16px;
    height: 16px;
    accent-color: var(--yonyou-orange-600, #ea580c);
    cursor: pointer;
    flex-shrink: 0;
  }
}

.menu-title-area {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
  cursor: pointer;
}

.menu-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
}

.menu-path {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  font-family: monospace;
  opacity: 0.7;
}

.expand-icon {
  font-size: 10px;
  color: var(--color-text-quaternary);
  transition: transform var(--transition-fast);
  flex-shrink: 0;

  &.expanded {
    transform: rotate(90deg);
  }
}

.menu-badges {
  display: flex;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

.badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 500;
  white-space: nowrap;

  &.badge-capability {
    background: #fff7e6;
    color: #fa8c16;

    &.badge-all-granted {
      background: #f6ffed;
      color: #52c41a;
    }
  }

  &.badge-scope {
    background: #e6f7ff;
    color: #1890ff;
  }
}

.menu-card-body {
  padding: var(--spacing-sm) var(--spacing-md) var(--spacing-md) calc(var(--spacing-md) + 20px);
  border-top: 1px solid var(--color-border-light);
  animation: slideDown 0.15s ease;
}

.capability-list {
  margin-bottom: var(--spacing-sm);
}

.capability-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.capability-matrix {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cap-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  font-size: 12px;

  &.cap-granted {
    background: rgba(82, 196, 26, 0.08);
    border: 1px solid rgba(82, 196, 26, 0.2);
  }

  &.cap-pending {
    background: rgba(250, 140, 22, 0.06);
    border: 1px dashed rgba(250, 140, 22, 0.3);
  }

  &.cap-inactive {
    background: var(--color-bg-tertiary);
    opacity: 0.6;
  }
}

.cap-status {
  flex-shrink: 0;
  width: 18px;
  text-align: center;
}

.status-icon {
  font-size: 12px;
  font-weight: bold;

  &.status-pending {
    color: #fa8c16;
  }

  &.status-idle {
    color: #d9d9d9;
  }
}

.cap-label {
  font-weight: 500;
  color: var(--color-text-primary);
  min-width: 70px;
}

.cap-code {
  color: var(--color-text-quaternary);
  font-family: monospace;
  font-size: 11px;
  flex: 1;
}

.data-scope-inline {
  margin-top: var(--spacing-sm);
}

.scope-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.scope-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  margin-bottom: 4px;
}

.scope-type {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.scope-detail {
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex: 1;
}

.menu-actions-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-light);
}

.actions-spacer {
  flex: 1;
}

.condition-section {
  h4 {
    margin-bottom: var(--spacing-sm);
  }

  .section-desc {
    font-size: var(--font-size-xs);
    color: var(--color-text-quaternary);
    font-weight: normal;
    margin-left: var(--spacing-sm);
    margin-bottom: var(--spacing-md);
  }
}

.empty-tip {
  text-align: center;
  color: var(--color-text-quaternary);
  padding: var(--spacing-lg);
  font-size: var(--font-size-sm);
}

.perm-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.perm-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--spacing-sm);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-md);

  &.is-denied {
    border-left: 3px solid var(--color-error);
  }
}

.perm-main {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-xs);
}

.perm-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.perm-condition {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: monospace;
  background: var(--color-bg-layout);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.perm-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.denied-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 10px;
  font-weight: var(--font-weight-medium);
  margin-right: var(--spacing-xs);
}

.perm-level {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);

  &.level-none { background: #f5f5f5; color: #999; }
  &.level-read { background: #e3f2fd; color: #1976d2; }
  &.level-write { background: #fff3e0; color: #f57c00; }
  &.level-manage { background: #fce4ec; color: #c62828; }
}

.inherit-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-success-bg);
  color: var(--color-success);
  margin-left: var(--spacing-xs);
}

.btn {
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);

  &:hover {
    border-color: var(--color-border);
    color: var(--color-text-primary);
  }

  &.btn-primary {
    background: var(--yonyou-orange-600, #ea580c);
    color: white;
    border-color: var(--yonyou-orange-600, #ea580c);

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }
}

.btn-link {
  @include button-link;
  font-size: 11px;
  padding: 0;

  &.danger {
    color: var(--color-error);

    &:hover {
      text-decoration: underline;
    }
  }

  &.btn-xs {
    font-size: 11px;
    padding: 0;
  }
}

@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 400px; }
}

/* [OK] 新增：来源标签系统（与 RoleDetailDrawer.vue 完全一致） */
.cap-source-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
  font-weight: 500;
}

.source-auto {
  background: #e6f7ff;
  color: #1890ff;
}

.source-manual {
  background: #f9f0ff;
  color: #722ed1;
}

.source-pending {
  background: #fff7e6;
  color: #d48806;
}

/* [OK] 新增：数据范围建议提示（与 RoleDetailDrawer.vue 完全一致） */
.data-scope-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: #fffbe6;
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.hint-icon {
  font-size: 12px;
}

/* [OK] 新增：友好条件表达式（与 RoleDetailDrawer.vue 完全一致） */
.perm-friendly {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: 4px;
  padding-left: 4px;
}

/* [OK] 新增：Pulse 动画（与 RoleDetailDrawer.vue 完全一致） */
.cap-pending {
  animation: pulse-orange 1.5s ease infinite;
}

/* ==================== Inline Edit Section Styles ==================== */
.inline-edit-section {
  padding: 0;
}

.inline-edit-section h2 {
  font-size: 24px;
  color: #1d2129;
  margin-bottom: 16px;
}

.inline-edit-section .preview-intro {
  font-size: 15px;
  color: #86909c;
  margin-bottom: 32px;
  line-height: 1.6;
}

/* Quick Edit Demo */
.quick-edit-demo {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  overflow: hidden;
}

.quick-edit-demo .demo-cell {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f2f3f5;
  transition: background-color 0.2s;
}

.quick-edit-demo .demo-cell:last-child {
  border-bottom: none;
}

.quick-edit-demo .demo-cell:hover {
  background: #ecf5ff;
}

.quick-edit-demo .cell-label {
  width: 100px;
  font-size: 13px;
  color: #86909c;
  flex-shrink: 0;
}

.quick-edit-demo .cell-value {
  flex: 1;
  font-size: 14px;
  color: #1d2129;
}

.quick-edit-demo .edit-icon {
  opacity: 0;
  color: var(--el-color-primary, #ea580c);
  cursor: pointer;
  transition: opacity 0.2s;
  margin-left: auto;
}

.quick-edit-demo .demo-cell:hover .edit-icon {
  opacity: 1;
}

/* Direct Edit Demo */
.direct-edit-demo {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  overflow: hidden;
}

.direct-edit-demo .demo-cell {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f2f3f5;
  background: #fff8e6;
}

.direct-edit-demo .demo-cell:last-child {
  border-bottom: none;
}

.direct-edit-demo .cell-label {
  width: 100px;
  font-size: 13px;
  color: #86909c;
  flex-shrink: 0;
}

/* Status Demo */
.status-demo {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-label {
  width: 80px;
  font-size: 12px;
  color: #86909c;
  flex-shrink: 0;
}

.inline-edit-cell {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: all 0.2s;
}

.inline-edit-cell.is-default {
  background: #fff;
  border-color: #e5e6eb;
}

.inline-edit-cell.is-hovered {
  background: var(--color-primary-bg, #fff7ed);
  border-color: var(--el-color-primary, #ea580c);
}

.inline-edit-cell.is-editing {
  background: #fff8e6;
  border-color: #e6a23c;
}

.inline-edit-cell.is-modified {
  background: #f0f9eb;
  border-color: #67c23a;
}

.inline-edit-cell.is-immutable {
  background: #f5f7fa;
  cursor: not-allowed;
  opacity: 0.7;
}

.edit-icon-visible {
  color: var(--el-color-primary, #ea580c);
  cursor: pointer;
}

/* Shortcuts */
.shortcuts-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.shortcut-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
}

.shortcut-item kbd {
  display: inline-block;
  padding: 4px 8px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
  background: #f5f7fa;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  color: #1d2129;
}

.shortcut-item span {
  font-size: 13px;
  color: #86909c;
}

/* Rounded Grid */
.rounded-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.rounded-item {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 12px;
  padding: 20px;
}

.rounded-item h4 {
  font-size: 14px;
  color: #1d2129;
  margin-bottom: 16px;
  font-weight: 600;
}

.mode-description {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f2f3f5;
}

.mode-description p {
  font-size: 12px;
  color: #86909c;
  margin: 0;
  line-height: 1.6;
}

@keyframes pulse-orange {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
