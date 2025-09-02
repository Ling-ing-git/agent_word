"""
OpenAI客户端 - 支持多配置管理和智能调用
"""

import json
import random
import time
from typing import Dict, List, Any, Optional, Union
from openai import OpenAI
from pathlib import Path

class OpenAIClient:
    """OpenAI多配置客户端管理器"""
    
    def __init__(self, config_file: str = "openai_config.json"):
        self.config_file = config_file
        self.configs = []
        self.clients = {}  # 缓存客户端实例
        self.load_configs()
    
    def load_configs(self) -> List[Dict[str, Any]]:
        """加载JSON配置文件"""
        try:
            if not Path(self.config_file).exists():
                # 创建示例配置文件
                self._create_example_config()
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 支持单个配置对象或配置数组
            if isinstance(data, dict):
                self.configs = [data]
            elif isinstance(data, list):
                self.configs = data
            else:
                raise ValueError("配置文件格式错误，应为对象或数组")
            
            # 验证配置格式
            for i, config in enumerate(self.configs):
                self._validate_config(config, i)
            
            print(f"成功加载 {len(self.configs)} 个配置")
            return self.configs
            
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {self.config_file} 不存在")
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件JSON格式错误: {e}")
    
    def _create_example_config(self):
        """创建示例配置文件"""
        example_configs = [
            {
                "url": "https://api.openai.com/v1",
                "model": "gpt-3.5-turbo",
                "apikey": "your-openai-api-key"
            },
            {
                "url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
                "apikey": "your-deepseek-api-key"
            },
            {
                "url": "http://localhost:8000/v1",
                "model": "local-model",
                "apikey": "local-key"
            }
        ]
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(example_configs, f, indent=2, ensure_ascii=False)
        
        print(f"已创建示例配置文件: {self.config_file}")
    
    def _validate_config(self, config: Dict[str, Any], index: int):
        """验证单个配置项"""
        required_fields = ["url", "model", "apikey"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"配置项 {index} 缺少必要字段: {field}")
            if not config[field]:
                raise ValueError(f"配置项 {index} 的 {field} 不能为空")
    
    def _get_client(self, config_index: int) -> OpenAI:
        """获取或创建客户端实例"""
        if config_index < 0 or config_index >= len(self.configs):
            raise ValueError(f"配置索引 {config_index} 超出范围 (0-{len(self.configs)-1})")
        
        # 使用缓存避免重复创建
        if config_index not in self.clients:
            config = self.configs[config_index]
            self.clients[config_index] = OpenAI(
                api_key=config["apikey"],
                base_url=config["url"]
            )
        
        return self.clients[config_index]
    
    def call_model(self, config_index: int, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """
        模型调用 - 支持3次重试
        
        Args:
            config_index: 指定配置项索引
            messages: 标准对话记录数组
            **kwargs: 其他OpenAI参数 (temperature, max_tokens等)
        
        Returns:
            str: 模型回复内容，失败返回None
        """
        if not messages:
            raise ValueError("消息列表不能为空")
        
        client = self._get_client(config_index)
        config = self.configs[config_index]
        
        # 默认参数
        params = {
            "model": config["model"],
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1000),
            **{k: v for k, v in kwargs.items() if k not in ["temperature", "max_tokens"]}
        }
        
        # 3次重试机制
        for attempt in range(3):
            try:
                print(f"[配置{config_index}] 第{attempt+1}次请求...")
                
                response = client.chat.completions.create(**params)
                
                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    print(f"[配置{config_index}] 请求成功")
                    return content
                else:
                    print(f"[配置{config_index}] 响应为空")
                    
            except Exception as e:
                print(f"[配置{config_index}] 第{attempt+1}次请求失败: {e}")
                if attempt < 2:  # 前两次失败时等待
                    time.sleep(1)
                continue
        
        print(f"[配置{config_index}] 3次请求均失败")
        return None
    
    def validate_model(self, config_index: int) -> bool:
        """
        模型验证 - 发送测试消息验证配置是否有效
        
        Args:
            config_index: 指定配置项索引
        
        Returns:
            bool: 验证是否成功
        """
        test_messages = [
            {"role": "user", "content": "你好"}
        ]
        
        try:
            print(f"[配置{config_index}] 开始验证...")
            
            # 限制字数节约资源
            result = self.call_model(
                config_index=config_index,
                messages=test_messages,
                max_tokens=20,  # 限制10个字左右
                temperature=0.1  # 降低随机性
            )
            
            if result and len(result.strip()) > 0:
                print(f"[配置{config_index}] 验证成功: {result.strip()}")
                return True
            else:
                print(f"[配置{config_index}] 验证失败: 无有效回复")
                return False
                
        except Exception as e:
            print(f"[配置{config_index}] 验证异常: {e}")
            return False
    
    def random_call(self, messages: List[Dict[str, str]], config_range: Optional[List[int]] = None, **kwargs) -> Optional[str]:
        """
        随机调用 - 从指定范围内随机选择配置进行调用
        
        Args:
            messages: 标准对话记录数组
            config_range: 指定配置范围，None表示全部配置
            **kwargs: 其他OpenAI参数
        
        Returns:
            str: 模型回复内容，失败返回None
        """
        # 确定可用的配置范围
        if config_range is None:
            available_configs = list(range(len(self.configs)))
        else:
            available_configs = [i for i in config_range if 0 <= i < len(self.configs)]
        
        if not available_configs:
            raise ValueError("没有可用的配置")
        
        # 随机选择配置
        selected_config = random.choice(available_configs)
        print(f"随机选择配置 {selected_config}")
        
        return self.call_model(selected_config, messages, **kwargs)
    
    def get_config_info(self, config_index: int) -> Dict[str, Any]:
        """获取配置信息（隐藏敏感信息）"""
        if config_index < 0 or config_index >= len(self.configs):
            raise ValueError(f"配置索引超出范围")
        
        config = self.configs[config_index].copy()
        # 隐藏API密钥
        config["apikey"] = config["apikey"][:8] + "..." if len(config["apikey"]) > 8 else "***"
        return config
    
    def list_configs(self) -> List[Dict[str, Any]]:
        """列出所有配置（隐藏敏感信息）"""
        return [self.get_config_info(i) for i in range(len(self.configs))]
    
    def validate_all_configs(self) -> Dict[int, bool]:
        """验证所有配置"""
        results = {}
        print("=== 验证所有配置 ===")
        
        for i in range(len(self.configs)):
            results[i] = self.validate_model(i)
            time.sleep(0.5)  # 避免请求过于频繁
        
        print(f"验证完成，有效配置: {sum(results.values())}/{len(results)}")
        return results

