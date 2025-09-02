import json
import random
import time
from typing import List, Dict, Any, Optional, Union
from openai import OpenAI


class OpenAIManager:
    """
    基于OpenAI库的多配置模型调用管理器
    支持多个API配置，模型调用、验证和随机调用功能
    """
    
    def __init__(self, config_file: str = "config.json"):
        """
        初始化管理器
        
        Args:
            config_file: JSON配置文件路径
        """
        self.config_file = config_file
        self.configs = self._load_config()
        
    def _load_config(self) -> List[Dict[str, str]]:
        """
        读取JSON配置文件
        
        Returns:
            配置列表
        """
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            # 支持单个配置对象或配置数组
            if isinstance(config_data, dict):
                return [config_data]
            elif isinstance(config_data, list):
                return config_data
            else:
                raise ValueError("配置文件格式错误：必须是对象或对象数组")
                
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {self.config_file} 不存在")
        except json.JSONDecodeError:
            raise ValueError(f"配置文件 {self.config_file} JSON格式错误")
    
    def _get_client(self, config_index: int) -> OpenAI:
        """
        根据配置索引获取OpenAI客户端
        
        Args:
            config_index: 配置项索引（从0开始）
            
        Returns:
            OpenAI客户端实例
        """
        if config_index < 0 or config_index >= len(self.configs):
            raise IndexError(f"配置索引 {config_index} 超出范围 [0, {len(self.configs)-1}]")
            
        config = self.configs[config_index]
        
        return OpenAI(
            api_key=config["apikey"],
            base_url=config["url"]
        )
    
    def call_model(self, config_index: int, messages: List[Dict[str, str]], 
                   max_retries: int = 3, **kwargs) -> Dict[str, Any]:
        """
        模型调用函数
        
        Args:
            config_index: 指定配置项索引（从0开始）
            messages: 标准对话记录数组 [{"role": "user", "content": "..."}]
            max_retries: 最大重试次数，默认3次
            **kwargs: 其他OpenAI API参数
            
        Returns:
            原始API响应消息
        """
        if config_index < 0 or config_index >= len(self.configs):
            raise IndexError(f"配置索引 {config_index} 超出范围 [0, {len(self.configs)-1}]")
        
        config = self.configs[config_index]
        client = self._get_client(config_index)
        
        # 设置默认参数
        api_params = {
            "model": config["model"],
            "messages": messages,
            **kwargs
        }
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**api_params)
                return response.model_dump()
                
            except Exception as e:
                last_error = e
                print(f"第 {attempt + 1} 次调用失败: {str(e)}")
                
                if attempt < max_retries - 1:
                    # 等待一段时间后重试
                    time.sleep(2 ** attempt)  # 指数退避
                    
        # 所有重试都失败
        raise Exception(f"经过 {max_retries} 次重试后仍然失败，最后错误: {str(last_error)}")
    
    def validate_model(self, config_index: int) -> bool:
        """
        模型验证函数
        
        Args:
            config_index: 指定配置项索引
            
        Returns:
            验证结果 True/False
        """
        try:
            test_messages = [{"role": "user", "content": "你好"}]
            
            # 限制返回字数以节省资源
            response = self.call_model(
                config_index=config_index,
                messages=test_messages,
                max_tokens=10,
                max_retries=1
            )
            
            # 检查响应是否有效
            if response and "choices" in response and len(response["choices"]) > 0:
                return True
            else:
                return False
                
        except Exception as e:
            print(f"配置 {config_index} 验证失败: {str(e)}")
            return False
    
    def random_call(self, messages: List[Dict[str, str]], 
                   config_range: Optional[List[int]] = None, **kwargs) -> Dict[str, Any]:
        """
        随机调用函数
        
        Args:
            messages: 标准对话记录数组
            config_range: 指定配置范围的索引列表，默认为None（使用全部配置）
            **kwargs: 其他OpenAI API参数
            
        Returns:
            原始API响应消息
        """
        # 确定可用的配置范围
        if config_range is None:
            available_configs = list(range(len(self.configs)))
        else:
            # 验证配置范围有效性
            available_configs = []
            for idx in config_range:
                if 0 <= idx < len(self.configs):
                    available_configs.append(idx)
                else:
                    print(f"警告：配置索引 {idx} 超出范围，已忽略")
        
        if not available_configs:
            raise ValueError("没有可用的配置项")
        
        # 随机选择一个配置
        selected_config = random.choice(available_configs)
        
        print(f"随机选择配置 {selected_config}: {self.configs[selected_config]['model']}")
        
        return self.call_model(
            config_index=selected_config,
            messages=messages,
            **kwargs
        )
    
    def get_config_info(self) -> List[Dict[str, str]]:
        """
        获取所有配置信息（隐藏API密钥）
        
        Returns:
            配置信息列表
        """
        masked_configs = []
        for i, config in enumerate(self.configs):
            masked_config = {
                "index": i,
                "url": config["url"],
                "model": config["model"],
                "apikey": config["apikey"][:8] + "..." if len(config["apikey"]) > 8 else "***"
            }
            masked_configs.append(masked_config)
        
        return masked_configs
    
    def validate_all_configs(self) -> Dict[int, bool]:
        """
        验证所有配置
        
        Returns:
            配置索引到验证结果的映射
        """
        results = {}
        for i in range(len(self.configs)):
            print(f"验证配置 {i}...")
            results[i] = self.validate_model(i)
        
        return results