/**
 * DeepSeek AI 校验服务
 * 使用DeepSeek API对关系说明进行可读性检查
 */

import { ValidationLevel, ValidationType } from './dataValidator.js';

// DeepSeek API配置
const DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions';
const DEEPSEEK_API_KEY = import.meta.env.VITE_DEEPSEEK_API_KEY || '';

/**
 * 批量校验关系说明
 * @param {Array} relationships - 关系数据数组
 * @returns {Promise<Array>} 校验结果数组
 */
export async function validateRelationshipDescriptions(relationships) {
  if (!relationships || relationships.length === 0) {
    return [];
  }

  const items = [];

  // 分批处理，每批10条关系
  const batchSize = 10;
  for (let i = 0; i < relationships.length; i += batchSize) {
    const batch = relationships.slice(i, i + batchSize);
    const batchResults = await validateBatch(batch, i);
    items.push(...batchResults);
  }

  return items;
}

/**
 * 校验一批关系说明
 * @param {Array} batch - 关系数据批次
 * @param {number} offset - 起始偏移量
 * @returns {Promise<Array>} 校验结果
 */
async function validateBatch(batch, offset) {
  const items = [];

  // 构建提示词
  const prompt = buildValidationPrompt(batch);

  try {
    const response = await callDeepSeekAPI(prompt);
    const results = parseAIResponse(response, batch, offset);
    items.push(...results);
  } catch (error) {
    console.error('DeepSeek API调用失败:', error);
    // API失败时添加一个提示信息
    items.push({
      level: ValidationLevel.INFO,
      type: ValidationType.AI_CHECK,
      sheet: '业务对象关系',
      row: offset + 2,
      field: '关系说明',
      value: '',
      message: 'AI校验服务暂时不可用，请稍后重试',
      suggestion: '您可以手动检查关系说明的清晰度和可读性'
    });
  }

  return items;
}

/**
 * 构建校验提示词
 * @param {Array} relationships - 关系数组
 * @returns {string} 提示词
 */
function buildValidationPrompt(relationships) {
  const relationsText = relationships.map((rel, idx) => {
    const source = rel.sourceName || rel['源业务对象名称'] || rel.sourceCode || rel['源业务对象编码'];
    const target = rel.targetName || rel['目标业务对象名称'] || rel.targetCode || rel['目标业务对象编码'];
    const desc = rel.relationDesc || rel['关系说明'] || '';
    const code = rel.relationCode || rel['关系编码'] || '';
    return `[${idx + 1}] 关系编码: ${code}\n源对象: ${source}\n目标对象: ${target}\n关系说明: ${desc || '(空)'}`;
  }).join('\n\n');

  return `你是一位资深的业务架构顾问，请对以下业务对象关系说明进行业务可读性检查。

【核心规则 - 必须遵守】：
1. 以下4条检查标准，只要满足任意1条（或1条以上），就必须返回PASS
2. 只有当4条标准全部不满足时，才返回WARNING或ERROR
3. 这是"或"关系，不是"与"关系！

【4条检查标准 - 满足任意1条即通过】：
标准1：是否说明了是"推单"或"拉单"模式进行订单/业务生成
  - 示例："A系统推单到B系统生成采购订单"、"B系统拉取A系统的库存数据"
标准2：是否说明了两个业务对象之间传递了什么数据信息
  - 示例："传递客户主数据信息"、"同步订单状态数据"
标准3：是否说明了服务调用实现了什么业务目的
  - 示例："调用库存查询服务获取实时库存"、"触发支付完成通知"
标准4：是否说明了业务对象之间的数据依赖关系
  - 示例："订单依赖于客户信息"、"发货单需要引用订单数据"

【判断流程 - 严格按此执行】：
步骤1：逐条检查是否满足4条标准
步骤2：如果有任意1条满足 → 返回PASS，reason说明满足哪条标准
步骤3：如果4条都不满足 → 根据情况返回WARNING或ERROR，并说明缺少哪些标准

【评价等级】：
- PASS：满足4条标准中的任意1条或以上（这是最常见的情况）
- WARNING：4条标准全部都不满足，但关系说明有一定业务含义
- ERROR：4条标准全部都不满足，且关系说明完全无法判断业务含义

【重要提醒】：
- 大部分关系说明应该返回PASS（只要满足任意1条标准）
- 不要过度严格，满足1条标准就足够了
- 检查时要宽松一些，有业务含义即可

待检查的关系说明：

${relationsText}

请以JSON格式返回结果，格式如下：
[
  {
    "index": 1,
    "result": "PASS|WARNING|ERROR",
    "reason": "评价理由：PASS时说明满足哪条标准；WARNING/ERROR时说明4条标准都不满足，缺少哪些",
    "suggestion": "优化建议：如未通过，说明应补充什么内容"
  }
]`;
}

