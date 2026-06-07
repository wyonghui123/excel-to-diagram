# -*- coding: utf-8 -*-
"""
多语言服务

提供运行时多语言文本的获取和管理功能。
支持：
- 多语言 key 解析
- 默认文本 fallback
- 从 YAML 加载多语言配置
- 语言切换
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path


class I18nService:
    """
    多语言服务
    
    提供多语言文本的获取和管理功能。
    """
    
    _instance = None
    _locales: Dict[str, Dict[str, str]] = {}
    _current_locale: str = "zh-CN"
    _i18n_dir: Optional[str] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._locales = {}
            cls._instance._current_locale = "zh-CN"
        return cls._instance
    
    def set_i18n_dir(self, dir_path: str) -> None:
        """设置多语言配置目录"""
        self._i18n_dir = dir_path
        self._load_all_locales()
    
    def _load_all_locales(self) -> None:
        """加载所有语言配置"""
        if not self._i18n_dir:
            return
        
        i18n_path = Path(self._i18n_dir)
        if not i18n_path.exists():
            return
        
        for locale_file in i18n_path.glob("*.yaml"):
            locale = locale_file.stem
            self._load_locale(locale, str(locale_file))
    
    def _load_locale(self, locale: str, file_path: str) -> None:
        """加载单个语言配置"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            self._locales[locale] = self._flatten_dict(data)
        except Exception as e:
            print(f"[I18nService] Error loading locale {locale}: {e}")
    
    def _flatten_dict(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
        """展平嵌套字典"""
        result = {}
        
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                result.update(self._flatten_dict(value, full_key))
            else:
                result[full_key] = str(value)
        
        return result
    
    def get_text(self, key: str, locale: Optional[str] = None, default: Optional[str] = None) -> str:
        """
        获取多语言文本
        
        Args:
            key: 多语言 key
            locale: 语言代码（可选，默认使用当前语言）
            default: 默认文本（可选）
            
        Returns:
            多语言文本
        """
        target_locale = locale or self._current_locale
        
        if target_locale in self._locales:
            if key in self._locales[target_locale]:
                return self._locales[target_locale][key]
        
        if default:
            return default
        
        return key
    
    def get_text_with_fallback(self, key: str, default_text: str, locale: Optional[str] = None) -> str:
        """
        获取多语言文本（带默认文本 fallback）
        
        Args:
            key: 多语言 key
            default_text: 默认文本
            locale: 语言代码（可选）
            
        Returns:
            多语言文本
        """
        text = self.get_text(key, locale)
        
        if text == key:
            return default_text
        
        return text
    
    def set_current_locale(self, locale: str) -> None:
        """设置当前语言"""
        self._current_locale = locale
    
    def get_current_locale(self) -> str:
        """获取当前语言"""
        return self._current_locale
    
    def get_available_locales(self) -> List[str]:
        """获取可用语言列表"""
        return list(self._locales.keys())
    
    def has_locale(self, locale: str) -> bool:
        """检查语言是否可用"""
        return locale in self._locales
    
    def add_locale_texts(self, locale: str, texts: Dict[str, str]) -> None:
        """
        添加语言文本
        
        Args:
            locale: 语言代码
            texts: 文本字典
        """
        if locale not in self._locales:
            self._locales[locale] = {}
        
        self._locales[locale].update(texts)
    
    def get_all_texts(self, locale: Optional[str] = None) -> Dict[str, str]:
        """
        获取所有文本
        
        Args:
            locale: 语言代码（可选）
            
        Returns:
            文本字典
        """
        target_locale = locale or self._current_locale
        return self._locales.get(target_locale, {})
    
    def resolve_i18n_key(self, i18n_key: str, default_text: str, locale: Optional[str] = None) -> str:
        """
        解析 i18n key
        
        如果 i18n_key 为空，直接返回 default_text。
        
        Args:
            i18n_key: 多语言 key
            default_text: 默认文本
            locale: 语言代码（可选）
            
        Returns:
            多语言文本
        """
        if not i18n_key:
            return default_text
        
        return self.get_text_with_fallback(i18n_key, default_text, locale)
    
    def reload_locale(self, locale: str) -> bool:
        """
        重新加载语言配置
        
        Args:
            locale: 语言代码
            
        Returns:
            是否成功
        """
        if not self._i18n_dir:
            return False
        
        locale_file = Path(self._i18n_dir) / f"{locale}.yaml"
        if locale_file.exists():
            self._load_locale(locale, str(locale_file))
            return True
        
        return False
    
    def reload_all_locales(self) -> None:
        """重新加载所有语言配置"""
        self._locales.clear()
        self._load_all_locales()


i18n_service = I18nService()
