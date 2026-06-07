import express from 'express'
import cors from 'cors'
import dotenv from 'dotenv'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

dotenv.config({ path: join(__dirname, '..', '.env') })

const app = express()
const PORT = 3001

app.use(cors())
app.use(express.json())

const DEEPSEEK_API_KEY = process.env.VITE_DEEPSEEK_API_KEY
const ZHIPU_API_KEY = process.env.VITE_ZHIPU_API_KEY

app.post('/api/deepseek', async (req, res) => {
  const { messages, model = 'deepseek-chat' } = req.body

  try {
    const response = await fetch('https://api.deepseek.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${DEEPSEEK_API_KEY}`
      },
      body: JSON.stringify({ model, messages, stream: false })
    })

    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('DeepSeek API Error:', error)
    res.status(500).json({ error: error.message })
  }
})

app.post('/api/zhipu', async (req, res) => {
  const { messages, model = 'glm-4' } = req.body

  try {
    const response = await fetch('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${ZHIPU_API_KEY}`
      },
      body: JSON.stringify({ model, messages, stream: false })
    })

    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('Zhipu API Error:', error)
    res.status(500).json({ error: error.message })
  }
})

app.listen(PORT, () => {
  console.log(`API Server running at http://localhost:${PORT}`)
  console.log('Proxy endpoints:')
  console.log('  POST /api/deepseek')
  console.log('  POST /api/zhipu')
})
