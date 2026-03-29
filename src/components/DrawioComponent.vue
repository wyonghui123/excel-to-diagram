<template>
  <div class="drawio-container">
    <div v-if="loading" class="loading-message">
      正在加载Draw.io...
    </div>
    <div v-else class="drawio-content">
      <div ref="drawioContainer" class="drawio-area"></div>
    </div>
  </div>
</template>

<script>
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'

export default {
  name: 'DrawioComponent',
  props: {
    diagramData: {
      type: Object,
      default: null
    }
  },
  setup(props) {
    const drawioContainer = ref(null)
    const loading = ref(true)
    let drawioEditor = null
    let initialized = false

    // 生成draw.io XML格式
    const generateDrawioXml = (data) => {
      let xml = '<mxGraphModel dx="1280" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1200" pageHeight="900" math="0" shadow="0">'
      xml += '<root>'
      xml += '<mxCell id="0"/>'
      xml += '<mxCell id="1" parent="0"/>'

      // 分析模块层次结构
      const hierarchy = buildModuleHierarchy(data)
      
      // 计算节点位置
      const nodePositions = calculateNodePositions(hierarchy, data)

      // 添加节点
      if (data && data.nodes) {
        data.nodes.forEach((node) => {
          const pos = nodePositions[node.id]
          const x = pos?.x || 100
          const y = pos?.y || 100
          // 根据节点类型设置不同的样式
          let fillColor = node.itemStyle?.color || '#FF9AA2'
          let style = `rounded=1;whiteSpace=wrap;html=1;fillColor=${fillColor};strokeColor=#333;`
          
          // 为模块节点添加特殊样式
          if (node.category === 'module') {
            style += 'fontStyle=1;'
          }
          
          xml += `<mxCell id="${node.id}" value="${node.name}" style="${style}" vertex="1" parent="1">`
          xml += `<mxGeometry x="${x}" y="${y}" width="180" height="90" as="geometry"/>`
          xml += '</mxCell>'
        })
      }

      // 添加连线
      if (data && data.links) {
        data.links.forEach((link, index) => {
          // 根据关系类型设置不同的样式
          let edgeStyle = 'orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;strokeColor=#666;'
          
          // 为层次关系设置虚线
          if (link.relationType === 'hierarchy') {
            edgeStyle += 'dashed=1;'
          } else if (link.lineStyle?.type === 'dashed') {
            edgeStyle += 'dashed=1;'
          }
          
          // 设置线宽
          if (link.lineStyle?.width) {
            edgeStyle += `strokeWidth=${link.lineStyle.width};`
          }
          
          // 根据关系类型设置不同的箭头
          if (link.relationType === 'hierarchy') {
            edgeStyle += 'endArrow=block;'
          } else if (link.relationType === 'dependency') {
            edgeStyle += 'endArrow=open;'
          } else if (link.relationType === 'inheritance') {
            edgeStyle += 'endArrow=block;'
          }
          
          xml += `<mxCell id="${1000 + index}" value="${link.label}" style="${edgeStyle}" edge="1" parent="1" source="${link.source}" target="${link.target}">`
          xml += '<mxGeometry relative="1" as="geometry"/>'
          xml += '</mxCell>'
        })
      }

      xml += '</root>'
      xml += '</mxGraphModel>'
      return xml
    }

    // 构建模块层次结构
    const buildModuleHierarchy = (data) => {
      const hierarchy = {}
      const nodeMap = {}
      
      // 构建节点映射
      if (data && data.nodes) {
        data.nodes.forEach(node => {
          nodeMap[node.id] = node
        })
      }
      
      // 构建层次结构
      if (data && data.links) {
        data.links.forEach(link => {
          if (link.relationType === 'hierarchy') {
            const parentId = link.source
            const childId = link.target
            
            if (!hierarchy[parentId]) {
              hierarchy[parentId] = []
            }
            hierarchy[parentId].push(childId)
          }
        })
      }
      
      return hierarchy
    }

    // 计算节点位置
    const calculateNodePositions = (hierarchy, data) => {
      const nodePositions = {}
      const levelWidth = 250 // 每层的宽度
      const levelHeight = 150 // 每层的高度
      
      // 找到根节点（没有父节点的模块）
      const rootNodes = []
      if (data && data.nodes) {
        data.nodes.forEach(node => {
          let isRoot = true
          if (data.links) {
            for (const link of data.links) {
              if (link.relationType === 'hierarchy' && link.target === node.id) {
                isRoot = false
                break
              }
            }
          }
          if (isRoot) {
            rootNodes.push(node.id)
          }
        })
      }
      
      // 递归计算位置
      const calculatePosition = (nodeId, level, index) => {
        nodePositions[nodeId] = {
          x: level * levelWidth,
          y: 100 + index * levelHeight
        }
        
        // 计算子节点位置
        if (hierarchy[nodeId]) {
          hierarchy[nodeId].forEach((childId, childIndex) => {
            calculatePosition(childId, level + 1, index * 2 + childIndex)
          })
        }
      }
      
      // 计算根节点位置
      rootNodes.forEach((rootId, index) => {
        calculatePosition(rootId, 0, index)
      })
      
      // 为非层次结构的节点分配位置
      if (data && data.nodes) {
        let nonHierarchyIndex = 0
        data.nodes.forEach(node => {
          if (!nodePositions[node.id]) {
            nodePositions[node.id] = {
              x: 100 + (nonHierarchyIndex % 4) * 200,
              y: 600 + Math.floor(nonHierarchyIndex / 4) * 150
            }
            nonHierarchyIndex++
          }
        })
      }
      
      return nodePositions
    }

    // 初始化draw.io编辑器
    const initDrawioEditor = () => {
      console.log('检查drawioContainer:', drawioContainer.value)
      if (!drawioContainer.value) {
        console.error('drawio容器不存在，稍后重试')
        // 再次尝试初始化
        setTimeout(() => {
          console.log('再次尝试初始化draw.io编辑器')
          if (drawioContainer.value) {
            console.log('drawio容器现在存在了')
            initializeEditor()
          } else {
            console.error('drawio容器仍然不存在，放弃初始化')
            loading.value = false
          }
        }, 500)
        return
      }

      initializeEditor()
    }

    // 实际初始化编辑器的函数
    const initializeEditor = () => {
      console.log('开始初始化draw.io编辑器')
      
      // 直接使用iframe备用方案，避免脚本加载失败的问题
      useIframeFallback()
    }

    // 备用方案：使用iframe加载draw.io
    const useIframeFallback = () => {
      console.log('使用iframe备用方案')
      loading.value = false
      
      // 创建iframe元素
      const iframe = document.createElement('iframe')
      // 直接使用基础URL，避免依赖diagramData
      const baseUrl = 'https://embed.diagrams.net/?ui=sketch&spin=1&modified=unsaved&storage=none'
      if (props.diagramData) {
        const xml = generateDrawioXml(props.diagramData)
        const encodedXml = btoa(unescape(encodeURIComponent(xml)))
        iframe.src = `${baseUrl}&xml=${encodedXml}`
      } else {
        iframe.src = baseUrl
      }
      iframe.width = '100%'
      iframe.height = '100%'
      iframe.frameborder = '0'
      
      // 清空容器并添加iframe
      if (drawioContainer.value) {
        drawioContainer.value.innerHTML = ''
        drawioContainer.value.appendChild(iframe)
        console.log('iframe备用方案已创建')
      }
    }

    // 加载图表数据（iframe版本）
    const loadDiagramData = () => {
      console.log('加载图表数据（iframe版本）')
      if (drawioContainer.value && props.diagramData) {
        // 重新创建iframe以加载新数据
        useIframeFallback()
      }
    }

    // 监听diagramData变化
    watch(
      () => props.diagramData,
      (newData) => {
        console.log('图表数据变化:', newData)
        if (newData) {
          if (initialized && drawioEditor) {
            loadDiagramData()
          } else if (!initialized) {
            console.log('draw.io编辑器尚未初始化，开始初始化')
            initDrawioEditor()
          }
        }
      },
      { deep: true, immediate: true }
    )

    // 组件挂载后初始化
    onMounted(() => {
      console.log('DrawioComponent挂载完成')
      // 使用nextTick确保DOM已经完全渲染
      nextTick(() => {
        console.log('DOM已经完全渲染')
        if (props.diagramData) {
          initDrawioEditor()
        } else {
          console.log('diagramData为null，等待数据加载')
          loading.value = false
        }
      })
    })

    // 组件卸载时清理
    onUnmounted(() => {
      console.log('DrawioComponent卸载')
      if (drawioEditor) {
        try {
          drawioEditor.destroy()
        } catch (error) {
          console.error('销毁draw.io编辑器失败:', error)
        }
      }
    })

    // 导出为图片
    const exportAsImage = () => {
      if (drawioEditor) {
        try {
          drawioEditor.export({ format: 'png' }, (data) => {
            const link = document.createElement('a');
            link.href = data;
            link.download = `diagram-${Date.now()}.png`;
            link.click();
          });
        } catch (error) {
          console.error('导出图片失败:', error);
          // 尝试备用方案
          if (drawioContainer.value.querySelector('iframe')) {
            const iframe = drawioContainer.value.querySelector('iframe');
            iframe.contentWindow.postMessage({ action: 'export', format: 'png' }, '*');
          }
        }
      }
    }

    // 导出为原生格式
    const exportAsNative = () => {
      if (drawioEditor) {
        try {
          drawioEditor.getXml((xml) => {
            const blob = new Blob([xml], { type: 'application/xml' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `diagram-${Date.now()}.drawio`;
            link.click();
          });
        } catch (error) {
          console.error('导出原生格式失败:', error);
        }
      }
    }

    return {
      drawioContainer,
      loading,
      exportAsImage,
      exportAsNative
    }
  }
}
</script>

<style scoped>
.drawio-container {
  width: 100%;
  height: 100%;
  border: 1px solid #ddd;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.drawio-content {
  width: 100%;
  height: 100%;
}

.drawio-area {
  width: 100%;
  height: 100%;
  min-height: 600px;
}

.loading-message {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 16px;
  color: #666;
  font-family: 'Comic Sans MS', Arial, sans-serif;
}
</style>