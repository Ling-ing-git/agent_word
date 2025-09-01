"""
OpenAI客户端核心 - 从JSON配置读取并创建客户端
"""

import json
from typing import Dict, Any, Optional
from openai import OpenAI

class OpenAIClientManager:
    """OpenAI客户端管理器"""
    
    def __init__(self, config_file: str = "model_config.json"):
        self.config_file = config_file
        self.client = None
        self.config = None
        
    def load_config(self) -> Dict[str, Any]:
        """从JSON文件读取模型配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            return self.config
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {self.config_file} 不存在")
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件JSON格式错误: {e}")
    
    def create_client(self) -> OpenAI:
        """根据配置创建OpenAI客户端"""
        if self.config is None:
            self.load_config()
        
        # 提取配置参数
        url = self.config.get("url")
        model = self.config.get("model") 
        api_key = self.config.get("apikey")
        
        # 验证必要参数
        if not url:
            raise ValueError("配置中缺少 'url' 参数")
        if not model:
            raise ValueError("配置中缺少 'model' 参数")
        if not api_key:
            raise ValueError("配置中缺少 'apikey' 参数")
        
        # 创建客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=url
        )
        
        return self.client
    
    def get_model_name(self) -> str:
        """获取配置的模型名称"""
        if self.config is None:
            self.load_config()
        return self.config.get("model")
    
    def get_client(self) -> OpenAI:
        """获取已创建的客户端"""
        if self.client is None:
            self.create_client()
        return self.client

# 使用示例
if __name__ == "__main__":
    # 创建示例配置文件
    example_config = {
        "url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo",
        "apikey": "your-api-key-here"
    }
    
    with open("model_config.json", "w", encoding="utf-8") as f:
        json.dump(example_config, f, indent=2, ensure_ascii=False)
    
    # 测试配置加载
    manager = OpenAIClientManager()
    try:
        config = manager.load_config()
        print("配置加载成功:")
        print(f"URL: {config['url']}")
        print(f"Model: {config['model']}")
        print(f"API Key: {config['apikey'][:10]}...")
        
        client = manager.create_client()
        print("客户端创建成功")
        
    except Exception as e:
        print(f"错误: {e}")