/**
 * 调用DeepSeek API
 * @param {string} prompt - 提示词
 * @returns {Promise<string>} API响应内容
 */
async function callDeepSeekAPI(prompt) {
  if (!DEEPSEEK_API_KEY) {
    throw new Error('DeepSeek API密钥未配置');
  }

  const response = await fetch(DEEPSEEK_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${DEEPSEEK_API_KEY}`
    },
    body: JSON.stringify({
      model: 'deepseek-chat',
      messages: [
        {
          role: 'system',
          content: '你是一位专业的业务架构顾问，擅长评估业务文档的可读性和清晰度。'
        },
        {
          role: 'user',
          content: prompt
        }
      ],
      temperature: 0.3,
      max_tokens: 2000
    })
  });

  if (!response.ok) {
    throw new Error(`API请求失败: ${response.status}`);
  }

  const data = await response.json();
  return data.choices[0].message.content;
}

/**
 * 解析AI响应
 * @param {string} response - API响应文本
 * @param {Array} batch - 原始批次数据
 * @param {number} offset - 起始偏移量
 * @returns {Array} 校验结果
 */
function parseAIResponse(response, batch, offset) {
  const items = [];

  try {
    // 提取JSON部分
    const jsonMatch = response.match(/\[[\s\S]*\]/);
    if (!jsonMatch) {
      throw new Error('无法解析AI响应');
    }

    const results = JSON.parse(jsonMatch[0]);

    results.forEach((result, idx) => {
      const rel = batch[idx];
      if (!rel) return;

      const row = offset + idx + 2; // Excel行号
      const desc = rel.relationDesc || rel['关系说明'] || '';
      const code = rel.relationCode || rel['关系编码'] || '';

      // 根据结果确定级别
      let level = ValidationLevel.INFO;
      if (result.result === 'ERROR') {
        level = ValidationLevel.WARNING; // AI判断的严重问题转为警告
      } else if (result.result === 'WARNING') {
        level = ValidationLevel.INFO; // AI判断的警告转为提示
      } else {
        // PASS的不添加校验项
        return;
      }

      items.push({
        level,
        type: ValidationType.AI_CHECK,
        sheet: '业务对象关系',
        row,
        field: '关系说明',
        value: desc,
        relationCode: code,
        checkedText: desc,
        message: result.reason,
        suggestion: result.suggestion || '建议优化关系说明的表述'
      });
    });
  } catch (error) {
    console.error('解析AI响应失败:', error);
    // 解析失败时添加提示
    const firstRel = batch[0];
    const firstCode = firstRel ? (firstRel.relationCode || firstRel['关系编码'] || '') : '';
    const firstDesc = firstRel ? (firstRel.relationDesc || firstRel['关系说明'] || '') : '';
    items.push({
      level: ValidationLevel.INFO,
      type: ValidationType.AI_CHECK,
      sheet: '业务对象关系',
      row: offset + 2,
      field: '关系说明',
      value: firstDesc,
      relationCode: firstCode,
      checkedText: firstDesc,
      message: 'AI校验结果解析失败，请手动检查',
      suggestion: '请确保关系说明清晰易懂，包含必要的业务上下文'
    });
  }

  return items;
}

/**
 * 模拟校验（用于测试或API不可用时）
 * @param {Array} relationships - 关系数组
 * @returns {Array} 模拟校验结果
 */
export function mockValidateDescriptions(relationships) {
  const items = [];

  relationships.forEach((rel, idx) => {
    const desc = rel.relationDesc || rel['关系说明'] || '';
    const code = rel.relationCode || rel['关系编码'] || '';

    // 简单的启发式检查
    if (!desc || desc.length < 5) {
      items.push({
        level: ValidationLevel.INFO,
        type: ValidationType.AI_CHECK,
        sheet: '业务对象关系',
        row: idx + 2,
        field: '关系说明',
        value: desc,
        relationCode: code,
        checkedText: desc,
        message: '说明过于简短，可能不够清晰',
        suggestion: '建议补充更多业务背景信息，说明关系的业务含义'
      });
    } else if (desc.length > 50) {
      items.push({
        level: ValidationLevel.INFO,
        type: ValidationType.AI_CHECK,
        sheet: '业务对象关系',
        row: idx + 2,
        field: '关系说明',
        value: desc,
        relationCode: code,
        checkedText: desc,
        message: '说明较长，建议精简',
        suggestion: '建议提炼核心信息，使说明更加简洁明了'
      });
    }
  });

  return items;
}
