/**
 * Test Data Factories Index
 *
 * Export all factory functions for easy importing:
 *   import { createUser, createProduct, setupProductWithVersion } from '@/test/factories'
 */

// User Factory
export {
  createUser,
  createAdminUser,
  createUserViaApi,
  cleanupUser,
  buildUserResponse
} from './userFactory.js'

// Product Factory
export {
  createProduct,
  createVersion,
  createProductViaApi,
  createVersionViaApi,
  setupProductWithVersion,
  cleanupProductWithVersion,
  buildProductResponse,
  buildVersionResponse,
  buildPaginatedResponse
} from './productFactory.js'
