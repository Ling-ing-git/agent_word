#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
便携式Python分发打包脚本
创建包含Python运行时的完整打包版本
"""

import os
import sys
import shutil
import subprocess
import zipfile
import urllib.request
from pathlib import Path

class PortablePythonBuilder:
    def __init__(self):
        self.build_dir = Path("portable_build")
        self.python_version = "3.11.9"  # 指定Python版本
        
    def download_python_embedded(self):
        """下载Windows嵌入式Python"""
        if sys.platform == "win32":
            python_url = f"https://www.python.org/ftp/python/{self.python_version}/python-{self.python_version}-embed-amd64.zip"
            python_zip = self.build_dir / "python-embed.zip"
            
            print(f"正在下载Python {self.python_version} 嵌入式版本...")
            urllib.request.urlretrieve(python_url, python_zip)
            
            # 解压Python
            python_dir = self.build_dir / "python"
            with zipfile.ZipFile(python_zip, 'r') as zip_ref:
                zip_ref.extractall(python_dir)
            
            return python_dir
        else:
            print("Linux/Mac系统，将复制当前Python环境")
            return self.copy_python_environment()
    
    def copy_python_environment(self):
        """复制当前Python环境（Linux/Mac）"""
        python_dir = self.build_dir / "python"
        
        # 创建Python目录结构
        python_dir.mkdir(parents=True, exist_ok=True)
        
        # 复制Python解释器
        python_exe = shutil.which("python3") or shutil.which("python")
        if python_exe:
            shutil.copy2(python_exe, python_dir / "python")
            os.chmod(python_dir / "python", 0o755)
        
        return python_dir
    
    def install_dependencies(self, python_dir):
        """安装依赖包到便携式Python环境"""
        print("安装依赖包...")
        
        if sys.platform == "win32":
            python_exe = python_dir / "python.exe"
            # 需要先安装pip到嵌入式Python
            get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
            get_pip_path = self.build_dir / "get-pip.py"
            urllib.request.urlretrieve(get_pip_url, get_pip_path)
            
            # 安装pip
            subprocess.run([str(python_exe), str(get_pip_path), "--no-warn-script-location"])
        else:
            python_exe = python_dir / "python"
        
        # 安装依赖
        requirements = ["openai", "lxml", "Pillow"]
        for package in requirements:
            print(f"安装 {package}...")
            subprocess.run([
                str(python_exe), "-m", "pip", "install", 
                package, "--target", str(python_dir / "site-packages"),
                "--no-warn-script-location"
            ])
    
    def create_launcher(self, python_dir):
        """创建启动脚本"""
        if sys.platform == "win32":
            # Windows批处理文件
            launcher_content = f"""@echo off
cd /d "%~dp0"
python\\python.exe "agent core.py" %*
pause
"""
            launcher_path = self.build_dir / "启动程序.bat"
        else:
            # Linux/Mac shell脚本
            launcher_content = f"""#!/bin/bash
cd "$(dirname "$0")"
python/python "agent core.py" "$@"
"""
            launcher_path = self.build_dir / "start.sh"
        
        with open(launcher_path, "w", encoding="utf-8") as f:
            f.write(launcher_content)
        
        if sys.platform != "win32":
            os.chmod(launcher_path, 0o755)
    
    def copy_application_files(self):
        """复制应用程序文件"""
        print("复制应用程序文件...")
        
        files_to_copy = [
            "agent core.py",
            "requirements.txt",
            "README.md"
        ]
        
        for file_name in files_to_copy:
            if os.path.exists(file_name):
                shutil.copy2(file_name, self.build_dir)
        
        # 创建配置文件模板
        config_template = {
            "api_pool": ["your-api-key-here"],
            "current_position": 0,
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "temperature": 0.7,
            "max_tokens": 100400
        }
        
        import json
        with open(self.build_dir / "agent_config.json", "w", encoding="utf-8") as f:
            json.dump(config_template, f, ensure_ascii=False, indent=2)
    
    def create_readme(self):
        """创建使用说明"""
        readme_content = """# Agent Word Processor - 便携式版本

## 使用说明

1. **首次使用配置**：
   - 编辑 `agent_config.json` 文件
   - 替换 "your-api-key-here" 为您的实际API密钥

2. **启动程序**：
   - Windows: 双击 `启动程序.bat`
   - Linux/Mac: 运行 `./start.sh`

3. **目录说明**：
   - `python/` - 内嵌的Python运行环境
   - `agent core.py` - 主程序文件
   - `agent_config.json` - 配置文件

## 系统要求

- Windows 10及以上 / Linux / macOS
- 无需安装Python环境
- 需要网络连接访问AI API

## 故障排除

如果程序无法启动：
1. 检查API密钥配置是否正确
2. 确保网络连接正常
3. 查看控制台错误信息

"""
        
        with open(self.build_dir / "使用说明.txt", "w", encoding="utf-8") as f:
            f.write(readme_content)
    
    def build(self):
        """执行完整的构建过程"""
        print("开始构建便携式版本...")
        
        # 创建构建目录
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        self.build_dir.mkdir(parents=True)
        
        try:
            # 下载/复制Python环境
            python_dir = self.download_python_embedded()
            
            # 安装依赖
            self.install_dependencies(python_dir)
            
            # 复制应用文件
            self.copy_application_files()
            
            # 创建启动脚本
            self.create_launcher(python_dir)
            
            # 创建说明文档
            self.create_readme()
            
            print(f"\n✅ 便携式版本构建完成！")
            print(f"📁 输出目录: {self.build_dir.absolute()}")
            print(f"📦 总大小: {self.get_directory_size(self.build_dir):.1f} MB")
            print("\n将整个文件夹复制到目标机器即可使用")
            
        except Exception as e:
            print(f"❌ 构建失败: {e}")
            return False
        
        return True
    
    def get_directory_size(self, path):
        """计算目录大小（MB）"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
        return total_size / (1024 * 1024)

if __name__ == "__main__":
    builder = PortablePythonBuilder()
    builder.build()