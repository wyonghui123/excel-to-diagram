import { ref } from 'vue'

export function useExport(containerRef) {
  const showPDFPreview = ref(false)
  const pdfPreviewImage = ref(null)
  const pdfSettings = ref({
    scale: 2,
    pageSize: 'a4',
    orientation: 'portrait',
    format: 'pdf'
  })

  const generatePDFPreview = async () => {
    console.log('=== 生成PDF预览 ===')

    try {
      const html2canvas = (await import('html2canvas')).default

      const wrapper = containerRef.value
      if (!wrapper) {
        console.log('未找到图表容器')
        return
      }

      const originalTransform = wrapper.style.transform
      wrapper.style.transform = 'none'

      const targetScale = Math.max(2, pdfSettings.value.scale)

      const canvas = await html2canvas(wrapper, {
        scale: targetScale,
        useCORS: true,
        allowTaint: true,
        backgroundColor: '#ffffff',
        logging: false,
        windowWidth: wrapper.scrollWidth,
        windowHeight: wrapper.scrollHeight
      })

      wrapper.style.transform = originalTransform

      const pageSizes = {
        a4: { width: 210, height: 297 },
        a3: { width: 297, height: 420 },
        a5: { width: 148, height: 210 },
        letter: { width: 216, height: 279 },
        legal: { width: 216, height: 356 }
      }

      const pageSize = pageSizes[pdfSettings.value.pageSize]
      const isLandscape = pdfSettings.value.orientation === 'landscape'

      const previewCanvas = document.createElement('canvas')
      const ctx = previewCanvas.getContext('2d')

      const maxPreviewWidth = 800
      const maxPreviewHeight = 600

      const actualPageWidth = isLandscape ? pageSize.height : pageSize.width
      const actualPageHeight = isLandscape ? pageSize.width : pageSize.height

      const pageRatio = actualPageHeight / actualPageWidth

      let previewWidth = maxPreviewWidth
      let previewHeight = previewWidth * pageRatio

      if (previewHeight > maxPreviewHeight) {
        previewHeight = maxPreviewHeight
        previewWidth = previewHeight / pageRatio
      }

      previewCanvas.width = previewWidth
      previewCanvas.height = previewHeight

      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, previewWidth, previewHeight)

      const margin = 20
      const availableWidth = previewWidth - margin * 2
      const availableHeight = previewHeight - 30 - margin * 2

      const scaleX = availableWidth / canvas.width
      const scaleY = availableHeight / canvas.height
      const imgScale = Math.min(scaleX, scaleY)

      const drawWidth = canvas.width * imgScale
      const drawHeight = canvas.height * imgScale
      const drawX = margin + (availableWidth - drawWidth) / 2
      const drawY = margin + (availableHeight - drawHeight) / 2

      ctx.drawImage(canvas, drawX, drawY, drawWidth, drawHeight)

      pdfPreviewImage.value = previewCanvas.toDataURL('image/png')
      console.log('PDF预览生成成功')
    } catch (error) {
      console.error('生成PDF预览失败:', error)
    }
  }

  const exportPDF = async () => {
    if (!pdfPreviewImage.value) return

    try {
      const { jsPDF } = await import('jspdf')

      const pageSizes = {
        a4: { width: 210, height: 297 },
        a3: { width: 297, height: 420 },
        a5: { width: 148, height: 210 },
        letter: { width: 216, height: 279 },
        legal: { width: 216, height: 356 }
      }

      const pageSize = pageSizes[pdfSettings.value.pageSize]

      const pdf = new jsPDF({
        orientation: pdfSettings.value.orientation,
        unit: 'mm',
        format: pdfSettings.value.pageSize
      })

      const pageWidth = pdf.internal.pageSize.getWidth()
      const pageHeight = pdf.internal.pageSize.getHeight()

      const imgProps = await new Promise((resolve) => {
        const img = new Image()
        img.onload = () => {
          resolve({ width: img.width, height: img.height })
        }
        img.src = pdfPreviewImage.value
      })

      const imgWidth = pageWidth
      const imgHeight = (imgProps.height * imgWidth) / imgProps.width

      let heightLeft = imgHeight
      let position = 0

      pdf.addImage(pdfPreviewImage.value, 'PNG', 0, position, imgWidth, imgHeight, undefined, 'FAST')
      heightLeft -= pageHeight

      while (heightLeft > 0) {
        position = heightLeft - imgHeight
        pdf.addPage()
        pdf.addImage(pdfPreviewImage.value, 'PNG', 0, position, imgWidth, imgHeight, undefined, 'FAST')
        heightLeft -= pageHeight
      }

      pdf.save(`diagram-${Date.now()}.pdf`)
      console.log('PDF导出完成')
      showPDFPreview.value = false
    } catch (error) {
      console.error('导出PDF失败:', error)
    }
  }

  const exportImage = async (format) => {
    if (!pdfPreviewImage.value) return

    try {
      const mimeType = format === 'png' ? 'image/png' : 'image/jpeg'
      const extension = format === 'png' ? 'png' : 'jpg'

      const link = document.createElement('a')
      link.download = `diagram-${Date.now()}.${extension}`
      link.href = pdfPreviewImage.value
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      console.log(`${format.toUpperCase()}图片导出完成`)
      showPDFPreview.value = false
    } catch (error) {
      console.error(`导出${format.toUpperCase()}图片失败:`, error)
    }
  }

  const openPDFPreview = async () => {
    showPDFPreview.value = true
    pdfPreviewImage.value = null
    await generatePDFPreview()
  }

  const closePDFPreview = () => {
    showPDFPreview.value = false
  }

  return {
    showPDFPreview,
    pdfPreviewImage,
    pdfSettings,
    generatePDFPreview,
    exportPDF,
    exportImage,
    openPDFPreview,
    closePDFPreview
  }
}