# 使用示例和测试
def test_openai_client():
    """测试OpenAI客户端功能"""
    
    print("=== OpenAI客户端测试 ===")
    
    # 初始化客户端
    client = OpenAIClient()
    
    # 列出配置
    print("\n1. 配置列表:")
    configs = client.list_configs()
    for i, config in enumerate(configs):
        print(f"  配置{i}: {config['model']} @ {config['url']}")
    
    # 验证所有配置
    print("\n2. 验证配置:")
    validation_results = client.validate_all_configs()
    
    # 找到有效配置进行测试
    valid_configs = [i for i, valid in validation_results.items() if valid]
    
    if valid_configs:
        print(f"\n3. 使用有效配置测试调用:")
        
        test_messages = [
            {"role": "user", "content": "请简单介绍一下Python编程语言"}
        ]
        
        # 测试指定配置调用
        config_index = valid_configs[0]
        print(f"\n3.1 指定配置{config_index}调用:")
        result = client.call_model(config_index, test_messages, max_tokens=100)
        if result:
            print(f"回复: {result}")
        
        # 测试随机调用
        print(f"\n3.2 随机调用 (范围: {valid_configs}):")
        result = client.random_call(test_messages, config_range=valid_configs, max_tokens=100)
        if result:
            print(f"回复: {result}")
    
    else:
        print("没有有效的配置可供测试")

if __name__ == "__main__":
    test_openai_client()