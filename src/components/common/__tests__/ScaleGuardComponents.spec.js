import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ScaleGuardBanner from '../ScaleGuardBanner.vue'
import ScaleGuardDialog from '../ScaleGuardDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('ScaleGuard components', () => {
  it('banner 显示关系/节点数 + 一键折叠按钮 + 可关闭', async () => {
    const w = mount(ScaleGuardBanner, { props: { nodes: 260, relations: 350 } })
    expect(w.text()).toContain('350')
    expect(w.text()).toContain('260')
    expect(w.text()).toContain('折叠到服务模块')
    await w.find('[data-test=fold]').trigger('click')
    expect(w.emitted('fold-to-sm')).toBeTruthy()
    await w.find('[data-test=close]').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('dialog 显示文案 + 两个动作', async () => {
    // el-dialog 用 teleport + 过渡, happy-dom 下内容不落 body; stub 成就地渲染容器
    const w = mount(ScaleGuardDialog, {
      props: { nodes: 500, relations: 700 },
      global: {
        stubs: { 'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' } }
      }
    })
    expect(w.text()).toContain('700')
    await w.find('[data-test=back]').trigger('click')
    expect(w.emitted('back')).toBeTruthy()
    await w.find('[data-test=fold]').trigger('click')
    expect(w.emitted('fold-to-sm')).toBeTruthy()
    w.unmount()
  })
})
