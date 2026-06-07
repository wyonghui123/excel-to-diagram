import { vi } from 'vitest'
import { config } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h } from 'vue'
import ElementPlus from 'element-plus'

// PR-TestFix-15 基础设施：全局 mock @element-plus/icons-vue
// 解决 vitest isolate:false 下跨 spec 污染（No "X" export is defined on mock）
// 覆盖 Element Plus 全部常用 icon 名 + 兜底 Proxy（任意访问都返回 mock）
const ICON_NAMES = [
  'Loading', 'ArrowRight', 'ArrowDown', 'ArrowUp', 'ArrowLeft',
  'Filter', 'Download', 'Upload', 'Search', 'Refresh', 'Plus', 'Edit', 'Delete',
  'Close', 'Check', 'Warning', 'CircleClose', 'InfoFilled', 'QuestionFilled',
  'SuccessFilled', 'Failed', 'Document', 'Folder', 'Setting', 'User', 'Lock',
  'Unlock', 'View', 'Hide', 'Select', 'MoreFilled', 'Star', 'Share',
  'Connection', 'Promotion', 'Operation', 'Histogram', 'DataAnalysis',
  'Bell', 'ChatLineRound', 'Coin', 'CreditCard', 'DataLine', 'DataBoard',
  'Link', 'Position', 'TrendCharts', 'List', 'Menu', 'Notification',
  'Picture', 'Postcard', 'PriceTag', 'Tickets', 'Tools', 'Trophy',
  'VideoCamera', 'Wallet', 'Aim', 'Back', 'Backups', 'Bottom',
  'Briefcase', 'Brush', 'Calendar', 'Camera', 'Cellphone', 'ChatLine',
  'Checked', 'ChromeFilled', 'CircleCheck', 'CirclePlus', 'Clock',
  'Compass', 'CopyDocument', 'Cpu', 'Crop', 'DArrowLeft', 'DArrowRight',
  'DataAnalysis', 'Discount', 'DocumentAdd', 'DocumentChecked', 'DocumentCopy',
  'DocumentDelete', 'DocumentRemove', 'Download', 'Eleme', 'ElemeFilled',
  'Expand', 'Female', 'Files', 'Film', 'Finished', 'FirstAidKit', 'Flag',
  'Fold', 'Food', 'Football', 'FullScreen', 'Goblet', 'GoldMedal', 'Goods',
  'GoodsFilled', 'Grape', 'Grid', 'Headset', 'Help', 'HelpFilled',
  'Histogram', 'HomeFilled', 'Hot', 'House', 'Iphone', 'Key', 'KnifeFork',
  'Lightning', 'Link', 'List', 'Loading', 'Location', 'Lock', 'Magnet',
  'Male', 'MapLocation', 'Medal', 'Menu', 'Message', 'MessageBox',
  'Mic', 'Microphone', 'Money', 'Monitor', 'Moon', 'MoreFilled',
  'Mouse', 'Mute', 'MuteNotification', 'Notebook', 'Notification',
  'Odometer', 'Operation', 'Opportunity', 'Orange', 'Paperclip', 'PartlyCloudy',
  'Pause', 'Phone', 'Picture', 'PictureFilled', 'PictureRounded', 'PieChart',
  'Place', 'Pointer', 'Position', 'Postcard', 'Printer', 'Promotion',
  'QuestionFilled', 'Reading', 'Refresh', 'Right', 'ScaleToOriginal', 'School',
  'Scissor', 'Search', 'Select', 'Sell', 'SemiSelect', 'Service', 'SetUp',
  'Setting', 'Share', 'Ship', 'Shop', 'ShoppingBag', 'ShoppingCart',
  'ShoppingCartFull', 'SilverMedal', 'SoldOut', 'Sort', 'SortDown', 'SortUp',
  'Star', 'StarFilled', 'Stopwatch', 'SuccessFilled', 'Switch', 'SwitchButton',
  'TakeawayBox', 'Ticket', 'Tickets', 'Timer', 'ToiletPaper', 'Tools', 'Top',
  'TopRight', 'Trophy', 'TrendCharts', 'Truck', 'TurnOff', 'Umbrella',
  'Unlock', 'UploadFilled', 'Upload', 'User', 'UserFilled', 'Van',
  'VideoCamera', 'VideoCameraFilled', 'VideoPause', 'VideoPlay', 'View',
  'View', 'Wallet', 'WalletFilled', 'Warning', 'WarningFilled', 'Watch',
  'Watermelon', 'ZoomIn', 'ZoomOut'
]
const _iconMocks = Object.fromEntries(
  ICON_NAMES.map(n => [n, { name: 'MockIcon-' + n, render: () => h('i', { class: 'mock-icon', 'data-icon': n }) }])
)
// 兜底：任何未列出的 icon 名也返回 mock
const _iconProxy = new Proxy(_iconMocks, {
  get(target, prop) {
    if (prop in target) return target[prop]
    if (typeof prop === 'string') {
      const m = { name: 'MockIcon-' + prop, render: () => h('i', { class: 'mock-icon', 'data-icon': prop }) }
      target[prop] = m
      return m
    }
    return undefined
  }
})
vi.mock('@element-plus/icons-vue', () => _iconProxy)

config.global.plugins = [ElementPlus]

config.global.components = {}

global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn()
}))

global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn()
}))

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn()
  }))
})

export function setupPinia() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return pinia
}
