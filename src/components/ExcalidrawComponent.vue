<template>
  <div ref="excalidrawContainer" class="excalidraw-container"></div>
</template>

<script>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import Excalidraw from '@excalidraw/excalidraw'

export default {
  name: 'ExcalidrawComponent',
  props: {
    diagramData: {
      type: Object,
      default: null
    }
  },
  setup(props) {
    const excalidrawContainer = ref(null)

    // 构建层次结构
    const buildHierarchy = (nodes, links) => {
      const nodeMap = new Map()
      const hierarchy = { children: [] }
      const parentMap = new Map()

      // 首先创建所有节点的映射
      nodes.forEach(node => {
        nodeMap.set(node.id, { ...node, children: [] })
      })

      // 构建父子关系
      links.forEach(link => {
        if (link.relationType === 'hierarchy') {
          const parent = nodeMap.get(link.source)
          const child = nodeMap.get(link.target)
          if (parent && child) {
            parent.children.push(child)
            parentMap.set(child.id, parent.id)
          }
        }
      })

      // 找到根节点（没有父节点的节点）
      nodes.forEach(node => {
        if (!parentMap.has(node.id)) {
          hierarchy.children.push(nodeMap.get(node.id))
        }
      })

      return { hierarchy, nodeMap }
    }

    // 计算节点位置（层次布局）
    const calculateNodePositions = (hierarchy) => {
      const positions = new Map()
      const levelHeights = []

      // 遍历层次结构，计算每个节点的位置
      const traverse = (node, level, x) => {
        // 计算当前层级的高度
        if (!levelHeights[level]) {
          levelHeights[level] = 100 + level * 180 // 每层高度为180
        }

        // 为当前节点分配位置
        positions.set(node.id, {
          x: x,
          y: levelHeights[level]
        })

        // 计算子节点的位置
        if (node.children && node.children.length > 0) {
          const childCount = node.children.length
          const startX = x - (childCount - 1) * 150 / 2 // 子节点间距为150

          node.children.forEach((child, index) => {
            traverse(child, level + 1, startX + index * 150)
          })
        }
      }

      // 从根节点开始遍历
      hierarchy.children.forEach((rootNode, index) => {
        // 根节点水平间距为300
        const rootX = 100 + index * 300
        traverse(rootNode, 0, rootX)
      })

      return positions
    }

    // 转换图表数据为Excalidraw格式
    const excalidrawData = computed(() => {
      if (!props.diagramData || !props.diagramData.nodes || !props.diagramData.links) {
        return { elements: [], appState: {} }
      }

      const elements = []
      const nodeMap = new Map()
      let elementId = 1

      // 构建层次结构
      const { hierarchy } = buildHierarchy(props.diagramData.nodes, props.diagramData.links)
      
      // 计算节点位置
      const positions = calculateNodePositions(hierarchy)

      // 添加节点
      props.diagramData.nodes.forEach((node) => {
        const position = positions.get(node.id)
        const x = position ? position.x : 100 + Math.random() * 500
        const y = position ? position.y : 100 + Math.random() * 300
        
        // 根据节点类型设置不同的样式
        let width = 150
        let height = 80
        let backgroundColor = node.itemStyle?.color || '#FF9AA2'
        
        // 模块节点使用不同的样式
        if (node.category === 'module') {
          width = 180
          height = 90
          backgroundColor = node.itemStyle?.color || '#A8D0E6'
        }
        
        const element = {
          id: `node-${node.id}`,
          type: 'rectangle',
          x: x,
          y: y,
          width: width,
          height: height,
          angle: 0,
          strokeColor: '#333',
          backgroundColor: backgroundColor,
          fillStyle: 'solid',
          strokeWidth: 2,
          strokeStyle: 'solid',
          roughness: 1,
          opacity: 100,
          groupIds: [],
          roundness: null,
          seed: elementId++,
          versionNonce: Math.floor(Math.random() * 1000000),
          isDeleted: false,
          link: null,
          locked: false,
          text: node.name,
          fontSize: 14,
          fontFamily: 1,
          textAlign: 'center',
          verticalAlign: 'middle',
          baseline: 'middle',
          textColor: '#333',
          strokeSharpness: 'sharp',
          edges: [],
          updated: Date.now(),
          linkText: null,
          linkTextBgColor: null,
          linkTextSize: null,
          linkTextColor: null,
          linkStyle: 'solid',
          linkWidth: 2,
          startBinding: null,
          endBinding: null,
          points: null,
          lastCommittedPoint: null,
          startArrowhead: null,
          endArrowhead: 'arrow',
          lastPointerDown: null,
          lastPointerUp: null,
          lastMoved: null,
          lastSelected: null,
          lastUpdated: null,
          isDragging: false,
          isResizing: false,
          isRotating: false,
          isEditing: false,
          isSelected: false,
          isHovered: false,
          isActive: false,
          isCreating: false,
          isReadonly: false,
          isCopied: false,
          isPasted: false,
          isCut: false,
          isGrouped: false,
          isInGroup: false,
          isLocked: false,
          isHidden: false,
          isTemplate: false,
          isDeleted: false,
          isResizable: true,
          isDraggable: true,
          isRotatable: true,
          isTextEditable: true,
          isSelectable: true,
          isConnectable: true,
          isDeletable: true,
          isDuplicable: true,
          isMovable: true,
          isResizableX: true,
          isResizableY: true,
          isResizableAspectRatioLocked: false,
          isRotatableSnapped: false
        }

        elements.push(element)
        nodeMap.set(node.id, element)
      })

      // 添加连线
      props.diagramData.links.forEach((link, index) => {
        const sourceNode = nodeMap.get(link.source)
        const targetNode = nodeMap.get(link.target)

        if (sourceNode && targetNode) {
          // 根据关系类型设置不同的样式
          let strokeStyle = 'solid'
          let strokeWidth = link.lineStyle?.width || 2
          let startArrowhead = null
          let endArrowhead = 'arrow'
          
          // 层次关系使用虚线
          if (link.relationType === 'hierarchy' || link.lineStyle?.type === 'dashed') {
            strokeStyle = 'dashed'
          }
          
          // 依赖关系使用点线
          if (link.relationType === 'dependency') {
            strokeStyle = 'dashed'
            strokeWidth = 1.5
          }
          
          // 继承关系使用实线和空心箭头
          if (link.relationType === 'inheritance') {
            strokeStyle = 'solid'
            strokeWidth = 2
            endArrowhead = 'arrow'
          }
          
          const element = {
            id: `link-${index}`,
            type: 'arrow',
            x: sourceNode.x + sourceNode.width / 2,
            y: sourceNode.y + sourceNode.height / 2,
            width: 0,
            height: 0,
            angle: 0,
            strokeColor: '#666',
            backgroundColor: 'transparent',
            fillStyle: 'solid',
            strokeWidth: strokeWidth,
            strokeStyle: strokeStyle,
            roughness: 1,
            opacity: 100,
            groupIds: [],
            roundness: null,
            seed: elementId++,
            versionNonce: Math.floor(Math.random() * 1000000),
            isDeleted: false,
            link: null,
            locked: false,
            text: link.label,
            fontSize: 12,
            fontFamily: 1,
            textAlign: 'center',
            verticalAlign: 'middle',
            baseline: 'middle',
            textColor: '#666',
            strokeSharpness: 'sharp',
            edges: [],
            updated: Date.now(),
            linkText: null,
            linkTextBgColor: null,
            linkTextSize: null,
            linkTextColor: null,
            linkStyle: strokeStyle,
            linkWidth: strokeWidth,
            startBinding: null,
            endBinding: null,
            points: [
              { x: sourceNode.x + sourceNode.width / 2, y: sourceNode.y + sourceNode.height / 2 },
              { x: targetNode.x + targetNode.width / 2, y: targetNode.y + targetNode.height / 2 }
            ],
            lastCommittedPoint: null,
            startArrowhead: startArrowhead,
            endArrowhead: endArrowhead,
            lastPointerDown: null,
            lastPointerUp: null,
            lastMoved: null,
            lastSelected: null,
            lastUpdated: null,
            isDragging: false,
            isResizing: false,
            isRotating: false,
            isEditing: false,
            isSelected: false,
            isHovered: false,
            isActive: false,
            isCreating: false,
            isReadonly: false,
            isCopied: false,
            isPasted: false,
            isCut: false,
            isGrouped: false,
            isInGroup: false,
            isLocked: false,
            isHidden: false,
            isTemplate: false,
            isDeleted: false,
            isResizable: false,
            isDraggable: true,
            isRotatable: false,
            isTextEditable: true,
            isSelectable: true,
            isConnectable: true,
            isDeletable: true,
            isDuplicable: true,
            isMovable: true,
            isResizableX: false,
            isResizableY: false,
            isResizableAspectRatioLocked: false,
            isRotatableSnapped: false
          }

          elements.push(element)
        }
      })

      return { elements, appState: { theme: 'light' } }
    })

    // 加载Excalidraw
    const loadExcalidraw = () => {
      console.log('开始加载Excalidraw')
      if (excalidrawContainer.value) {
        console.log('Excalidraw容器存在')
        console.log('使用导入的Excalidraw库')
        renderExcalidraw()
      } else {
        console.error('Excalidraw容器不存在')
      }
    }

    // 渲染Excalidraw
    let excalidrawInstance = null
    
    const renderExcalidraw = () => {
      console.log('开始渲染Excalidraw')
      if (excalidrawContainer.value && Excalidraw) {
        console.log('容器和Excalidraw都存在')
        console.log('Excalidraw数据:', excalidrawData.value)
        // 清空容器
        excalidrawContainer.value.innerHTML = ''
        
        try {
          // 创建Excalidraw实例
          excalidrawInstance = Excalidraw.createApp({
            element: excalidrawContainer.value,
            initialData: excalidrawData.value,
            onChange: (elements, state) => {
              console.log('Elements changed:', elements)
            },
            theme: 'light'
          })
          console.log('Excalidraw实例创建成功')
        } catch (error) {
          console.error('创建Excalidraw实例失败:', error)
        }
      } else {
        console.error('容器或Excalidraw不存在:', {
          container: excalidrawContainer.value,
          excalidraw: Excalidraw
        })
      }
    }

    onMounted(() => {
      console.log('ExcalidrawComponent挂载')
      loadExcalidraw()
    })

    watch(
      () => props.diagramData,
      () => {
        console.log('diagramData变化')
        if (Excalidraw) {
          renderExcalidraw()
        } else {
          loadExcalidraw()
        }
      },
      { deep: true }
    )

    // 导出为图片
    const exportAsImage = () => {
      if (excalidrawInstance) {
        try {
          excalidrawInstance.exportToCanvas().then((canvas) => {
            canvas.toBlob((blob) => {
              const link = document.createElement('a');
              link.href = URL.createObjectURL(blob);
              link.download = `diagram-${Date.now()}.png`;
              link.click();
            });
          });
        } catch (error) {
          console.error('导出图片失败:', error);
        }
      }
    }

    // 导出为原生格式
    const exportAsNative = () => {
      if (excalidrawInstance) {
        try {
          const elements = excalidrawInstance.getSceneElements();
          const data = {
            elements,
            appState: { theme: 'light' }
          };
          const jsonString = JSON.stringify(data);
          const blob = new Blob([jsonString], { type: 'application/json' });
          const link = document.createElement('a');
          link.href = URL.createObjectURL(blob);
          link.download = `diagram-${Date.now()}.excalidraw`;
          link.click();
        } catch (error) {
          console.error('导出原生格式失败:', error);
        }
      }
    }

    return {
      excalidrawContainer,
      exportAsImage,
      exportAsNative
    }
  }
}
</script>

<style scoped>
.excalidraw-container {
  width: 100%;
  height: 100%;
}
</style>