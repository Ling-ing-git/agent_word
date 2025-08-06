#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller 打包配置脚本
用于将 agent core.py 程序打包成独立的可执行文件
"""

import PyInstaller.__main__
import sys
import os

def build_executable():
    """构建可执行文件"""
    
    # PyInstaller 参数配置
    args = [
        '--onefile',  # 打包成单个文件
        '--windowed',  # Windows下不显示控制台窗口（可选）
        '--name=AgentWordProcessor',  # 可执行文件名称
        '--icon=icon.png',  # 图标文件（支持PNG格式）
        '--add-data=agent_config.json;.',  # 包含配置文件
        '--distpath=./dist',  # 输出目录
        '--workpath=./build',  # 临时文件目录
        '--specpath=.',  # spec文件目录
        '--clean',  # 清理临时文件
        '--hidden-import=openai',  # 确保包含openai库
        '--hidden-import=lxml',  # 确保包含lxml库
        '--hidden-import=PIL',  # 确保包含Pillow库
        '--hidden-import=json',
        '--hidden-import=subprocess',
        '--hidden-import=pathlib',
        '--hidden-import=re',
        '--hidden-import=io',
        '--hidden-import=contextlib',
        '--hidden-import=argparse',
        '--collect-all=openai',  # 收集openai的所有依赖
        'agent core.py'  # 主程序文件
    ]
    
    # 如果是Linux/Mac，移除windowed参数
    if sys.platform != 'win32':
        args = [arg for arg in args if arg != '--windowed']
    
    # 检查图标文件，支持多种格式
    icon_files = ['icon.png', 'icon.ico', 'icon.icns']
    icon_found = None
    for icon_file in icon_files:
        if os.path.exists(icon_file):
            icon_found = icon_file
            break
    
    if icon_found:
        # 更新图标参数
        args = [arg if not arg.startswith('--icon') else f'--icon={icon_found}' for arg in args]
        print(f"🎨 使用图标文件: {icon_found}")
    else:
        # 移除图标参数
        args = [arg for arg in args if not arg.startswith('--icon')]
        print("⚠️ 未找到图标文件，将使用默认图标")
    
    print("开始构建可执行文件...")
    print(f"参数: {' '.join(args)}")
    
    try:
        PyInstaller.__main__.run(args)
        print("\n✅ 构建完成！")
        print("📁 可执行文件位置: ./dist/AgentWordProcessor")
        print("\n📋 使用说明:")
        print("1. 将整个dist文件夹复制到目标机器")
        print("2. 运行 AgentWordProcessor 可执行文件")
        print("3. 程序会自动创建配置文件，请编辑API密钥")
        
    except Exception as e:
        print(f"❌ 构建失败: {e}")
        return False
    
    return True

if __name__ == "__main__":
    build_executable()