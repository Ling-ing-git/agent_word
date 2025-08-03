import sys
import json
import time
import os
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QSpinBox, QDoubleSpinBox, QGroupBox, QMessageBox,
                             QFileDialog, QScrollArea, QGridLayout, QSplitter,
                             QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
                             QComboBox, QTextEdit, QTextBrowser, QTextEdit, QFrame)
from PyQt6.QtGui import QFont, QPixmap, QDrag, QKeyEvent
from PyQt6.QtCore import Qt, QMimeData, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QFontMetrics
from openai import OpenAI
from advanced_word_scanner import AdvancedWordScanner
from folder_scanner import scan_folder_simple
from agent_core import load_config, build_system_prompt, handle_function_call
import markdown

class DraggableTreeWidget(QTreeWidget):
    """可拖拽的树形文件列表"""
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setHeaderLabel('文件结构')
        self.setColumnCount(1)
    
    def startDrag(self, actions):
        """开始拖拽"""
        item = self.currentItem()
        if item and item.data(0, Qt.ItemDataRole.UserRole):  # 只有文件可以拖拽
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(item.data(0, Qt.ItemDataRole.UserRole))
            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.CopyAction)

class NotificationWidget(QFrame):
    """浮动通知窗口"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        #self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(350, 80)
        
        # 设置样式
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 12px;
                border: 2px solid #000000;
            }
            QLabel {
                color: #000000;
                font-weight: bold;
                font-size: 13px;
                background: transparent;
                border: none;
            }
        """)
        
        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        # 标题标签
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # 内容标签
        self.content_label = QLabel()
        self.content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("font-size: 12px; color: #e0e0e0;")
        layout.addWidget(self.content_label)
        
        # 动画
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(300)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.slide_animation = QPropertyAnimation(self, b"geometry")
        self.slide_animation.setDuration(400)
        self.slide_animation.setEasingCurve(QEasingCurve.Type.OutBack)
        
        # 自动隐藏定时器
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_notification)
        
    def show_notification(self, title, content, notification_type="info", duration=3000):
        """显示通知"""
        self.title_label.setText(title)
        self.content_label.setText(content)
        
        # 根据类型设置不同的样式
        if notification_type == "success":
            icon = "✅"
            border_color = "#4caf50"
            bg_color = "#ffffff"
        elif notification_type == "error":
            icon = "❌"
            border_color = "#f44336"
            bg_color = "#ffffff"
        elif notification_type == "warning":
            icon = "⚠️"
            border_color = "#ff9800"
            bg_color = "#ffffff"
        elif notification_type == "file":
            icon = "📄"
            border_color = "#2196f3"
            bg_color = "#ffffff"
        elif notification_type == "code":
            icon = "🐍"
            border_color = "#9c27b0"
            bg_color = "#ffffff"
        else:  # info
            icon = "ℹ️"
            border_color = "#607d8b"
            bg_color = "#ffffff"
        
        self.title_label.setText(f"{icon} {title}")
        
        # 更新样式
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 12px;
                border: 2px solid {border_color};
            }}
            QLabel {{
                color: #000000;
                font-weight: bold;
                background: transparent;
                border: none;
            }}
        """)
        
        # 获取父窗口位置
        if self.parent():
            parent_rect = self.parent().geometry()
            # 计算通知窗口位置（右上角）
            x = parent_rect.right() - self.width() - 20
            y = parent_rect.top() + 80
        else:
            # 如果没有父窗口，显示在屏幕右上角
            screen = QApplication.primaryScreen().geometry()
            x = screen.right() - self.width() - 20
            y = 80
        
        # 设置初始位置（从右边滑入）
        start_rect = QRect(x + self.width(), y, self.width(), self.height())
        end_rect = QRect(x, y, self.width(), self.height())
        
        self.setGeometry(start_rect)
        self.setWindowOpacity(0.0)
        self.show()
        
        # 滑入动画
        self.slide_animation.setStartValue(start_rect)
        self.slide_animation.setEndValue(end_rect)
        
        # 淡入动画
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        
        # 开始动画
        self.slide_animation.start()
        self.fade_animation.start()
        
        # 设置自动隐藏
        self.hide_timer.start(duration)
    
    def hide_notification(self):
        """隐藏通知"""
        # 淡出动画
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(self.close)
        self.fade_animation.start()

class NotificationManager:
    """通知管理器"""
    def __init__(self, parent_window):
        self.parent_window = parent_window
        self.active_notifications = []
        
    def show_notification(self, title, content, notification_type="info", duration=3000):
        """显示通知"""
        # 清理已关闭的通知
        self.active_notifications = [n for n in self.active_notifications if n.isVisible()]
        
        # 如果有太多通知，关闭最老的
        if len(self.active_notifications) >= 3:
            oldest = self.active_notifications.pop(0)
            oldest.close()
        
        # 创建新通知
        notification = NotificationWidget(self.parent_window)
        notification.show_notification(title, content, notification_type, duration)
        self.active_notifications.append(notification)
        
        return notification
    
    def clear_all(self):
        """清除所有通知"""
        for notification in self.active_notifications:
            notification.close()
        self.active_notifications.clear()

class StreamingWorker(QThread):
    """流式响应工作线程 - 修改版，支持真正的流式输出"""
    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    chunk_received = pyqtSignal(str)  # 实时流式更新
    stopped = pyqtSignal()  # 停止信号
    # 新增：文件操作通知信号
    file_created = pyqtSignal(str, str)  # 文件类型, 文件路径
    python_executed = pyqtSignal(str, bool, str)  # 文件名, 是否成功, 结果消息
    python_execution_feedback = pyqtSignal(str, bool, str, str)  # 文件名, 成功, stdout, stderr
    
    def __init__(self, messages, config, system_prompt):
        super().__init__()
        self.messages = messages
        self.config = config
        self.system_prompt = system_prompt
        self.is_running = True
        self._stop_requested = False
    
    def stop(self):
        """停止线程"""
        self.is_running = False
        self._stop_requested = True
    
    def run(self):
        try:
            if self._stop_requested:
                return
            
            # 加载agent_core配置
            from agent_core import load_config, get_current_api_key, rotate_api_key, move_api_to_rubbish
            
            # 获取配置
            agent_config = load_config()
            
            # 检查是否有可用的API
            if not agent_config.get("api_pool"):
                self.error_occurred.emit("没有可用的API密钥")
                return
            
            # 获取当前API key
            current_api_key = get_current_api_key(agent_config)
            if not current_api_key:
                self.error_occurred.emit("无法获取API密钥")
                return
            
            # 创建OpenAI客户端
            client = OpenAI(
                api_key=current_api_key,
                base_url=agent_config.get("base_url", "https://api.openai.com/v1")
            )
            
            # 构建完整消息
            full_messages = [{"role": "system", "content": self.system_prompt}]
            for msg in self.messages:
                full_messages.append({"role": msg["role"], "content": msg["content"]})
            
            # 创建流式请求
            payload = {
                "model": agent_config["model"],
                "messages": full_messages,
                "max_tokens": agent_config.get("max_tokens", 2000),
                "temperature": agent_config.get("temperature", 0.7),
                "stream": True
            }
            
            # 执行流式API调用
            collected_content = ""
            
            try:
                stream = client.chat.completions.create(**payload)
                
                for chunk in stream:
                    if self._stop_requested:
                        break
                        
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        collected_content += content
                        
                        # 实时发送chunk到GUI
                        if self.is_running:
                            self.chunk_received.emit(content)
                
                # 发送完整响应
                if self.is_running and not self._stop_requested:
                    self.response_received.emit(collected_content)
                    
                    # 在响应完成后处理function call
                    if collected_content:
                        self.process_function_calls(collected_content)
                    
                    # API调用成功，轮换到下一个
                    
                    
            except Exception as api_error:
                error_msg = str(api_error).lower()
                
                # 检查是否是API失效错误
                if any(keyword in error_msg for keyword in ["quota", "billing", "insufficient", "invalid", "unauthorized", "forbidden"]):
                    # 将失效API移到垃圾箱
                    move_api_to_rubbish(agent_config, agent_config["current_position"])
                    
                    if not agent_config["api_pool"]:
                        self.error_occurred.emit("所有API密钥都已失效")
                    else:
                        self.error_occurred.emit(f"API失效已移除，切换到下一个API")
                else:
                    self.error_occurred.emit(f"API调用失败: {str(api_error)}")
            
        except Exception as e:
            if self.is_running and not self._stop_requested:
                self.error_occurred.emit(f"线程执行失败: {str(e)}")
    
    def process_function_calls(self, content):
        """处理函数调用并发送通知"""
        pattern = re.compile(r"<functioncall>\s*filename:\s*(.*?)\s*type:\s*(.*?)\s*content:\s*([\s\S]*?)</functioncall>", re.DOTALL)
        matches = pattern.findall(content)
        
        for filename, filetype, file_content in matches:
            filename = filename.strip()
            filetype = filetype.strip().lower()
            file_content = file_content.strip()
            
            try:
                if filetype == "txt":
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(file_content)
                    self.file_created.emit("文本文件", filename)
                    
                elif filetype == "json":
                    json_obj = json.loads(file_content)
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(json_obj, f, ensure_ascii=False, indent=2)
                    self.file_created.emit("JSON文件", filename)
                    
                elif filetype == "python":
                    # 创建Python文件
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(file_content)
                    self.file_created.emit("Python文件", filename)
                    
                    # 执行Python代码
                    success, result = self.execute_python_safely(filename)
                    self.python_executed.emit(filename, success, result)
                    
                elif filetype == "exec":
                    # 直接执行Python代码
                    success, result = self.execute_python_code_direct(file_content)
                    self.python_executed.emit("内联代码", success, result)
                    
            except Exception as e:
                self.python_executed.emit(filename, False, f"处理失败: {str(e)}")
    
    def execute_python_safely(self, filename, timeout=60):
        """安全执行Python文件"""
        try:
            import subprocess
            import sys
            
            result = subprocess.run(
                [sys.executable, filename], 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                cwd=os.getcwd()
            )
            
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            success = result.returncode == 0
            
            # 发送详细的执行反馈信号
            self.python_execution_feedback.emit(filename, success, stdout, stderr)
            
            if success:
                output = stdout if stdout else "执行完成"
                return True, output
            else:
                error_output = stderr if stderr else f"返回码: {result.returncode}"
                return False, error_output
                
        except subprocess.TimeoutExpired:
            error_msg = f"执行超时 (>{timeout}秒)"
            self.python_execution_feedback.emit(filename, False, "", error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"执行异常: {str(e)}"
            self.python_execution_feedback.emit(filename, False, "", error_msg)
            return False, error_msg
    
    def execute_python_code_direct(self, code):
        """直接执行Python代码"""
        try:
            import io
            import sys
            from contextlib import redirect_stdout, redirect_stderr
            
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code)
            
            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()
            success = not stderr_output
            
            # 发送详细的执行反馈信号
            self.python_execution_feedback.emit("内联代码", success, stdout_output, stderr_output)
            
            if stderr_output:
                return False, stderr_output
            else:
                output = stdout_output if stdout_output else "执行完成"
                return True, output
                
        except Exception as e:
            error_msg = f"执行异常: {str(e)}"
            self.python_execution_feedback.emit("内联代码", False, "", error_msg)
            return False, error_msg

class MarkdownStreamer(QTextEdit):
    """支持Markdown流式渲染的文本编辑器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.markdown_buffer = ""
        self.is_in_code_block = False
        self.code_block_language = ""
        
        # 检查markdown模块
        try:
            import markdown
            self.markdown_available = True
        except ImportError:
            self.markdown_available = False
            print("警告: markdown模块未安装，将使用纯文本显示")
        
        # 设置样式
        self.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 15px;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-size: 13px;
                line-height: 1.6;
            }
            QTextEdit:focus {
                border: 2px solid #2196f3;
            }
        """)
    
    def append_markdown_chunk(self, chunk):
        """追加Markdown块并智能渲染"""
        self.markdown_buffer += chunk
        
        # 检测是否形成完整的Markdown块
        if self.is_markdown_block_complete():
            self.render_markdown_block()
            self.markdown_buffer = ""
        else:
            # 临时显示原始文本（避免闪烁）
            self.insert_plain_text_chunk(chunk)
    
    def is_markdown_block_complete(self):
        """检测Markdown块是否完整"""
        text = self.markdown_buffer.strip()
        
        # 空行分隔段落
        if text.endswith('\n\n'):
            return True
        
        # 代码块结束
        if text.endswith('```') and self.is_in_code_block:
            return True
        
        # 列表项结束（以换行符结尾）
        if text.endswith('\n') and (text.startswith('- ') or text.startswith('* ') or text.startswith('1. ')):
            return True
        
        # 标题结束
        if text.endswith('\n') and text.startswith('#'):
            return True
        
        # 引用结束
        if text.endswith('\n') and text.startswith('>'):
            return True
        
        return False
    
    def render_markdown_block(self):
        """渲染完整的Markdown块"""
        if not self.markdown_buffer.strip():
            return
        
        # 渲染Markdown为HTML
        html_content = self.render_markdown_to_html(self.markdown_buffer)
        
        # 插入HTML内容
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        
        # 删除临时显示的原始文本
        self.delete_last_chunk(len(self.markdown_buffer))
        
        # 插入渲染后的HTML
        self.insertHtml(html_content)
        
        # 滚动到底部
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def render_markdown_to_html(self, text):
        """将Markdown文本渲染为HTML"""
        if not self.markdown_available:
            # 如果markdown模块不可用，返回简单的HTML格式
            return text.replace('\n', '<br>').replace('**', '<strong>').replace('*', '<em>')
        
        try:
            # 基本的Markdown渲染，使用安全的扩展
            extensions = []
            # 只添加存在的扩展
            available_extensions = ['fenced_code', 'tables']
            for ext in available_extensions:
                try:
                    md_test = markdown.Markdown(extensions=[ext])
                    extensions.append(ext)
                except:
                    continue
            
            md = markdown.Markdown(extensions=extensions)
            html = md.convert(text)
            
            # 添加代码高亮样式
            html = html.replace('<pre><code>', '<pre><code style="background-color: #f8f9fa; padding: 12px; border-radius: 6px; border: 1px solid #e9ecef; font-family: \'Consolas\', \'Monaco\', monospace; font-size: 12px; line-height: 1.4; overflow-x: auto;">')
            html = html.replace('</code></pre>', '</code></pre>')
            
            # 改进表格样式
            html = html.replace('<table>', '<table style="border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid #ddd;">')
            html = html.replace('<th>', '<th style="border: 1px solid #ddd; padding: 8px; background-color: #f8f9fa; font-weight: bold;">')
            html = html.replace('<td>', '<td style="border: 1px solid #ddd; padding: 8px;">')
            
            # 改进列表样式
            html = html.replace('<ul>', '<ul style="margin: 10px 0; padding-left: 20px;">')
            html = html.replace('<ol>', '<ol style="margin: 10px 0; padding-left: 20px;">')
            html = html.replace('<li>', '<li style="margin: 5px 0;">')
            
            # 改进标题样式
            html = html.replace('<h1>', '<h1 style="color: #2c3e50; margin: 20px 0 10px 0; font-size: 18px; font-weight: 600;">')
            html = html.replace('<h2>', '<h2 style="color: #2c3e50; margin: 18px 0 8px 0; font-size: 16px; font-weight: 600;">')
            html = html.replace('<h3>', '<h3 style="color: #2c3e50; margin: 15px 0 6px 0; font-size: 14px; font-weight: 600;">')
            
            return html
        except Exception as e:
            print(f"Markdown渲染失败: {e}")
            return text.replace('\n', '<br>')
    
    def insert_plain_text_chunk(self, chunk):
        """插入纯文本块（临时显示）"""
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.insertPlainText(chunk)
        
        # 滚动到底部
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def delete_last_chunk(self, length):
        """删除最后插入的文本块"""
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.KeepAnchor, length)
        cursor.removeSelectedText()
    
    def flush_buffer(self):
        """强制刷新缓冲区"""
        if self.markdown_buffer.strip():
            self.render_markdown_block()
            self.markdown_buffer = ""

class ChatInputWidget(QTextEdit):
    """支持Enter发送、Shift+Enter换行的聊天输入框"""
    def __init__(self, send_callback):
        super().__init__()
        self.send_callback = send_callback
        self.setMaximumHeight(120)
        self.setPlaceholderText("请输入消息...\nEnter发送  Shift+Enter换行\nCtrl+S停止  Ctrl+Z撤回  Ctrl+L清除")
        self.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-size: 13px;
                line-height: 1.4;
            }
            QTextEdit:focus {
                border: 2px solid #2196f3;
            }
        """)
    
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter: 换行
                super().keyPressEvent(event)
            else:
                # Enter: 发送
                self.send_callback()
        else:
            super().keyPressEvent(event)

class APIConfigApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.text_items = []
        self.image_items = []
        self.chat_messages = []
        self.selected_word_file = None  # 选中的Word文件路径
        self.streaming_worker = None  # 添加worker引用
        
        # 添加通知管理器
        self.notification_manager = NotificationManager(self)
        
        self.init_ui()
        self.load_config()
        self.setup_shortcuts()  # 设置快捷键
    
    def init_ui(self):
        self.setWindowTitle('API配置工具 + Word解析 + 文件夹扫描 + 智能对话')
        self.setGeometry(100, 100, 1600, 1000)
        self.setMinimumSize(1400, 800)
        
        # 设置黑白风格
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #000000;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #000000;
            }
            QLineEdit {
                padding: 8px;
                border: 2px solid #cccccc;
                border-radius: 3px;
                font-size: 12px;
                background: white;
                color: #000000;
            }
            QLineEdit:focus {
                border: 2px solid #000000;
            }
            QPushButton {
                background-color: #000000;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #333333;
            }
            QPushButton:pressed {
                background-color: #666666;
            }
            QLabel {
                color: #000000;
                font-weight: bold;
                font-size: 12px;
            }
            QSpinBox, QDoubleSpinBox {
                padding: 8px;
                border: 2px solid #cccccc;
                border-radius: 3px;
                font-size: 12px;
                background: white;
                color: #000000;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #000000;
            }
            QListWidget, QTreeWidget {
                border: 2px solid #cccccc;
                border-radius: 3px;
                background: white;
                color: #000000;
            }
            QListWidget::item, QTreeWidget::item {
                padding: 5px;
                border-bottom: 1px solid #eeeeee;
            }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background-color: #e0e0e0;
            }
            QTextEdit, QTextBrowser {
                border: 2px solid #cccccc;
                border-radius: 3px;
                background: white;
                color: #000000;
                font-family: "Consolas", "Monaco", monospace;
            }
            QComboBox {
                padding: 8px;
                border: 2px solid #cccccc;
                border-radius: 3px;
                background: white;
                color: #000000;
            }
        """)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(8)  # 设置分割器手柄宽度
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
                border-radius: 3px;
            }
            QSplitter::handle:hover {
                background-color: #d0d0d0;
            }
            QSplitter::handle:pressed {
                background-color: #c0c0c0;
            }
        """)
        
        central_widget.setLayout(QHBoxLayout())
        central_widget.layout().setContentsMargins(0, 0, 0, 0)  # 移除边距
        central_widget.layout().addWidget(main_splitter)
        
        # 左侧文件列表面板
        self.create_left_panel(main_splitter)
        
        # 右侧功能面板 
        self.create_right_panel(main_splitter)
        
        # 设置分割器比例 - 左侧较窄，右侧较宽
        main_splitter.setSizes([350, 1250])
        main_splitter.setCollapsible(0, False)  # 左侧面板不可折叠
        main_splitter.setCollapsible(1, False)  # 右侧面板不可折叠
    
    def create_left_panel(self, splitter):
        """创建左侧文件列表面板"""
        left_widget = QWidget()
        left_widget.setMinimumWidth(250)  # 设置最小宽度
        left_widget.setMaximumWidth(600)  # 设置最大宽度
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(8, 8, 8, 8)  # 设置边距
        left_layout.setSpacing(8)  # 设置间距
        left_widget.setLayout(left_layout)
        
        # 添加左侧面板样式
        left_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-right: 2px solid #e0e0e0;
            }
            QGroupBox {
                background-color: #ffffff;
                margin: 2px;
                padding-top: 15px;
            }
        """)
        
        # 文件夹扫描组 - 紧凑设计
        folder_group = QGroupBox('📁 文件夹扫描')
        folder_layout = QVBoxLayout()
        folder_layout.setContentsMargins(12, 8, 12, 8)
        folder_layout.setSpacing(6)
        folder_group.setLayout(folder_layout)
        left_layout.addWidget(folder_group)
        
        # 扫描按钮
        self.scan_folder_btn = QPushButton('🔍 扫描文件夹')
        self.scan_folder_btn.clicked.connect(self.scan_and_select_folder)
        self.scan_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        folder_layout.addWidget(self.scan_folder_btn)
        
        # 当前文件夹显示
        self.folder_path_label = QLabel('📂 未选择文件夹')
        self.folder_path_label.setStyleSheet("""
            color: #666666; 
            font-weight: normal; 
            font-size: 10px;
            padding: 4px;
            background-color: #f5f5f5;
            border-radius: 3px;
        """)
        self.folder_path_label.setWordWrap(True)
        folder_layout.addWidget(self.folder_path_label)
        
        # 文件筛选组 - 紧凑设计
        filter_group = QGroupBox('🔧 文件筛选')
        filter_layout = QVBoxLayout()
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(6)
        filter_group.setLayout(filter_layout)
        left_layout.addWidget(filter_group)
        
        # 文件类型筛选 - 垂直布局更节省空间
        filter_type_label = QLabel('类型:')
        filter_type_label.setStyleSheet("font-size: 11px; color: #333333; font-weight: bold;")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(['全部文件', '图片文件', '文档文件', '文本文件', '自定义'])
        self.filter_combo.currentTextChanged.connect(self.filter_files)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                font-size: 10px;
                min-height: 20px;
            }
        """)
        filter_layout.addWidget(filter_type_label)
        filter_layout.addWidget(self.filter_combo)
        
        # 自定义筛选
        custom_filter_label = QLabel('自定义:')
        custom_filter_label.setStyleSheet("font-size: 11px; color: #333333; font-weight: bold;")
        self.custom_filter_edit = QLineEdit()
        self.custom_filter_edit.setPlaceholderText('*.txt, *.docx')
        self.custom_filter_edit.textChanged.connect(self.filter_files)
        self.custom_filter_edit.setStyleSheet("""
            QLineEdit {
                padding: 4px 8px;
                font-size: 10px;
                min-height: 20px;
            }
        """)
        filter_layout.addWidget(custom_filter_label)
        filter_layout.addWidget(self.custom_filter_edit)
        
        # 文件列表组 - 占主要空间
        file_group = QGroupBox('📄 文件列表')
        file_layout = QVBoxLayout()
        file_layout.setContentsMargins(12, 8, 12, 8)
        file_layout.setSpacing(6)
        file_group.setLayout(file_layout)
        left_layout.addWidget(file_group, 1)  # 设置拉伸因子为1，占据剩余空间
        
        # 可拖拽的树形文件列表
        self.file_tree = DraggableTreeWidget()
        self.file_tree.setMinimumHeight(300)
        self.file_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: #ffffff;
                font-size: 11px;
            }
            QTreeWidget::item {
                padding: 3px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTreeWidget::item:hover {
                background-color: #e8f4f8;
            }
            QTreeWidget::item:selected {
                background-color: #d4e6f1;
                color: #000000;
            }
        """)
        file_layout.addWidget(self.file_tree)
        
        # 文件统计标签
        self.file_count_label = QLabel('📊 文件数量: 0')
        self.file_count_label.setStyleSheet("""
            color: #666666; 
            font-weight: normal; 
            font-size: 10px;
            padding: 4px;
            background-color: #f5f5f5;
            border-radius: 3px;
            text-align: center;
        """)
        self.file_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_layout.addWidget(self.file_count_label)
        
        # 检查按钮
        self.check_rules_btn = QPushButton('🔍 检查规则')
        self.check_rules_btn.clicked.connect(self.check_replace_rules)
        self.check_rules_btn.setStyleSheet("""
            QPushButton {
                background-color: #20c997;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                margin-top: 4px;
            }
            QPushButton:hover {
                background-color: #1aa085;
            }
            QPushButton:pressed {
                background-color: #148f77;
            }
        """)
        file_layout.addWidget(self.check_rules_btn)
        
        splitter.addWidget(left_widget)
    
    def create_right_panel(self, splitter):
        """创建右侧功能面板"""
        # 创建滚动区域
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
        """)
        
        # 创建右侧内容容器
        right_content = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(15, 15, 15, 15)  # 设置边距
        right_layout.setSpacing(15)  # 设置间距
        right_content.setLayout(right_layout)
        right_scroll.setWidget(right_content)
        
        # 标题
        title_label = QLabel('🤖 Agent Word - 智能文档处理工具')
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 26px;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0 20px 0;
            padding: 15px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #f8f9fa, stop:1 #e9ecef);
            border-radius: 10px;
            border: 2px solid #dee2e6;
        """)
        right_layout.addWidget(title_label)
        
        # 创建垂直分割器来分隔配置区和聊天区
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        vertical_splitter.setHandleWidth(6)
        vertical_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
                border-radius: 2px;
            }
            QSplitter::handle:hover {
                background-color: #d0d0d0;
            }
        """)
        right_layout.addWidget(vertical_splitter, 1)
        
        # 上半部分：配置区域
        config_widget = QWidget()
        config_layout = QVBoxLayout()
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)
        config_widget.setLayout(config_layout)
        
        # API配置组
        api_group = QGroupBox('⚙️ API配置')
        api_layout = QVBoxLayout()
        api_layout.setContentsMargins(15, 12, 15, 12)
        api_layout.setSpacing(8)
        api_group.setLayout(api_layout)
        config_layout.addWidget(api_group)
        
        # URL配置
        url_layout = QHBoxLayout()
        url_label = QLabel('URL:')
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText('请输入API URL')
        self.url_edit.setAcceptDrops(True)
        self.url_edit.dropEvent = self.handle_drop
        self.url_edit.dragEnterEvent = self.handle_drag_enter
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)
        api_layout.addLayout(url_layout)
        
        # API Key配置
        key_layout = QHBoxLayout()
        key_label = QLabel('API Key:')
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText('请输入API Key')
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_edit)
        api_layout.addLayout(key_layout)
        
        # API池状态显示
        pool_layout = QHBoxLayout()
        pool_label = QLabel('API池状态:')
        self.pool_status_label = QLabel('未配置')
        self.pool_status_label.setStyleSheet("color: #666666; font-weight: normal;")
        pool_layout.addWidget(pool_label)
        pool_layout.addWidget(self.pool_status_label)
        api_layout.addLayout(pool_layout)
        
        # 添加API到池的按钮
        add_api_layout = QHBoxLayout()
        self.add_api_btn = QPushButton('添加API到池')
        self.add_api_btn.clicked.connect(self.add_api_to_pool)
        add_api_layout.addWidget(self.add_api_btn)
        api_layout.addLayout(add_api_layout)
        
        # Model配置
        model_layout = QHBoxLayout()
        model_label = QLabel('Model:')
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText('请输入模型名称')
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_edit)
        api_layout.addLayout(model_layout)
        
        # 参数配置组
        param_group = QGroupBox('🎛️ 参数配置')
        param_layout = QVBoxLayout()
        param_layout.setContentsMargins(15, 12, 15, 12)
        param_layout.setSpacing(8)
        param_group.setLayout(param_layout)
        config_layout.addWidget(param_group)
        
        # Temperature配置
        temp_layout = QHBoxLayout()
        temp_label = QLabel('Temperature:')
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        self.temp_spin.setDecimals(1)
        temp_layout.addWidget(temp_label)
        temp_layout.addWidget(self.temp_spin)
        param_layout.addLayout(temp_layout)
        
        # Max Tokens配置
        tokens_layout = QHBoxLayout()
        tokens_label = QLabel('Max Tokens:')
        self.tokens_spin = QSpinBox()
        self.tokens_spin.setRange(100, 10000000)
        self.tokens_spin.setValue(2000)
        self.tokens_spin.setSingleStep(100)
        tokens_layout.addWidget(tokens_label)
        tokens_layout.addWidget(self.tokens_spin)
        param_layout.addLayout(tokens_layout)
        
        # API状态显示
        self.status_label = QLabel('⏳ 等待测试...')
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 13px;
            font-weight: bold;
            padding: 12px;
            border: 2px solid #cccccc;
            border-radius: 8px;
            background-color: #f8f9fa;
            color: #6c757d;
        """)
        config_layout.addWidget(self.status_label)
        
        # API测试按钮
        self.test_btn = QPushButton('🧪 测试并保存配置')
        self.test_btn.clicked.connect(self.test_and_save)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        config_layout.addWidget(self.test_btn)
        
        # Word解析模块
        word_group = QGroupBox('📄 Word解析模块')
        word_layout = QVBoxLayout()
        word_layout.setContentsMargins(15, 12, 15, 12)
        word_layout.setSpacing(8)
        word_group.setLayout(word_layout)
        config_layout.addWidget(word_group)
        
        # 文件选择
        file_layout = QHBoxLayout()
        file_label = QLabel('选择文件:')
        self.file_path_label = QLabel('未选择文件')
        self.file_path_label.setStyleSheet("color: #666666; font-weight: normal;")
        self.browse_btn = QPushButton('浏览')
        self.browse_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_path_label)
        file_layout.addWidget(self.browse_btn)
        word_layout.addLayout(file_layout)
        
        # 文字内容区域
        self.text_group = QGroupBox('📝 文字内容')
        self.text_layout = QVBoxLayout()
        self.text_layout.setContentsMargins(15, 12, 15, 12)
        self.text_layout.setSpacing(8)
        self.text_group.setLayout(self.text_layout)
        config_layout.addWidget(self.text_group)
        
        # 图片内容区域
        self.image_group = QGroupBox('🖼️ 图片内容')
        self.image_layout = QVBoxLayout()
        self.image_layout.setContentsMargins(15, 12, 15, 12)
        self.image_layout.setSpacing(8)
        self.image_group.setLayout(self.image_layout)
        config_layout.addWidget(self.image_group)
        
        # 将配置区域添加到垂直分割器
        vertical_splitter.addWidget(config_widget)
        
        # 下半部分：智能对话模块
        chat_group = QGroupBox('💬 智能对话')
        chat_layout = QVBoxLayout()
        chat_layout.setContentsMargins(15, 12, 15, 12)
        chat_layout.setSpacing(10)
        chat_group.setLayout(chat_layout)
        
        # 对话历史显示
        chat_display_layout = QHBoxLayout()
        
        # 字体大小控制
        font_control_layout = QVBoxLayout()
        font_label = QLabel('字体大小:')
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        font_control_layout.addWidget(font_label)
        font_control_layout.addWidget(self.font_size_spin)
        font_control_layout.addStretch()
        chat_display_layout.addLayout(font_control_layout)
        
        # 对话显示区域
        self.chat_display = MarkdownStreamer()
        self.chat_display.setMinimumHeight(400)  # 增加最小高度
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Consolas", 12))
        chat_display_layout.addWidget(self.chat_display)
        
        chat_layout.addLayout(chat_display_layout)
        
        # 输入区域
        input_layout = QHBoxLayout()
        self.chat_input = ChatInputWidget(self.send_message)
        input_layout.addWidget(self.chat_input)
        
        # 按钮区域
        button_layout = QVBoxLayout()
        
        self.send_btn = QPushButton('📤 发送')
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 10px 18px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
        """)
        button_layout.addWidget(self.send_btn)
        
        # 停止按钮
        self.stop_btn = QPushButton('⏹️ 停止')
        self.stop_btn.clicked.connect(self.stop_streaming)
        self.stop_btn.setEnabled(False)  # 初始状态禁用
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #fd7e14;
                color: white;
                border: none;
                padding: 10px 18px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e8690b;
            }
            QPushButton:pressed {
                background-color: #dc5f0a;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        button_layout.addWidget(self.stop_btn)
        
        # 撤回按钮
        self.undo_btn = QPushButton('↩️ 撤回')
        self.undo_btn.clicked.connect(self.undo_last_message)
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                border: none;
                padding: 10px 18px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #5a359a;
            }
            QPushButton:pressed {
                background-color: #4e2a84;
            }
        """)
        button_layout.addWidget(self.undo_btn)
        
        self.clear_btn = QPushButton('🗑️ 清除')
        self.clear_btn.clicked.connect(self.clear_chat_history)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 10px 18px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
        """)
        button_layout.addWidget(self.clear_btn)
        
        input_layout.addLayout(button_layout)
        chat_layout.addLayout(input_layout)
        
        # 将聊天组添加到垂直分割器
        vertical_splitter.addWidget(chat_group)
        
        # 设置垂直分割器比例 - 配置区域较小，聊天区域较大
        vertical_splitter.setSizes([600, 800])
        vertical_splitter.setCollapsible(0, False)  # 配置区域不可折叠
        vertical_splitter.setCollapsible(1, False)  # 聊天区域不可折叠
        
        # 模板构建模块 - 移到配置区域
        template_group = QGroupBox('🔧 构建模板')
        template_layout = QVBoxLayout()
        template_layout.setContentsMargins(15, 12, 15, 12)
        template_layout.setSpacing(8)
        template_group.setLayout(template_layout)
        config_layout.addWidget(template_group)
        
        # 导出按钮放在上面
        export_btn = QPushButton('📤 导出到对话框')
        export_btn.clicked.connect(self.export_template_to_chat)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
            QPushButton:pressed {
                background-color: #0f6674;
            }
        """)
        template_layout.addWidget(export_btn)
        
        # 可替换内容区域
        content_label = QLabel('可替换内容:')
        template_layout.addWidget(content_label)
        
        # 替换项容器
        self.replace_container = QWidget()
        self.replace_layout = QVBoxLayout()
        self.replace_container.setLayout(self.replace_layout)
        template_layout.addWidget(self.replace_container)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        add_text_btn = QPushButton('➕ 文字项')
        add_text_btn.clicked.connect(self.add_text_item)
        add_text_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        add_image_btn = QPushButton('🖼️ 图片项')
        add_image_btn.clicked.connect(self.add_image_item)
        add_image_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        button_layout.addWidget(add_text_btn)
        button_layout.addWidget(add_image_btn)
        template_layout.addLayout(button_layout)
        
        # 生成文档模块 - 移到配置区域
        generate_group = QGroupBox('🚀 生成文档')
        generate_layout = QVBoxLayout()
        generate_layout.setContentsMargins(15, 12, 15, 12)
        generate_layout.setSpacing(8)
        generate_group.setLayout(generate_layout)
        config_layout.addWidget(generate_group)
        
        # 生成文档按钮
        self.generate_btn = QPushButton('🚀 生成文档')
        self.generate_btn.clicked.connect(self.generate_document)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #218838;
                transform: translateY(-1px);
            }
            QPushButton:pressed {
                background-color: #1e7e34;
                transform: translateY(1px);
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        generate_layout.addWidget(self.generate_btn)
        
        # 生成状态显示
        self.generate_status_label = QLabel('📋 准备生成文档...')
        self.generate_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.generate_status_label.setStyleSheet("""
            font-size: 12px;
            font-weight: bold;
            padding: 12px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            background-color: #f8f9fa;
            color: #6c757d;
        """)
        generate_layout.addWidget(self.generate_status_label)
        
        splitter.addWidget(right_scroll)
        
        # 添加状态栏
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("就绪 - 使用 Ctrl+S 停止，Ctrl+Z 撤回，Ctrl+L 清除，F1 帮助")
        
        # 创建菜单栏
        self.create_menu_bar()
    
    def setup_shortcuts(self):
        """设置快捷键"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # Ctrl+S: 停止流式响应
        stop_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        stop_shortcut.activated.connect(self.stop_streaming)
        
        # Ctrl+Z: 撤回消息
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self.undo_last_message)
        
        # Ctrl+L: 清除聊天记录
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self.clear_chat_history)
        
        # F1: 显示帮助
        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.activated.connect(self.show_help)
    
    def create_menu_bar(self):
        """创建菜单栏"""
        from PyQt6.QtWidgets import QMenuBar
        from PyQt6.QtGui import QAction
        
        menubar = self.menuBar()
        
        # 在现有菜单中添加
        view_menu = menubar.addMenu('视图')
        
        clear_notifications_action = QAction('清除所有通知', self)
        clear_notifications_action.triggered.connect(self.notification_manager.clear_all)
        view_menu.addAction(clear_notifications_action)
    
    def show_help(self):
        """显示帮助信息"""
        help_text = """
快捷键说明：

聊天功能：
- Enter: 发送消息
- Shift+Enter: 换行
- Ctrl+S: 停止流式响应
- Ctrl+Z: 撤回消息
- Ctrl+L: 清除聊天记录
- F1: 显示此帮助

文件操作：
- 拖拽文件到输入框：快速输入文件路径
- 拖拽图片到图片项：快速设置图片路径

其他功能：
- 文件夹扫描：扫描并显示文件结构
- Word解析：解析Word文档内容
- 模板构建：创建替换规则
- 文档生成：批量生成文档
        """
        QMessageBox.information(self, '快捷键帮助', help_text.strip())
    
    def handle_drop(self, event):
        """处理拖拽放下事件"""
        if event.mimeData().hasText():
            file_path = event.mimeData().text()
            file_path = file_path.replace('file:///', '').replace('file://', '')
            file_path = os.path.normpath(file_path)
            if os.path.exists(file_path):
                self.url_edit.setText(file_path)
        event.accept()
    
    def handle_drag_enter(self, event):
        """处理拖拽进入事件"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def handle_image_drop(self, event, target_edit):
        """处理图片拖拽"""
        if event.mimeData().hasText():
            file_path = event.mimeData().text()
            file_path = file_path.replace('file:///', '').replace('file://', '')
            file_path = os.path.normpath(file_path)
            if os.path.exists(file_path):
                target_edit.setText(file_path)
        event.accept()
    
    def scan_and_select_folder(self):
        """扫描并选择文件夹"""
        folder_path = QFileDialog.getExistingDirectory(
            self, '选择要扫描的文件夹')
        
        if folder_path:
            self.folder_path_label.setText(folder_path)
            self.folder_path_label.setStyleSheet("color: #000000; font-weight: normal;")
            
            try:
                # 清空文件列表
                self.file_tree.clear()
                
                # 扫描文件夹
                folder_structure = scan_folder_simple(folder_path)
                
                # 递归添加文件到列表
                self.add_files_to_tree(folder_structure, folder_path)
                
                # 同时运行folder_scanner保存结果
                self.run_folder_scanner(folder_path)
                
                # 更新文件统计
                self.update_file_count()
                
                QMessageBox.information(self, '成功', f'文件夹扫描完成，发现 {self.file_tree.topLevelItemCount()} 个文件')
                
            except Exception as e:
                QMessageBox.critical(self, '错误', f'扫描文件夹时出错: {e}')
    
    def run_folder_scanner(self, folder_path):
        """运行folder_scanner保存结果"""
        try:
            # 创建输出文件夹
            output_folder = "folder_scan_results"
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
            
            # 扫描文件夹
            folder_structure = scan_folder_simple(folder_path)
            
            # 保存到JSON文件
            json_output_file = os.path.join(output_folder, "folder_structure.json")
            with open(json_output_file, 'w', encoding='utf-8') as f:
                json.dump(folder_structure, f, ensure_ascii=False, indent=2)
            
            # 生成文本格式的文件夹结构
            try:
                from folder_scanner import generate_text_structure
                text_structure = generate_text_structure(folder_path)
                
                # 保存到TXT文件
                txt_output_file = os.path.join(output_folder, "folder_structure.txt")
                with open(txt_output_file, 'w', encoding='utf-8') as f:
                    f.write(f"文件夹结构 - {folder_path}\n")
                    f.write("=" * 50 + "\n")
                    f.write(text_structure)
            except ImportError:
                print("generate_text_structure函数不可用")
            
            # 扫描图片文件并保存嵌套结构
            try:
                from folder_scanner import save_images_structure_to_json
                images_json_file = save_images_structure_to_json(folder_path, "images_structure.json")
                if images_json_file:
                    print(f"图片文件结构已保存: {images_json_file}")
            except ImportError:
                print("save_images_structure_to_json函数不可用")
                
        except Exception as e:
            print(f"运行folder_scanner时出错: {e}")
    
    def add_files_to_tree(self, folder_data, base_path, parent_item=None):
        """递归添加文件到树形列表"""
        if isinstance(folder_data, dict):
            for key, value in folder_data.items():
                if key == 'files':
                    # 添加文件
                    for file_name in value:
                        file_path = os.path.join(base_path, file_name)
                        item = QTreeWidgetItem(parent_item or self.file_tree)
                        item.setText(0, file_name)
                        item.setData(0, Qt.ItemDataRole.UserRole, file_path)
                        if parent_item:
                            parent_item.addChild(item)
                        else:
                            self.file_tree.addTopLevelItem(item)
                elif key != 'root_path':
                    # 创建文件夹节点
                    folder_item = QTreeWidgetItem(parent_item or self.file_tree)
                    folder_item.setText(0, key)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, None)  # 文件夹不能拖拽
                    if parent_item:
                        parent_item.addChild(folder_item)
                    else:
                        self.file_tree.addTopLevelItem(folder_item)
                    
                    # 递归处理子文件夹
                    sub_path = os.path.join(base_path, key)
                    self.add_files_to_tree(value, sub_path, folder_item)
    
    def filter_files(self):
        """筛选文件"""
        filter_type = self.filter_combo.currentText()
        custom_pattern = self.custom_filter_edit.text().strip()
        
        # 根据筛选条件显示/隐藏项目
        self.apply_filter_to_tree(self.file_tree.invisibleRootItem(), filter_type, custom_pattern)
        
        # 更新文件统计
        self.update_file_count()
    
    def apply_filter_to_tree(self, parent_item, filter_type, custom_pattern):
        """递归应用筛选到树形列表"""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            
            if item.childCount() > 0:
                # 这是文件夹，递归处理
                self.apply_filter_to_tree(item, filter_type, custom_pattern)
                # 如果文件夹有可见的子项，则显示文件夹
                has_visible_children = any(self.is_item_visible(item.child(j)) for j in range(item.childCount()))
                item.setHidden(not has_visible_children)
            else:
                # 这是文件，应用筛选
                file_path = item.data(0, Qt.ItemDataRole.UserRole)
                if file_path:
                    should_show = self.should_show_file(file_path, filter_type, custom_pattern)
                    item.setHidden(not should_show)
    
    def should_show_file(self, file_path, filter_type, custom_pattern):
        """判断文件是否应该显示"""
        file_name = os.path.basename(file_path).lower()
        
        if filter_type == '全部文件':
            return True
        elif filter_type == '图片文件':
            return any(file_name.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp'])
        elif filter_type == '文档文件':
            return any(file_name.endswith(ext) for ext in ['.doc', '.docx', '.pdf', '.txt'])
        elif filter_type == '文本文件':
            return any(file_name.endswith(ext) for ext in ['.txt', '.md', '.py', '.js', '.html'])
        elif filter_type == '自定义' and custom_pattern:
            import fnmatch
            patterns = [p.strip() for p in custom_pattern.split(',')]
            return any(fnmatch.fnmatch(file_name, pattern.lower()) for pattern in patterns)
        
        return True
    
    def is_item_visible(self, item):
        """检查项目是否可见"""
        if item.isHidden():
            return False
        if item.childCount() > 0:
            return any(self.is_item_visible(item.child(i)) for i in range(item.childCount()))
        return True
    
    def update_file_count(self):
        """更新文件数量统计"""
        visible_count = self.count_visible_files(self.file_tree.invisibleRootItem())
        self.file_count_label.setText(f'文件数量: {visible_count}')
    
    def count_visible_files(self, parent_item):
        """递归统计可见文件数量"""
        count = 0
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            if not item.isHidden():
                if item.childCount() > 0:
                    # 这是文件夹，递归统计
                    count += self.count_visible_files(item)
                else:
                    # 这是文件
                    count += 1
        return count
    
    def check_replace_rules(self):
        """检查替换规则并标记对应文件：绿色表示有规则，红色表示无规则"""
        try:
            # 检查replace.json文件是否存在
            replace_json_path = 'replace.json'
            if not os.path.exists(replace_json_path):
                self.notification_manager.show_notification(
                    "未找到规则文件", 
                    "replace.json 文件不存在，请先创建替换规则",
                    "warning"
                )
                return
            
            # 读取替换规则
            try:
                with open(replace_json_path, 'r', encoding='utf-8') as f:
                    replace_rules = json.load(f)
            except json.JSONDecodeError:
                self.notification_manager.show_notification(
                    "规则文件错误", 
                    "replace.json 文件格式不正确",
                    "error"
                )
                return
            except Exception as e:
                self.notification_manager.show_notification(
                    "读取错误", 
                    f"无法读取 replace.json: {str(e)}",
                    "error"
                )
                return
            
            # 获取规则中涉及的文件路径
            rule_files = set()
            
            # 处理不同格式的replace.json
            if isinstance(replace_rules, list):
                # 数组格式 - 处理每个对象
                for item in replace_rules:
                    if isinstance(item, dict):
                        for key, value in item.items():
                            self._extract_file_paths_from_value(value, rule_files)
            elif isinstance(replace_rules, dict):
                # 对象格式 - 直接处理键值对
                for key, value in replace_rules.items():
                    self._extract_file_paths_from_value(value, rule_files)
            
            if not rule_files:
                self.notification_manager.show_notification(
                    "无文件规则", 
                    "replace.json 中未找到有效的文件路径规则",
                    "info"
                )
                return
            
            # 重置所有文件的颜色
            self.reset_file_colors(self.file_tree.invisibleRootItem())
            
            # 标记文件并收集统计信息
            stats = {'green_count': 0, 'red_count': 0}
            red_items = []  # 存储红色标记的项目，用于展开
            
            self._mark_and_collect_files(self.file_tree.invisibleRootItem(), rule_files, stats, red_items)
            
            # 展开包含红色文件的文件夹
            self._expand_red_file_parents(red_items)
            
            # 显示结果通知
            green_count = stats['green_count']
            red_count = stats['red_count']
            total_files = green_count + red_count
            if total_files > 0:
                self.notification_manager.show_notification(
                    "✅ 检查完成", 
                    f"绿色: {green_count} 个文件有规则\n红色: {red_count} 个文件无规则\n已展开无规则文件所在位置",
                    "success" if red_count == 0 else "warning"
                )
            else:
                self.notification_manager.show_notification(
                    "⚠️ 无文件检查", 
                    "未找到任何文件进行检查",
                    "warning"
                )
                
        except Exception as e:
            self.notification_manager.show_notification(
                "检查出错", 
                f"检查替换规则时出错: {str(e)}",
                "error"
            )
    
    def reset_file_colors(self, parent_item):
        """重置文件树中所有项目的颜色"""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            
            # 重置颜色为默认
            item.setBackground(0, item.treeWidget().palette().base())
            item.setForeground(0, item.treeWidget().palette().text())
            
            if item.childCount() > 0:
                # 递归处理子项
                self.reset_file_colors(item)
    
    def _mark_and_collect_files(self, parent_item, rule_files, stats, red_items):
        """标记文件并收集统计信息"""
        from PyQt6.QtGui import QBrush, QColor
        
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            
            if item.childCount() > 0:
                # 这是文件夹，递归处理
                self._mark_and_collect_files(item, rule_files, stats, red_items)
            else:
                # 这是文件，检查是否在规则中
                file_path = item.data(0, Qt.ItemDataRole.UserRole)
                if file_path:
                    # 标准化路径用于比较
                    normalized_file_path = os.path.normpath(file_path)
                    
                    # 检查是否匹配规则中的任何文件
                    has_rule = False
                    for rule_file in rule_files:
                        if self._is_file_match(normalized_file_path, rule_file):
                            has_rule = True
                            break
                    
                    if has_rule:
                        # 设置绿色背景
                        green_brush = QBrush(QColor(220, 255, 220))  # 浅绿色背景
                        green_text = QBrush(QColor(0, 120, 0))       # 深绿色文字
                        
                        item.setBackground(0, green_brush)
                        item.setForeground(0, green_text)
                        stats['green_count'] += 1
                    else:
                        # 设置红色背景
                        red_brush = QBrush(QColor(255, 220, 220))    # 浅红色背景
                        red_text = QBrush(QColor(150, 0, 0))         # 深红色文字
                        
                        item.setBackground(0, red_brush)
                        item.setForeground(0, red_text)
                        stats['red_count'] += 1
                        red_items.append(item)
    
    def _expand_red_file_parents(self, red_items):
        """展开包含红色文件的所有父文件夹"""
        expanded_parents = set()
        
        for red_item in red_items:
            parent = red_item.parent()
            while parent is not None:
                if parent not in expanded_parents:
                    parent.setExpanded(True)
                    expanded_parents.add(parent)
                parent = parent.parent()
    
    def mark_files_in_tree(self, parent_item, rule_files):
        """在文件树中标记规则文件为绿色（保留兼容性）"""
        marked_count = 0
        
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            
            if item.childCount() > 0:
                # 这是文件夹，递归处理
                marked_count += self.mark_files_in_tree(item, rule_files)
            else:
                # 这是文件，检查是否在规则中
                file_path = item.data(0, Qt.ItemDataRole.UserRole)
                if file_path:
                    # 标准化路径用于比较
                    normalized_file_path = os.path.normpath(file_path)
                    
                    # 检查是否匹配规则中的任何文件
                    for rule_file in rule_files:
                        if self._is_file_match(normalized_file_path, rule_file):
                            # 设置绿色背景
                            from PyQt6.QtGui import QBrush, QColor
                            green_brush = QBrush(QColor(220, 255, 220))  # 浅绿色背景
                            green_text = QBrush(QColor(0, 120, 0))       # 深绿色文字
                            
                            item.setBackground(0, green_brush)
                            item.setForeground(0, green_text)
                            marked_count += 1
                            break
        
        return marked_count
    
    def _extract_file_paths_from_value(self, value, rule_files):
        """从值中提取文件路径"""
        if isinstance(value, str):
            # 检查是否是文件路径
            if os.path.exists(value) and os.path.isfile(value):
                # 转换为相对路径用于比较
                rule_files.add(os.path.normpath(value))
            # 检查是否是相对路径格式（包含路径分隔符）
            elif ('/' in value or '\\' in value) and not value.startswith('http'):
                normalized_path = os.path.normpath(value)
                if os.path.exists(normalized_path) and os.path.isfile(normalized_path):
                    rule_files.add(normalized_path)
                else:
                    # 即使文件不存在，也添加到规则中用于匹配
                    # 这样可以检查文件名匹配
                    rule_files.add(normalized_path)
    
    def _is_file_match(self, file_path, rule_file):
        """检查文件是否匹配规则"""
        # 精确匹配
        if file_path == rule_file:
            return True
        
        # 文件名匹配
        file_name = os.path.basename(file_path)
        rule_name = os.path.basename(rule_file)
        if file_name == rule_name:
            return True
        
        # 路径末尾匹配（考虑不同的路径分隔符）
        file_parts = file_path.replace('\\', '/').split('/')
        rule_parts = rule_file.replace('\\', '/').split('/')
        
        # 检查rule_file是否是file_path的后缀
        if len(rule_parts) <= len(file_parts):
            if file_parts[-len(rule_parts):] == rule_parts:
                return True
        
        # 检查file_path是否是rule_file的后缀
        if len(file_parts) <= len(rule_parts):
            if rule_parts[-len(file_parts):] == file_parts:
                return True
        
        return False
    
    def change_font_size(self):
        """改变字体大小"""
        font_size = self.font_size_spin.value()
        current_font = self.chat_display.font()
        current_font.setPointSize(font_size)
        self.chat_display.setFont(current_font)
    
    def clear_chat_history(self):
        """清除聊天记录"""
        reply = QMessageBox.question(
            self, '确认清除', 
            '确定要清除所有聊天记录吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            self.chat_messages.clear()
            QMessageBox.information(self, '成功', '聊天记录已清除')
    
    def generate_document(self):
        """生成文档"""
        try:
            # 检查Word文件是否已选择
            if not self.selected_word_file:
                QMessageBox.warning(self, '警告', '请先选择一个Word文档作为模板')
                return
            # 检查Word文件是否存在
            if not os.path.exists(self.selected_word_file):
                QMessageBox.critical(self, '错误', '选择的Word文件不存在')
                return
            # 检查必要的文件是否存在
            required_files = []
            missing_files = []
            # 检查JSON数据文件
            json_file = os.path.normpath('replace.json')
            if os.path.exists(json_file):
                required_files.append(json_file)
            else:
                missing_files.append('replace.json 文件缺失')
            # 检查是否有替换规则
            if not self.text_items and not self.image_items:
                missing_files.append('替换规则 (需要在模板构建中添加文字或图片项)')
            if missing_files:
                error_msg = "缺少以下必要文件或配置：\n\n" + "\n".join(missing_files)
                QMessageBox.critical(self, '错误', error_msg)
                return
            # 更新状态
            self.generate_status_label.setText('正在生成文档...')
            self.generate_status_label.setStyleSheet("""
                font-size: 12px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #2196f3;
                border-radius: 5px;
                background-color: #e3f2fd;
                color: #1976d2;
            """)
            self.generate_btn.setEnabled(False)
            # 创建替换规则文件
            rules_file = os.path.normpath('replace.txt')
            # 导入replace模块并执行
            from replace import create_dynamic_document
            # 执行文档生成
            template_file = os.path.normpath(self.selected_word_file)
            output_path = create_dynamic_document(
                template_file,  # 模板文件
                json_file,      # JSON数据文件
                rules_file      # 替换规则文件
            )
            # 更新状态为成功
            self.generate_status_label.setText('文档生成成功！')
            self.generate_status_label.setStyleSheet("""
                font-size: 12px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #4caf50;
                border-radius: 5px;
                background-color: #e8f5e8;
                color: #2e7d32;
            """)
            # 显示成功消息
            QMessageBox.information(
                self, '成功', 
                f'文档生成成功！\n\n输出文件：{output_path}'
            )
        except Exception as e:
            # 更新状态为错误
            self.generate_status_label.setText('生成失败')
            self.generate_status_label.setStyleSheet("""
                font-size: 12px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #f44336;
                border-radius: 5px;
                background-color: #ffebee;
                color: #c62828;
            """)
            QMessageBox.critical(self, '错误', f'生成文档时出错：\n{str(e)}')
        finally:
            # 恢复按钮状态
            self.generate_btn.setEnabled(True)
    
    def send_message(self):
        """发送消息"""
        from agent_core import load_config, get_current_api_key, rotate_api_key, move_api_to_rubbish
        agent_config = load_config()    
        rotate_api_key(agent_config)
        message = self.chat_input.toPlainText().strip()
        if not message:
            return
        
        # 清空输入框
        self.chat_input.clear()
        
        # 显示用户消息
        timestamp = time.strftime("%H:%M:%S")
        user_msg = f"用户 ({timestamp}): {message}\n"
        self.chat_display.append(user_msg)
        
        # 添加到消息历史
        self.chat_messages.append({
            "role": "user",
            "content": message
        })
        
        # 禁用发送按钮，防止重复发送
        self.send_btn.setEnabled(False)
        self.send_btn.setText('发送中...')
        
        # 在后台线程中调用AI API
        try:
            # 使用agent_core的配置和API轮换功能
            config = load_config()
            system_prompt = build_system_prompt()
            
            # 开始流式显示
            self.start_streaming_response(self.chat_messages, config, system_prompt)
            
        except Exception as e:
            error_msg = f"发送消息失败: {e}"
            self.add_chat_message("系统", error_msg)
            self.send_btn.setEnabled(True)
            self.send_btn.setText('发送')
    
    def start_streaming_response(self, messages, config, system_prompt):
        """开始流式响应"""
        # 添加AI消息占位符
        timestamp = time.strftime("%H:%M:%S")
        
        # 创建AI消息显示
        formatted_msg = f"AI ({timestamp}): "
        self.chat_display.append(formatted_msg)
        
        # 滚动到底部
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # 创建工作线程处理API调用
        self.streaming_worker = StreamingWorker(messages, config, system_prompt)
        self.streaming_worker.response_received.connect(self.handle_streaming_response)
        self.streaming_worker.error_occurred.connect(self.handle_streaming_error)
        self.streaming_worker.chunk_received.connect(self.handle_streaming_chunk)
        self.streaming_worker.stopped.connect(self.handle_streaming_stopped)
        
        # 新增：连接通知信号
        self.streaming_worker.file_created.connect(self.handle_file_created)
        self.streaming_worker.python_executed.connect(self.handle_python_executed)
        self.streaming_worker.python_execution_feedback.connect(self.handle_python_execution_feedback)
        
        self.streaming_worker.start()
        
        # 初始化流式内容
        self.streaming_content = ""
        
        # 启用停止按钮，禁用发送按钮
        self.stop_btn.setEnabled(True)
        self.send_btn.setEnabled(False)
        
        # 更新状态栏
        self.statusBar.showMessage("正在发送消息... 使用 Ctrl+S 停止")
    
    def handle_streaming_response(self, reply):
        """处理流式响应结果"""
        # 强制刷新缓冲区，确保所有内容都被渲染
        self.chat_display.flush_buffer()
        
        # 添加换行符
        self.chat_display.append("\n")
        
        # 处理function call
        handle_function_call(reply)
        
        # 添加到消息历史
        self.chat_messages.append({
            "role": "assistant",
            "content": reply
        })
        
        # 恢复发送按钮
        self.send_btn.setEnabled(True)
        self.send_btn.setText('发送')
        self.stop_btn.setEnabled(False)
        
        # 更新状态栏
        self.statusBar.showMessage("就绪 - 使用 Ctrl+S 停止，Ctrl+Z 撤回，Ctrl+L 清除，F1 帮助")
    
    def handle_streaming_chunk(self, chunk):
        """处理流式响应的每个chunk"""
        self.streaming_content += chunk
        # 使用Markdown流式渲染
        self.chat_display.append_markdown_chunk(chunk)
    
    def handle_streaming_error(self, error_msg):
        """处理流式响应错误"""
        # 强制刷新缓冲区
        self.chat_display.flush_buffer()
        
        error_text = f"\n[错误] 流式响应失败: {error_msg}\n"
        self.chat_display.append(error_text)
        self.send_btn.setEnabled(True)
        self.send_btn.setText('发送')
        self.stop_btn.setEnabled(False)
        
        # 更新状态栏
        self.statusBar.showMessage("错误 - 使用 Ctrl+S 停止，Ctrl+Z 撤回，Ctrl+L 清除，F1 帮助")
    
    def handle_streaming_stopped(self):
        """处理流式响应被停止"""
        self.chat_display.append("\n[提示] 流式响应已停止。\n")
        self.send_btn.setEnabled(True)
        self.send_btn.setText('发送')
        self.stop_btn.setEnabled(False)
        
        # 更新状态栏
        self.statusBar.showMessage("已停止 - 使用 Ctrl+S 停止，Ctrl+Z 撤回，Ctrl+L 清除，F1 帮助")
    
    def stop_streaming(self):
        """停止流式响应"""
        if self.streaming_worker and self.streaming_worker.isRunning():
            self.streaming_worker.stop()
            if not self.streaming_worker.wait(2000):  # 等待2秒
                self.streaming_worker.terminate()  # 强制终止
                self.streaming_worker.wait()
            self.chat_display.append("\n[提示] 正在停止响应...\n")
            self.statusBar.showMessage("正在停止...")
    
    def undo_last_message(self):
        """撤回最后一条消息"""
        if not self.chat_messages:
            QMessageBox.information(self, '提示', '没有消息可以撤回')
            return
        
        # 创建选择对话框
        from PyQt6.QtWidgets import QInputDialog
        
        count, ok = QInputDialog.getInt(
            self, '撤回消息', 
            f'当前有 {len(self.chat_messages)} 条消息，要撤回几条？\n(输入1-{len(self.chat_messages)}的数字)',
            value=1, min=1, max=len(self.chat_messages)
        )
        
        if ok and count > 0:
            reply = QMessageBox.question(
                self, '确认撤回', 
                f'确定要撤回最后 {count} 条消息吗？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # 移除指定数量的消息
                removed_messages = []
                for _ in range(count):
                    if self.chat_messages:
                        removed_messages.append(self.chat_messages.pop())
                
                # 重新显示所有消息
                self.redisplay_all_messages()
                
                # 显示撤回结果
                if len(removed_messages) == 1:
                    QMessageBox.information(self, '成功', f'已撤回消息：{removed_messages[0]["content"][:50]}...')
                else:
                    QMessageBox.information(self, '成功', f'已撤回 {len(removed_messages)} 条消息')
    
    def redisplay_all_messages(self):
        """重新显示所有消息"""
        self.chat_display.clear()
        
        for msg in self.chat_messages:
            role = msg["role"]
            content = msg["content"]
            sender = "用户" if role == "user" else "AI"
            
            timestamp = time.strftime("%H:%M:%S")
            formatted_msg = f"{sender} ({timestamp}): {content}\n"
            self.chat_display.append(formatted_msg)
    
    def add_chat_message(self, sender, content):
        """添加聊天消息"""
        timestamp = time.strftime("%H:%M:%S")
        
        # 添加到消息历史
        self.chat_messages.append({
            "role": "user" if sender == "用户" else "assistant",
            "content": content
        })
        
        # 简单的文本显示
        formatted_msg = f"{sender} ({timestamp}): {content}\n"
        self.chat_display.append(formatted_msg)
        
        # 滚动到底部
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def add_text_item(self, default_text=""):
        """添加文字替换项，分配唯一占位符"""
        item_widget = QWidget()
        item_layout = QHBoxLayout()
        item_widget.setLayout(item_layout)
        
        # 标签直接用原文内容
        label = QLabel(default_text or "内容：")
        item_layout.addWidget(label)
        
        # 输入框
        text_edit = QLineEdit()
        text_edit.setPlaceholderText("请输入替换内容")
        if default_text:
            text_edit.setText(default_text)
        item_layout.addWidget(text_edit)
        
        # 删除按钮
        delete_btn = QPushButton('×')
        delete_btn.setMaximumWidth(30)
        delete_btn.clicked.connect(lambda: self.remove_replace_item(item_widget))
        item_layout.addWidget(delete_btn)
        
        # 分配唯一占位符
        placeholder = f"text{len(self.text_items) + 1}"
        self.replace_layout.addWidget(item_widget)
        self.text_items.append((label, text_edit, item_widget, default_text, placeholder))
    
    def add_image_item(self, default_path=""):
        """添加图片替换项，分配唯一占位符"""
        item_widget = QWidget()
        item_layout = QHBoxLayout()
        item_widget.setLayout(item_layout)
        
        # 标签
        label = QLabel(f"图{len(self.image_items) + 1}:")
        item_layout.addWidget(label)
        
        # 路径输入框
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("拖拽图片文件到此处")
        path_edit.setAcceptDrops(True)
        path_edit.dropEvent = lambda e: self.handle_image_drop(e, path_edit)
        path_edit.dragEnterEvent = self.handle_drag_enter
        if default_path:
            default_path = os.path.normpath(default_path)
            path_edit.setText(default_path)
        item_layout.addWidget(path_edit)
        
        # 删除按钮
        delete_btn = QPushButton('×')
        delete_btn.setMaximumWidth(30)
        delete_btn.clicked.connect(lambda: self.remove_replace_item(item_widget))
        item_layout.addWidget(delete_btn)
        
        # 分配唯一占位符
        placeholder = f"path{len(self.image_items) + 1}"
        self.replace_layout.addWidget(item_widget)
        self.image_items.append((label, path_edit, item_widget, placeholder))
    
    def remove_replace_item(self, item_widget):
        """删除替换项"""
        # 从列表中移除
        self.text_items = [(l, e, w, o, p) for l, e, w, o, p in self.text_items if w != item_widget]
        self.image_items = [(l, e, w, p) for l, e, w, p in self.image_items if w != item_widget]
        
        # 删除控件
        item_widget.setParent(None)
        item_widget.deleteLater()
        
        # 重新编号
        self.renumber_items()
    
    def renumber_items(self):
        """重新编号替换项（仅图片项，文字项不再编号）"""
        # 文字项标签不再编号，保持原文
        for i, (label, _, _, original_text, placeholder) in enumerate(self.text_items, 1):
            pass  # 不做任何操作
        for i, (label, _, _, placeholder) in enumerate(self.image_items, 1):
            label.setText(f"图{i}:")
            # 重新分配图片占位符
            self.image_items[i-1] = (label, self.image_items[i-1][1], self.image_items[i-1][2], f"path{i}")
    
    def export_template_to_chat(self):
        """导出模板到对话框，生成规则和json映射"""
        rules = []
        json_dict = {}
        # 文字项：等号前为原文，等号后为text1、text2...，只导出内容不同且不为空
        for label, text_edit, _, original_text, placeholder in self.text_items:
            template_text = original_text or label.text()
            user_input = text_edit.text().strip()
            if user_input and user_input != template_text:
                rules.append(f"{template_text}={placeholder}")
                json_dict[placeholder] = user_input
        # 图片项：等号前为图1、图2，等号后为path1、path2...，只导出内容不同且不为空
        for i, (label, path_edit, _, placeholder) in enumerate(self.image_items, 1):
            template_label = f"图{i}"
            user_input = path_edit.text().strip()
            if user_input:
                rules.append(f"{template_label}={placeholder}")
                json_dict[placeholder] = user_input
        # 生成规则文本和json文本
        rule_text = "\n".join(rules)
        json_text = json.dumps([json_dict], ensure_ascii=False)
        # 输出到输入框
        output = f"{rule_text}\n\n{json_text}"
        self.chat_input.setPlainText(output)
    
    def populate_template_from_scan(self):
        """从扫描结果填充模板"""
        try:
            # 读取扫描结果
            with open('word_extracted_data/word_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 清空现有项
            for item in self.text_items + self.image_items:
                if len(item) >= 3:  # 确保有足够的元素
                    item[2].setParent(None)
                    item[2].deleteLater()
            self.text_items.clear()
            self.image_items.clear()
            
            # 添加文字项
            unique_texts = data.get('unique_content', {}).get('unique_texts', [])
            for i, text_item in enumerate(unique_texts, 1):
                self.add_text_item(text_item.get('text', ''))
            
            # 添加图片项
            images = data.get('images', [])
            for i, image_info in enumerate(images, 1):
                self.add_image_item(image_info.get('saved_name', ''))
                
        except Exception as e:
            print(f"填充模板时出错: {e}")
    
    def load_config(self):
        """加载配置文件"""
        try:
            with open('agent_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            self.url_edit.setText(config.get('base_url', ''))
            
            # 兼容新旧配置格式
            if 'api_pool' in config and config['api_pool']:
                # 新格式：使用API池
                self.key_edit.setText(config['api_pool'][0])  # 显示第一个API key
            elif 'api_key' in config:
                # 旧格式：单个API key
                self.key_edit.setText(config.get('api_key', ''))
            else:
                self.key_edit.setText('')
                
            self.model_edit.setText(config.get('model', ''))
            self.temp_spin.setValue(config.get('temperature', 0.7))
            self.tokens_spin.setValue(config.get('max_tokens', 2000))
            
            # 显示API池信息
            api_count = len(config.get('api_pool', []))
            current_pos = config.get('current_position', 0)
            if api_count > 0:
                status_text = f'配置已加载 - API池: {api_count}个, 当前位置: {current_pos + 1}'
                pool_status = f'{api_count}个API, 当前使用第{current_pos + 1}个'
            else:
                status_text = '配置已加载'
                pool_status = '未配置API池'
                
            self.status_label.setText(status_text)
            self.pool_status_label.setText(pool_status)
            self.status_label.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #cccccc;
                border-radius: 5px;
                background-color: #f8f8f8;
                color: #000000;
            """)
            
        except FileNotFoundError:
            self.status_label.setText('未找到配置文件，请填写参数后测试')
        except Exception as e:
            self.status_label.setText(f'加载配置失败: {e}')
    
    def test_api(self, config, max_retries=3):
        """测试API连接"""
        try:
            client = OpenAI(
                api_key=config['api_pool'][0] if config.get('api_pool') else config.get('api_key'),
                base_url=config.get('base_url', 'https://api.openai.com/v1')
            )
            
            # 简单测试
            response = client.chat.completions.create(
                model=config['model'],
                messages=[{"role": "user", "content": "你好"}],
                max_tokens=50
            )
            
            return True, response.choices[0].message.content
            
        except Exception as e:
            return False, str(e)
    
    def test_and_save(self):
        """测试连接并保存配置"""
        url = self.url_edit.text().strip()
        key = self.key_edit.text().strip()
        model = self.model_edit.text().strip()
        
        if not url or not key or not model:
            self.status_label.setText('请填写完整的URL、API Key和Model')
            self.status_label.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #ff0000;
                border-radius: 5px;
                background-color: #ffe6e6;
                color: #ff0000;
            """)
            return
        
        # 使用agent_core的配置格式
        config = {
            'base_url': url,
            'api_pool': [key],  # 使用API池格式
            'current_position': 0,
            'model': model,
            'temperature': self.temp_spin.value(),
            'max_tokens': self.tokens_spin.value()
        }
        
        self.status_label.setText('正在测试连接...')
        self.status_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            padding: 10px;
            border: 2px solid #0000ff;
            border-radius: 5px;
            background-color: #e6f3ff;
            color: #0000ff;
        """)
        
        success, result = self.test_api(config)
        
        if success:
            try:
                with open('agent_config.json', 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                self.status_label.setText(f'✅ API有效，配置已保存\n回复: {result[:100]}...')
                self.status_label.setStyleSheet("""
                    font-size: 14px;
                    font-weight: bold;
                    padding: 10px;
                    border: 2px solid #00ff00;
                    border-radius: 5px;
                    background-color: #e6ffe6;
                    color: #008000;
                """)
            except Exception as e:
                self.status_label.setText(f'✅ API有效，但保存失败: {e}')
                self.status_label.setStyleSheet("""
                    font-size: 14px;
                    font-weight: bold;
                    padding: 10px;
                    border: 2px solid #ff0000;
                    border-radius: 5px;
                    background-color: #ffe6e6;
                    color: #ff0000;
                """)
        else:
            self.status_label.setText(f'❌ API测试失败: {result}')
            self.status_label.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border: 2px solid #ff0000;
                border-radius: 5px;
                background-color: #ffe6e6;
                color: #ff0000;
            """)
    
    def browse_file(self):
        """浏览选择Word文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择Word文档', '', 'Word文档 (*.docx *.doc)')
        if file_path:
            file_path = os.path.normpath(file_path)
            self.file_path_label.setText(file_path)
            self.file_path_label.setStyleSheet("color: #000000; font-weight: normal;")
            self.selected_word_file = file_path  # 保存选中的文件路径
            # 自动扫描
            self.scan_word_document(file_path)
    
    def scan_word_document(self, file_path):
        """扫描Word文档"""
        if not os.path.exists(file_path):
            QMessageBox.critical(self, '错误', '选择的文件不存在')
            return
        
        try:
            # 创建扫描器并扫描文档
            scanner = AdvancedWordScanner()
            result = scanner.scan_word_document(file_path)
            
            if result:
                self.display_scan_results()
                # 填充模板
                self.populate_template_from_scan()
            else:
                QMessageBox.critical(self, '错误', 'Word文档扫描失败')
                
        except Exception as e:
            QMessageBox.critical(self, '错误', f'扫描过程中出错: {e}')
    
    def display_scan_results(self):
        """显示扫描结果"""
        try:
            # 清除现有文字内容
            for i in reversed(range(self.text_layout.count())):
                child = self.text_layout.itemAt(i)
                if child:
                    widget = child.widget()
                    if widget:
                        widget.setParent(None)
            
            # 清除现有图片内容
            for i in reversed(range(self.image_layout.count())):
                child = self.image_layout.itemAt(i)
                if child:
                    widget = child.widget()
                    if widget:
                        widget.setParent(None)
            
            # 读取扫描结果
            with open('word_extracted_data/word_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 显示文字内容 - 直接换行显示
            unique_texts = data.get('unique_content', {}).get('unique_texts', [])
            if unique_texts:
                for i, text_item in enumerate(unique_texts, 1):
                    text_label = QLabel(f"{i}. {text_item.get('text', '')}")
                    text_label.setWordWrap(True)
                    text_label.setStyleSheet("""
                        font-weight: normal;
                        padding: 5px;
                        border-bottom: 1px solid #eeeeee;
                    """)
                    self.text_layout.addWidget(text_label)
            else:
                no_text_label = QLabel('未发现文字内容')
                no_text_label.setStyleSheet("color: #666666; font-weight: normal;")
                self.text_layout.addWidget(no_text_label)
            
            # 显示图片内容 - 自适应网格布局
            images = data.get('images', [])
            if images:
                # 创建图片网格容器
                grid_widget = QWidget()
                grid_layout = QGridLayout()
                grid_widget.setLayout(grid_layout)
                self.image_layout.addWidget(grid_widget)
                
                # 计算每行图片数量（3张）
                cols = 3
                
                for i, image_info in enumerate(images):
                    row = i // cols
                    col = i % cols
                    
                    # 创建图片容器
                    image_container = QWidget()
                    container_layout = QVBoxLayout()
                    image_container.setLayout(container_layout)
                    
                    # 图片显示 - 自适应比例
                    image_label = QLabel()
                    image_label.setStyleSheet("""
                        border: 1px solid #cccccc;
                        background-color: #f8f8f8;
                    """)
                    
                    # 加载图片
                    image_path = image_info.get('file_path', '')
                    if os.path.exists(image_path):
                        pixmap = QPixmap(image_path)
                        if not pixmap.isNull():
                            # 获取图片原始尺寸
                            original_width = pixmap.width()
                            original_height = pixmap.height()
                            
                            # 计算合适的显示尺寸（保持比例）
                            max_width = 250  # 最大宽度
                            max_height = 200  # 最大高度
                            
                            # 计算缩放比例
                            width_ratio = max_width / original_width
                            height_ratio = max_height / original_height
                            scale_ratio = min(width_ratio, height_ratio)
                            
                            # 计算新的尺寸
                            new_width = int(original_width * scale_ratio)
                            new_height = int(original_height * scale_ratio)
                            
                            # 缩放图片
                            scaled_pixmap = pixmap.scaled(
                                new_width, new_height,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation
                            )
                            
                            # 设置图片标签大小适应图片
                            image_label.setPixmap(scaled_pixmap)
                            image_label.setFixedSize(new_width, new_height)
                            
                        else:
                            image_label.setText('❌')
                            image_label.setFixedSize(100, 100)
                    else:
                        image_label.setText('❌')
                        image_label.setFixedSize(100, 100)
                    
                    container_layout.addWidget(image_label)
                    
                    # 文件名 - 换行显示并添加position信息
                    original_name = image_info.get('original_name', '')
                    # 从original_name中提取数字
                    number_match = re.search(r'\d+', original_name)
                    if number_match:
                        number = int(number_match.group()) - 1  # 数字减1
                        position_text = f"图{number:04d}"  # 格式化为4位数字，如"图0000"
                    else:
                        position_text = "图0000"  # 默认值

                    filename_label = QLabel(f"{image_info.get('saved_name', '')} ({position_text})")
                    filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    filename_label.setWordWrap(True)  # 启用文字换行
                    filename_label.setStyleSheet("""
                        font-size: 10px;
                        color: #666666;
                        font-weight: normal;
                        padding: 2px;
                    """)
                    container_layout.addWidget(filename_label)
                    
                    grid_layout.addWidget(image_container, row, col)
            else:
                no_image_label = QLabel('未发现图片内容')
                no_image_label.setStyleSheet("color: #666666; font-weight: normal;")
                self.image_layout.addWidget(no_image_label)
            
        except FileNotFoundError:
            error_label = QLabel('未找到扫描结果文件')
            error_label.setStyleSheet("color: #ff0000; font-weight: normal;")
            self.text_layout.addWidget(error_label)
        except Exception as e:
            error_label = QLabel(f'显示结果时出错: {e}')
            error_label.setStyleSheet("color: #ff0000; font-weight: normal;")
            self.text_layout.addWidget(error_label)
    
    def add_api_to_pool(self):
        """添加API到池中"""
        new_api_key = self.key_edit.text().strip()
        if not new_api_key:
            QMessageBox.warning(self, '警告', '请先输入API Key')
            return
        
        try:
            # 读取当前配置
            with open('agent_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 确保api_pool存在
            if 'api_pool' not in config:
                config['api_pool'] = []
            
            # 检查是否已存在
            if new_api_key in config['api_pool']:
                QMessageBox.information(self, '提示', '该API Key已存在于池中')
                return
            
            # 添加到池中
            config['api_pool'].append(new_api_key)
            
            # 保存配置
            with open('agent_config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            # 更新显示
            self.load_config()
            
            QMessageBox.information(self, '成功', f'API Key已添加到池中，当前池中有{len(config["api_pool"])}个API')
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'添加API到池时出错: {e}')
    
    def handle_file_created(self, file_type, filename):
        """处理文件创建通知"""
        title = f"{file_type}已创建"
        content = f"文件: {os.path.basename(filename)}"
        
        # 根据文件类型选择通知类型
        if "Python" in file_type:
            notification_type = "code"
        elif "JSON" in file_type:
            notification_type = "file"
        else:
            notification_type = "file"
        
        self.notification_manager.show_notification(
            title, content, notification_type, duration=2500
        )
    
    def handle_python_executed(self, filename, success, result):
        """处理Python执行通知"""
        if success:
            title = "Python执行成功"
            content = f"文件: {os.path.basename(filename)}"
            notification_type = "success"
            
            # 如果有输出，显示简短预览
            if result and result.strip() and result.strip() != "执行完成":
                preview = result.strip()[:50]
                if len(result.strip()) > 50:
                    preview += "..."
                content += f"\n输出: {preview}"
        else:
            title = "Python执行失败"
            content = f"文件: {os.path.basename(filename)}"
            notification_type = "error"
            
            # 显示错误信息预览
            if result:
                error_preview = result.strip()[:50]
                if len(result.strip()) > 50:
                    error_preview += "..."
                content += f"\n错误: {error_preview}"
        
        self.notification_manager.show_notification(
            title, content, notification_type, duration=4000
        )
    
    def handle_python_execution_feedback(self, filename, success, stdout, stderr):
        """处理Python执行反馈，自动发送给AI分析"""
        try:
            # 构建反馈消息
            feedback_message = "🔧 **Python代码执行结果**\n\n"
            feedback_message += f"**文件**: {filename}\n"
            feedback_message += f"**状态**: {'✅ 执行成功' if success else '❌ 执行失败'}\n\n"
            
            if stdout and stdout.strip():
                feedback_message += f"**标准输出**:\n```\n{stdout.strip()}\n```\n\n"
            
            if stderr and stderr.strip():
                feedback_message += f"**错误输出**:\n```\n{stderr.strip()}\n```\n\n"
            
            if not stdout.strip() and not stderr.strip():
                feedback_message += "**输出**: 无输出内容\n\n"
            
            feedback_message += "请分析执行结果：\n"
            feedback_message += "1. 执行是否成功，结果是否符合预期\n"
            feedback_message += "2. 如有错误，请提供解决方案\n"
            feedback_message += "3. 基于结果的下一步建议\n"
            feedback_message += "4. 如果生成了文件，请说明文件用途和内容概要"
            
            # 在聊天界面显示执行结果
            timestamp = time.strftime("%H:%M:%S")
            result_display = f"\n📋 **执行结果反馈** ({timestamp})\n"
            result_display += f"文件: {filename} | 状态: {'成功' if success else '失败'}\n"
            
            if stdout and stdout.strip():
                preview = stdout.strip()[:100]
                if len(stdout.strip()) > 100:
                    preview += "..."
                result_display += f"输出: {preview}\n"
            
            if stderr and stderr.strip():
                error_preview = stderr.strip()[:100]
                if len(stderr.strip()) > 100:
                    error_preview += "..."
                result_display += f"错误: {error_preview}\n"
            
            self.chat_display.append(result_display)
            
            # 自动添加反馈消息到对话历史
            self.chat_messages.append({
                "role": "user",
                "content": feedback_message
            })
            
            # 显示用户反馈消息
            user_feedback_display = f"\n用户 ({timestamp}): [自动]Python执行结果反馈\n"
            self.chat_display.append(user_feedback_display)
            
            # 自动触发AI分析（延迟1秒）
            QTimer.singleShot(1000, self.trigger_ai_analysis_for_execution)
            
        except Exception as e:
            print(f"处理Python执行反馈时出错: {e}")
    
    def trigger_ai_analysis_for_execution(self):
        """触发AI分析Python执行结果"""
        try:
            from agent_core import load_config, build_system_prompt
            
            # 加载配置
            config = load_config()
            system_prompt = build_system_prompt()
            
            # 开始AI分析
            self.start_streaming_response(self.chat_messages, config, system_prompt)
            
        except Exception as e:
            error_msg = f"触发AI分析失败: {e}"
            self.add_chat_message("系统", error_msg)

def main():
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    window = APIConfigApp()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()