/**
 * 元数据配置验证器
 * 
 * 参考 SAP CDS 注解验证机制
 * 提供运行时配置验证，确保配置符合契约规范
 * 
 * @module utils/configValidator
 */

/**
 * @typedef {Object} ValidationResult
 * @property {boolean} valid - 是否通过验证
 * @property {string[]} errors - 错误列表
 * @property {string[]} warnings - 警告列表
 */

/**
 * 元数据配置验证器
 */
const ConfigValidator = {
  
  /**
   * 验证 cross_table_filters 配置
   * 
   * @param {Array} config - cross_table_filters 配置数组
   * @returns {ValidationResult} 验证结果
   * 
   * @example
   * const result = ConfigValidator.validateCrossTableFilters(config);
   * if (!result.valid) {
   *   console.error(result.errors);
   * }
   */
  validateCrossTableFilters(config) {
    const errors = [];
    const warnings = [];
    
    // 基本类型检查
    if (!Array.isArray(config)) {
      errors.push('cross_table_filters must be an array');
      return { valid: false, errors, warnings };
    }
    
    // 逐个验证配置项
    config.forEach((filter, index) => {
      const prefix = `[${index}]`;
      
      // ========== 必需字段验证 ==========
      
      // 验证 id
      if (!filter.id) {
        errors.push(`${prefix} Missing required field: id`);
      } else if (typeof filter.id !== 'string') {
        errors.push(`${prefix} id must be a string`);
      }
      
      // 验证 display_name
      if (!filter.display_name) {
        warnings.push(`${prefix} Missing display_name`);
      }
      
      // ========== Association 验证 ==========
      
      if (!filter.association) {
        errors.push(`${prefix} Missing required field: association`);
      } else {
        const assoc = filter.association;
        
        // target_table 验证
        if (!assoc.target_table) {
          errors.push(`${prefix} Missing association.target_table`);
        } else if (typeof assoc.target_table !== 'string') {
          errors.push(`${prefix} association.target_table must be a string`);
        }
        
        // target_alias 验证
        if (assoc.target_alias !== undefined && typeof assoc.target_alias !== 'string') {
          errors.push(`${prefix} association.target_alias must be a string`);
        }
        
        // join_type 验证
        if (assoc.join_type !== undefined) {
          const validJoinTypes = ['exists', 'inner', 'left'];
          if (!validJoinTypes.includes(assoc.join_type)) {
            errors.push(
              `${prefix} association.join_type must be one of: ${validJoinTypes.join(', ')}`
            );
          }
        }
        
        // on_conditions 验证
        if (!assoc.on_conditions) {
          errors.push(`${prefix} Missing association.on_conditions`);
        } else if (!Array.isArray(assoc.on_conditions)) {
          errors.push(`${prefix} association.on_conditions must be an array`);
        } else if (assoc.on_conditions.length === 0) {
          errors.push(`${prefix} association.on_conditions cannot be empty`);
        } else {
          // 验证每个 on_condition
          assoc.on_conditions.forEach((cond, condIndex) => {
            if (!cond.left_field) {
              errors.push(`${prefix}[${condIndex}] Missing left_field`);
            }
            if (!cond.operator) {
              errors.push(`${prefix}[${condIndex}] Missing operator`);
            } else {
              const validOperators = ['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'like', 'in'];
              if (!validOperators.includes(cond.operator)) {
                errors.push(
                  `${prefix}[${condIndex}] Invalid operator: ${cond.operator}`
                );
              }
            }
            if (!cond.right_field) {
              errors.push(`${prefix}[${condIndex}] Missing right_field`);
            }
          });
        }
        
        // where_conditions 验证
        if (assoc.where_conditions !== undefined) {
          if (!Array.isArray(assoc.where_conditions)) {
            errors.push(`${prefix} association.where_conditions must be an array`);
          } else {
            assoc.where_conditions.forEach((cond, condIndex) => {
              if (!cond.field) {
                errors.push(`${prefix}[where:${condIndex}] Missing field`);
              }
              if (!cond.operator) {
                errors.push(`${prefix}[where:${condIndex}] Missing operator`);
              }
              if (!cond.parameter) {
                errors.push(`${prefix}[where:${condIndex}] Missing parameter`);
              }
            });
          }
        }
      }
      
      // ========== UI 配置验证 ==========
      
      if (!filter.ui) {
        warnings.push(`${prefix} Missing ui configuration`);
      } else {
        const ui = filter.ui;
        
        // filter_type 验证
        if (!ui.filter_type) {
          errors.push(`${prefix} Missing ui.filter_type`);
        } else {
          const validFilterTypes = [
            'search', 'select', 'multi-select',
            'date', 'date-range', 'number'
          ];
          if (!validFilterTypes.includes(ui.filter_type)) {
            errors.push(
              `${prefix} ui.filter_type must be one of: ${validFilterTypes.join(', ')}`
            );
          }
        }
        
        // options_source 验证
        if (!ui.options_source) {
          warnings.push(`${prefix} Missing ui.options_source, defaulting to text`);
        } else {
          const validSources = ['static', 'enum', 'api'];
          if (!validSources.includes(ui.options_source)) {
            errors.push(
              `${prefix} ui.options_source must be one of: ${validSources.join(', ')}`
            );
          } else {
            // options_source 互斥验证
            switch (ui.options_source) {
              case 'static':
                if (!ui.static_options) {
                  errors.push(
                    `${prefix} Missing ui.static_options when options_source=static`
                  );
                } else if (!Array.isArray(ui.static_options)) {
                  errors.push(`${prefix} ui.static_options must be an array`);
                } else if (ui.static_options.length === 0) {
                  warnings.push(`${prefix} ui.static_options is empty`);
                }
                break;
                
              case 'enum':
                if (!ui.enum_type) {
                  errors.push(
                    `${prefix} Missing ui.enum_type when options_source=enum`
                  );
                } else if (typeof ui.enum_type !== 'string') {
                  errors.push(`${prefix} ui.enum_type must be a string`);
                }
                break;
                
              case 'api':
                if (!ui.api_endpoint) {
                  errors.push(
                    `${prefix} Missing ui.api_endpoint when options_source=api`
                  );
                } else if (typeof ui.api_endpoint !== 'string') {
                  errors.push(`${prefix} ui.api_endpoint must be a string`);
                }
                break;
            }
          }
        }
        
        // position 验证
        if (ui.position !== undefined && typeof ui.position !== 'number') {
          errors.push(`${prefix} ui.position must be a number`);
        }
      }
    });
    
    return {
      valid: errors.length === 0,
      errors,
      warnings
    };
  },
  
  /**
   * 验证配置并输出日志
   * 
   * @param {Array} config - 配置数组
   * @param {string} configName - 配置名称（用于日志）
   * @returns {ValidationResult} 验证结果
   * 
   * @example
   * const result = ConfigValidator.validateAndLog(
   *   metaObj.analytical_model?.cross_table_filters,
   *   'cross_table_filters'
   * );
   */
  validateAndLog(config, configName = 'config') {
    const result = this.validateCrossTableFilters(config);
    
    // 输出错误日志
    if (result.errors.length > 0) {
      console.error(
        `[ConfigValidator] ${configName} validation FAILED:`,
        result.errors
      );
    }
    
    // 输出警告日志
    if (result.warnings.length > 0) {
      console.warn(
        `[ConfigValidator] ${configName} validation warnings:`,
        result.warnings
      );
    }
    
    // 输出成功日志
    if (result.valid) {
      console.log(`[ConfigValidator] ${configName} validation passed`);
    }
    
    return result;
  },
  
  /**
   * 快速验证单个配置项
   * 
   * @param {Object} filter - 单个过滤配置
   * @returns {ValidationResult} 验证结果
   */
  validateSingleFilter(filter) {
    return this.validateCrossTableFilters([filter]);
  },
  
  /**
   * 获取验证错误摘要
   * 
   * @param {ValidationResult} result - 验证结果
   * @returns {string} 错误摘要字符串
   */
  getErrorSummary(result) {
    if (result.valid) {
      return 'No errors';
    }
    
    const lines = [];
    if (result.errors.length > 0) {
      lines.push(`Errors (${result.errors.length}):`);
      result.errors.forEach(err => lines.push(`  - ${err}`));
    }
    if (result.warnings.length > 0) {
      lines.push(`Warnings (${result.warnings.length}):`);
      result.warnings.forEach(warn => lines.push(`  - ${warn}`));
    }
    
    return lines.join('\n');
  }
};

export default ConfigValidator;
export { ConfigValidator };
