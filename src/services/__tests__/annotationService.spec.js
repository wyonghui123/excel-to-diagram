/**
 * annotationService 单元测试
 *
 * 覆盖：
 *  - queryAnnotations 成功/失败
 *  - getAnnotation 成功/失败
 *  - createAnnotation 成功/失败
 *  - updateAnnotation 成功/失败
 *  - deleteAnnotation 成功/失败
 *
 * 策略：mock @/utils/httpClient 的 apiV1
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  queryAnnotations,
  getAnnotation,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
} from '../annotationService.js'

// vi.hoisted 确保 mock 引用在 import 之前创建
const mocks = vi.hoisted(() => ({
  apiV1Get: vi.fn(),
  apiV1Post: vi.fn(),
  apiV1Put: vi.fn(),
  apiV1Delete: vi.fn(),
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: {
    get: mocks.apiV1Get,
    post: mocks.apiV1Post,
    put: mocks.apiV1Put,
    delete: mocks.apiV1Delete,
  },
}))

import { apiV1 } from '@/utils/httpClient'

// 工具：构造 httpClient 标准响应
function okResp(data) {
  return {
    success: true,
    data,
    message: '',
    httpStatus: 200,
    traceId: 'trace-test',
  }
}

function failResp(httpStatus, message = 'error') {
  return {
    success: false,
    data: null,
    message,
    code: 'ERR',
    httpStatus,
    traceId: 'trace-test',
  }
}

describe('annotationService', () => {
  beforeEach(() => {
    mocks.apiV1Get.mockReset()
    mocks.apiV1Post.mockReset()
    mocks.apiV1Put.mockReset()
    mocks.apiV1Delete.mockReset()
  })

  describe('queryAnnotations', () => {
    it('成功时返回标注列表', async () => {
      const mockData = {
        items: [
          { id: 1, target_type: 'node', target_id: 'n1', category: 'note', content: '标注1' },
          { id: 2, target_type: 'edge', target_id: 'e1', category: 'warning', content: '标注2' },
        ],
        total: 2,
        page: 1,
        page_size: 20,
      }
      apiV1.get.mockResolvedValueOnce(okResp(mockData))

      const params = { target_type: 'node', target_id: 'n1', page: 1, page_size: 20 }
      const result = await queryAnnotations(params)

      expect(result.success).toBe(true)
      expect(result.data.items).toHaveLength(2)
      expect(result.data.total).toBe(2)
      expect(apiV1.get).toHaveBeenCalledWith('/annotations', { params })
    })

    it('失败时返回错误信息', async () => {
      apiV1.get.mockResolvedValueOnce(failResp(500, '服务器错误'))

      const result = await queryAnnotations({ target_type: 'node' })

      expect(result.success).toBe(false)
      expect(result.message).toBe('服务器错误')
      expect(result.httpStatus).toBe(500)
    })
  })

  describe('getAnnotation', () => {
    it('成功时返回标注详情', async () => {
      const mockData = { id: 1, target_type: 'node', target_id: 'n1', category: 'note', content: '详情内容' }
      apiV1.get.mockResolvedValueOnce(okResp(mockData))

      const result = await getAnnotation(1)

      expect(result.success).toBe(true)
      expect(result.data.id).toBe(1)
      expect(result.data.content).toBe('详情内容')
      expect(apiV1.get).toHaveBeenCalledWith('/annotations/1')
    })

    it('失败时返回错误信息', async () => {
      apiV1.get.mockResolvedValueOnce(failResp(404, '标注不存在'))

      const result = await getAnnotation(999)

      expect(result.success).toBe(false)
      expect(result.message).toBe('标注不存在')
      expect(result.httpStatus).toBe(404)
    })
  })

  describe('createAnnotation', () => {
    it('成功时返回新建标注', async () => {
      const inputData = { target_type: 'node', target_id: 'n1', category: 'note', content: '新标注' }
      const mockData = { id: 10, ...inputData }
      apiV1.post.mockResolvedValueOnce(okResp(mockData))

      const result = await createAnnotation(inputData)

      expect(result.success).toBe(true)
      expect(result.data.id).toBe(10)
      expect(result.data.content).toBe('新标注')
      expect(apiV1.post).toHaveBeenCalledWith('/annotations', inputData)
    })

    it('失败时返回错误信息', async () => {
      apiV1.post.mockResolvedValueOnce(failResp(400, '参数校验失败'))

      const result = await createAnnotation({})

      expect(result.success).toBe(false)
      expect(result.message).toBe('参数校验失败')
      expect(result.httpStatus).toBe(400)
    })
  })

  describe('updateAnnotation', () => {
    it('成功时返回更新后的标注', async () => {
      const updateData = { category: 'warning', content: '更新内容' }
      const mockData = { id: 1, target_type: 'node', target_id: 'n1', ...updateData }
      apiV1.put.mockResolvedValueOnce(okResp(mockData))

      const result = await updateAnnotation(1, updateData)

      expect(result.success).toBe(true)
      expect(result.data.category).toBe('warning')
      expect(result.data.content).toBe('更新内容')
      expect(apiV1.put).toHaveBeenCalledWith('/annotations/1', updateData)
    })

    it('失败时返回错误信息', async () => {
      apiV1.put.mockResolvedValueOnce(failResp(403, '无权限修改'))

      const result = await updateAnnotation(1, { content: 'x' })

      expect(result.success).toBe(false)
      expect(result.message).toBe('无权限修改')
      expect(result.httpStatus).toBe(403)
    })
  })

  describe('deleteAnnotation', () => {
    it('成功时返回成功响应', async () => {
      apiV1.delete.mockResolvedValueOnce(okResp(null))

      const result = await deleteAnnotation(1)

      expect(result.success).toBe(true)
      expect(apiV1.delete).toHaveBeenCalledWith('/annotations/1')
    })

    it('失败时返回错误信息', async () => {
      apiV1.delete.mockResolvedValueOnce(failResp(404, '标注不存在'))

      const result = await deleteAnnotation(999)

      expect(result.success).toBe(false)
      expect(result.message).toBe('标注不存在')
      expect(result.httpStatus).toBe(404)
    })
  })
})
