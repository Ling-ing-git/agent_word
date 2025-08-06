#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图标格式转换工具
将PNG格式图标转换为ICO格式，用于PyInstaller打包
"""

from PIL import Image
import os
import sys

def convert_png_to_ico(png_path, ico_path=None, sizes=None):
    """
    将PNG图标转换为ICO格式
    
    Args:
        png_path: PNG文件路径
        ico_path: 输出ICO文件路径（可选）
        sizes: 图标尺寸列表（可选）
    """
    if not os.path.exists(png_path):
        print(f"❌ PNG文件不存在: {png_path}")
        return False
    
    if ico_path is None:
        ico_path = png_path.replace('.png', '.ico')
    
    if sizes is None:
        # 常用的图标尺寸
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    try:
        # 打开PNG图像
        img = Image.open(png_path)
        
        # 确保图像是RGBA模式（支持透明背景）
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 创建不同尺寸的图标
        icon_images = []
        for size in sizes:
            # 调整图像大小，保持高质量
            resized_img = img.resize(size, Image.Resampling.LANCZOS)
            icon_images.append(resized_img)
        
        # 保存为ICO文件
        icon_images[0].save(
            ico_path,
            format='ICO',
            sizes=sizes,
            append_images=icon_images[1:]
        )
        
        print(f"✅ 转换成功!")
        print(f"📁 输入文件: {png_path}")
        print(f"📁 输出文件: {ico_path}")
        print(f"🎨 包含尺寸: {', '.join([f'{w}x{h}' for w, h in sizes])}")
        
        return True
        
    except Exception as e:
        print(f"❌ 转换失败: {e}")
        return False

def auto_convert_icons():
    """自动查找并转换PNG图标"""
    png_files = [f for f in os.listdir('.') if f.lower().endswith('.png') and 'icon' in f.lower()]
    
    if not png_files:
        print("⚠️ 未找到PNG图标文件")
        print("💡 请将PNG图标文件放在当前目录，文件名包含'icon'")
        return False
    
    success_count = 0
    for png_file in png_files:
        print(f"\n🔄 处理文件: {png_file}")
        if convert_png_to_ico(png_file):
            success_count += 1
    
    print(f"\n📊 转换完成: {success_count}/{len(png_files)} 个文件")
    return success_count > 0

def create_sample_icon():
    """创建示例图标（如果没有图标文件）"""
    try:
        # 创建一个简单的示例图标
        img = Image.new('RGBA', (256, 256), (70, 130, 180, 255))  # 钢蓝色背景
        
        # 添加一些简单的图形
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        
        # 绘制圆形
        draw.ellipse([50, 50, 206, 206], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
        
        # 添加文字
        try:
            # 尝试使用系统字体
            font = ImageFont.truetype("arial.ttf", 60)
        except:
            # 如果找不到字体，使用默认字体
            font = ImageFont.load_default()
        
        # 绘制字母 "A"
        text = "A"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (256 - text_width) // 2
        text_y = (256 - text_height) // 2
        draw.text((text_x, text_y), text, fill=(0, 0, 0, 255), font=font)
        
        # 保存PNG和ICO
        img.save('icon.png')
        convert_png_to_ico('icon.png')
        
        print("✅ 已创建示例图标文件: icon.png 和 icon.ico")
        return True
        
    except Exception as e:
        print(f"❌ 创建示例图标失败: {e}")
        return False

def main():
    """主函数"""
    print("🎨 图标转换工具")
    print("=" * 40)
    
    if len(sys.argv) > 1:
        # 命令行模式
        png_file = sys.argv[1]
        ico_file = sys.argv[2] if len(sys.argv) > 2 else None
        convert_png_to_ico(png_file, ico_file)
    else:
        # 交互模式
        print("1. 自动转换当前目录的PNG图标")
        print("2. 创建示例图标")
        print("3. 手动指定文件")
        
        choice = input("\n请选择操作 (1/2/3): ").strip()
        
        if choice == '1':
            auto_convert_icons()
        elif choice == '2':
            create_sample_icon()
        elif choice == '3':
            png_file = input("请输入PNG文件路径: ").strip()
            ico_file = input("请输入ICO输出路径 (按回车使用默认): ").strip()
            ico_file = ico_file if ico_file else None
            convert_png_to_ico(png_file, ico_file)
        else:
            print("❌ 无效选择")

if __name__ == "__main__":
    main()