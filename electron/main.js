const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')

// 保持对window对象的全局引用，如果不这么做的话，当JavaScript对象被
// 垃圾回收的时候，window窗口将会自动关闭
let mainWindow

function createWindow() {
  // 创建浏览器窗口
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 700,
    frame: false, // 无边框窗口，使用自定义标题栏
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    titleBarStyle: 'hidden', // 隐藏默认标题栏
    show: false // 先不显示，等加载完成后再显示
  })

  // 加载应用
  if (process.env.VITE_DEV_SERVER_URL) {
    // 开发环境
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
    mainWindow.webContents.openDevTools()
  } else {
    // 生产环境
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  // 窗口加载完成后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // 当 window 被关闭，这个事件会被触发
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// Electron 会在初始化后并准备创建浏览器窗口时，调用这个函数
app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    // 在 macOS 上，当点击 dock 图标并且没有其他窗口打开时，
    // 通常在应用程序中重新创建一个窗口
    if (mainWindow === null) {
      createWindow()
    }
  })
})

// 当所有窗口都被关闭后退出应用
app.on('window-all-closed', () => {
  // 在 macOS 上，除非用户用 Cmd + Q 确定地退出，
  // 否则绝大部分应用及其菜单栏会保持激活
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// IPC 通信处理
ipcMain.handle('get-app-version', () => {
  return app.getVersion()
})

ipcMain.handle('get-platform', () => {
  return process.platform
})

// 窗口控制
ipcMain.handle('minimize-window', () => {
  if (mainWindow) {
    mainWindow.minimize()
  }
})

ipcMain.handle('maximize-window', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize()
    } else {
      mainWindow.maximize()
    }
  }
})

ipcMain.handle('close-window', () => {
  if (mainWindow) {
    mainWindow.close()
  }
})
