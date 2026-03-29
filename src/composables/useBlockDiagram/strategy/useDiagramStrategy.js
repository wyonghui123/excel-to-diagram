import { businessObjectTransformer } from '../transform/businessObjectTransformer'
import { serviceModuleTransformer } from '../transform/serviceModuleTransformer'
import { SizeConfig, LayoutConfig, ColorConfig } from '../model'

export function useDiagramStrategy() {
  const strategies = new Map()

  const register = (type, strategy) => {
    strategies.set(type, strategy)
  }

  const get = (type) => {
    return strategies.get(type)
  }

  const has = (type) => {
    return strategies.has(type)
  }

  const getAll = () => {
    return Array.from(strategies.entries())
  }

  const initializeDefaultStrategies = () => {
    register('business-object', createBusinessObjectStrategy())
    register('service-module', createServiceModuleStrategy())
  }

  return {
    register,
    get,
    has,
    getAll,
    initializeDefaultStrategies
  }
}

export function createBusinessObjectStrategy() {
  return {
    name: 'business-object',
    description: '业务对象图策略',

    transformer: businessObjectTransformer,

    sizeConfig: new SizeConfig({
      strategy: 'content-based',
      fontSize: 18,
      charWidthRatio: 0.65,
      lineHeight: 28,
      padding: 20,
      minWidth: 180,
      minHeight: 80
    }),

    layoutConfig: new LayoutConfig({
      direction: 'TB',
      nodeSpacing: 80,
      rankSpacing: 100,
      nodeWidth: 180,
      nodeHeight: 80,
      curve: 'basis',
      padding: 25
    }),

    colorConfig: new ColorConfig({
      groupBy: 'subDomain',
      scheme: 'default',
      linkColorRule: 'nonCenter'
    }),

    behaviorConfig: {
      zoom: {
        enabled: true,
        minScale: 0.1,
        maxScale: 3,
        zoomFactor: 0.1,
        mouseCentered: true
      },
      selection: {
        enabled: true,
        onPathClick: {
          highlightPath: true,
          highlightNodes: true,
          highlightLabel: true
        },
        onLabelClick: {
          highlightPath: true,
          highlightNodes: false
        },
        highlightStyle: {
          pathStrokeWidth: '4px',
          pathFilter: 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))',
          nodeStroke: '#FF6B6B',
          nodeStrokeWidth: '4px',
          nodeFilter: 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
        }
      },
      tooltip: {
        enabled: true
      },
      label: {
        background: 'white',
        trailingLine: {
          enabled: true,
          color: '#999',
          dashArray: '3,3'
        }
      },
      container: {
        titleFormat: 'hierarchical',
        hierarchicalTemplate: '{parent}/{name}',
        style: {
          fill: '#ffffff',
          stroke: '#333',
          strokeWidth: '2px',
          titleFontStyle: 'italic'
        }
      }
    },

    getMermaidConfig() {
      return {
        startOnLoad: false,
        securityLevel: 'loose',
        theme: 'default',
        themeVariables: {
          edgeLabelBackground: '#ffffff',
          edgeLabelColor: '#333333'
        },
        flowchart: {
          curve: 'basis',
          padding: 25,
          nodeSpacing: 80,
          rankSpacing: 100,
          arrowMarkerAbsolute: true,
          useMaxWidth: false,
          htmlLabels: true,
          diagramPadding: 30,
          wrappingWidth: 200,
          labelPosition: 'b',
          defaultLinkLength: 60,
          arrowHeadWidth: 6,
          arrowHeadHeight: 6,
          nodeWidth: 180,
          nodeHeight: 80
        }
      }
    }
  }
}

export function createServiceModuleStrategy() {
  return {
    name: 'service-module',
    description: '服务模块图策略',

    transformer: serviceModuleTransformer,

    sizeConfig: new SizeConfig({
      strategy: 'fixed',
      fontSize: 18,
      charWidthRatio: 0.65,
      lineHeight: 28,
      padding: 20,
      minWidth: 300,
      minHeight: 120,
      fixedWidth: 300,
      fixedHeight: 120
    }),

    layoutConfig: new LayoutConfig({
      direction: 'TB',
      nodeSpacing: 150,
      rankSpacing: 200,
      nodeWidth: 300,
      nodeHeight: 120,
      curve: 'basis',
      padding: 30
    }),

    colorConfig: new ColorConfig({
      groupBy: 'subDomain',
      scheme: 'default',
      linkColorRule: 'nonCenter'
    }),

    behaviorConfig: {
      zoom: {
        enabled: true,
        minScale: 0.1,
        maxScale: 3,
        zoomFactor: 0.1,
        mouseCentered: true
      },
      selection: {
        enabled: true,
        onPathClick: {
          highlightPath: true,
          highlightNodes: true,
          highlightLabel: true
        },
        onLabelClick: {
          highlightPath: true,
          highlightNodes: false
        },
        highlightStyle: {
          pathStrokeWidth: '4px',
          pathFilter: 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))',
          nodeStroke: '#FF6B6B',
          nodeStrokeWidth: '4px',
          nodeFilter: 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
        }
      },
      tooltip: {
        enabled: true
      },
      label: {
        background: 'transparent',
        trailingLine: {
          enabled: true,
          color: '#999',
          dashArray: '3,3'
        }
      },
      container: {
        titleFormat: 'simple',
        style: {
          fill: '#ffffff',
          stroke: '#666',
          strokeWidth: '2px',
          titleFontStyle: 'normal'
        }
      }
    },

    getMermaidConfig() {
      return {
        startOnLoad: false,
        securityLevel: 'loose',
        theme: 'base',
        themeVariables: {
          edgeLabelBackground: 'transparent',
          edgeLabelColor: '#000000',
          primaryColor: '#ffffff',
          primaryTextColor: '#000000',
          primaryBorderColor: '#333333',
          lineColor: '#333333',
          secondaryColor: '#f0f0f0',
          tertiaryColor: '#ffffff'
        },
        flowchart: {
          curve: 'basis',
          padding: 30,
          nodeSpacing: 150,
          rankSpacing: 200,
          arrowMarkerAbsolute: true,
          useMaxWidth: false,
          htmlLabels: true,
          diagramPadding: 50,
          wrappingWidth: 500,
          labelPosition: 'c',
          labelOffset: 0,
          defaultLinkLength: 80,
          arrowHeadWidth: 10,
          arrowHeadHeight: 8,
          nodeWidth: 300,
          nodeHeight: 120,
          rankdir: 'TB'
        }
      }
    }
  }
}

export const diagramStrategy = useDiagramStrategy()
diagramStrategy.initializeDefaultStrategies()
