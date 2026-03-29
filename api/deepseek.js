export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { messages, model = 'deepseek-chat' } = req.body

  try {
    const response = await fetch('https://api.deepseek.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.DEEPSEEK_API_KEY}`
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
    console.error('DeepSeek API Error:', error)
    res.status(500).json({ error: error.message })
  }
}
