export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { messages, model = 'glm-4' } = req.body

  try {
    const response = await fetch('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.ZHIPU_API_KEY}`
      },
      body: JSON.stringify({
        model,
        messages,
        stream: false
      })
    })

    const data = await response.json()
    res.status(200).json(data)
  } catch (error) {
    console.error('Zhipu API Error:', error)
    res.status(500).json({ error: error.message })
  }
}
