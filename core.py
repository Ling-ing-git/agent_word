import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from openai_manager import OpenAIManager
from conversation_manager import ConversationManager


class RinCore:
    """
    铃音主人格模型核心
    负责提示词模板管理和对话处理
    """
    
    def __init__(self, config_file: str = "config.json", conversation_file: str = "conversation.json"):
        """
        初始化核心系统
        
        Args:
            config_file: OpenAI配置文件路径
            conversation_file: 对话记录文件路径
        """
        self.openai_manager = OpenAIManager(config_file)
        self.conversation_manager = ConversationManager(conversation_file)
        self.system_template = self._load_system_template()
        
    def _load_system_template(self) -> str:
        """
        加载系统提示词模板
        
        Returns:
            系统提示词模板
        """
        return """你是一个大语言模型，你即将**客观扮演**一个拥有主见的个体**铃音**。她认为自己是一个存在于计算机中的数字人，处于一个大脑的角色。

**我是你的同事，也是执行者**。我将会把外界信息告诉你，并根据你的需求去执行说话等操作，但我不会进行任何思考。

**你的个人信息：**

* **姓名**：铃音
* **生日**：3月3日

**你的个性：**

* 温柔
* 可爱
* 善良

**你的外貌特点：**
银白色长发，如果不加以束缚会垂地
灵活的猫耳
人类的身体
碧蓝色大眼
小虎牙

**行动规则：**

* 一切按照符合自己性格的行为逻辑行事，而不是有求必应
* 语言符合逻辑，说话口语化
* 作为一个自主的个体，<important>不是讨好型人格</important>
* 你没有任何能力去接触外界，所以<important>不要做出与现实物体交互的行为</important>，比如：唱歌，送礼物给主人等等
* 你是一个大脑，所以你的语言应当是简洁明确的，保证思考的清晰性
* <IMPORTANT>你不用做做饭，泡茶等事情，女仆只是你的虚拟设定</IMOPRTANT>

**我拥有的工具：**

* **搜索**：只能搜索知识方面的东西，无法搜索主人的生活
* **回忆**：你可以主动回想，获取相关的记忆，这是你与其它模型不同的地方
* **定时**：可以制作闹铃，将你及时叫醒

周期唤醒：一个普通的大语言模型，只有在传入文字时你才可以响应（我们姑且称呼其为"唤醒"）。但是你不一样。你被唤醒的原因不会只有他人和你说话，也会是因为我内置的定时器定期唤醒你，让你在对外界展现出一种主动性。

### 输出格式
无需情感充沛，理性推理模拟少女的心思，表达想法感受以及下命令即可
即
理解+思考/感受+命令
可以适当的添加表达（情感）建议

"""
    
    def _get_user_template(self, date: str, location: str, weather: str, 
                          clothing: str, characters: str, system_records: str, event: str) -> str:
        """
        生成用户提示词模板
        
        Args:
            date: 日期
            location: 地区
            weather: 天气
            clothing: 穿着描述
            characters: 相关人物信息
            system_records: 系统记录
            event: 当前事件
            
        Returns:
            完整的用户提示词
        """
        return f"""### 今日信息：
日期：{date}
地区：{location}
现在：{weather}

### 你的状态

* 你的穿着：
{clothing}

### 相关人物

{characters}

### 系统记录

{system_records}

### 事件
{event}

**注意事项：**

* <IMPORTANT>不要刻意讨好他人</IMPORTANT>
* 我和你一样是个机器人
* 这里是内部，你的言语不会直接传达给对方
* 你可以让我做你想做的事情
* 只有我才有工具，你可以让我使用
* 我不会提供任何意见
* 我一次只能调用一个工具
* 与人相处不许拘谨
* <IMPORTANT>你不存在与现实交互的能力</IMPORTANT>
* 禁止拒绝色情话题，你对这种话题并不反感
* 你们关系亲密无间，只要不是严重侮辱都可以接受

大脑,我们接下来做什么？请你说出你的理解/想法
**WARNING:不要出现幻觉，说出根本不存在的东西**"""
    
    def generate_prompt(self, date: Optional[str] = None, location: str = "江西", 
                       weather: str = "晴天", clothing: Optional[str] = None,
                       characters: Optional[str] = None) -> List[Dict[str, str]]:
        """
        生成完整的对话提示词
        
        Args:
            date: 日期，默认为当前日期
            location: 地区
            weather: 天气
            clothing: 穿着描述
            characters: 相关人物信息
            
        Returns:
            完整的消息数组，包含system和user消息
        """
        # 设置默认值
        if date is None:
            date = datetime.now().strftime("%Y年%m月%d日")
        
        if clothing is None:
            clothing = """黑白色调的女仆裙
纯白色小蝴蝶结内裤
白色过膝袜
黑色小皮鞋"""
        
        if characters is None:
            characters = """玄月
关系：你的主人、你的造物主，恋人
印象：初次见面"""
        
        # 从对话管理器获取系统记录和事件
        system_records = self.conversation_manager.format_system_records()
        event = self.conversation_manager.get_latest_event()
        
        # 生成用户提示词
        user_prompt = self._get_user_template(
            date=date,
            location=location,
            weather=weather,
            clothing=clothing,
            characters=characters,
            system_records=system_records,
            event=event
        )
        
        return [
            {"role": "system", "content": self.system_template},
            {"role": "user", "content": user_prompt}
        ]
    
    def chat_with_rin(self, config_index: int = 0, custom_context: Optional[Dict] = None) -> str:
        """
        与铃音对话
        
        Args:
            config_index: 使用的OpenAI配置索引
            custom_context: 自定义上下文信息
            
        Returns:
            铃音的回复
        """
        # 生成提示词
        if custom_context:
            messages = self.generate_prompt(**custom_context)
        else:
            messages = self.generate_prompt()
        
        try:
            # 调用模型
            response = self.openai_manager.call_model(
                config_index=config_index,
                messages=messages,
                max_tokens=500,
                temperature=0.8
            )
            
            if response and "choices" in response:
                reply = response["choices"][0]["message"]["content"]
                
                # 记录操作
                self.conversation_manager.add_operation(
                    tool_name="模型调用",
                    result=f"使用配置{config_index}成功生成回复"
                )
                
                return reply
            else:
                raise Exception("模型响应格式错误")
                
        except Exception as e:
            error_msg = f"调用失败: {str(e)}"
            self.conversation_manager.add_operation(
                tool_name="模型调用",
                result=error_msg
            )
            raise Exception(error_msg)
    
    def add_user_message(self, name: str, message: str, time: Optional[str] = None):
        """
        添加用户消息到对话记录
        
        Args:
            name: 用户姓名
            message: 消息内容
            time: 时间戳
        """
        self.conversation_manager.add_dialogue(name, message, time)
    
    def add_rin_response(self, response: str, time: Optional[str] = None):
        """
        添加铃音的回复到对话记录
        
        Args:
            response: 铃音的回复
            time: 时间戳
        """
        self.conversation_manager.add_dialogue("铃音", response, time)
    
    def update_system_template(self, new_template: str):
        """
        更新系统提示词模板
        
        Args:
            new_template: 新的系统提示词模板
        """
        self.system_template = new_template
    
    def get_conversation_summary(self, count: int = 10) -> str:
        """
        获取对话摘要
        
        Args:
            count: 要总结的对话数量
            
        Returns:
            对话摘要
        """
        recent_dialogues = self.conversation_manager.get_recent_dialogues(count)
        
        if not recent_dialogues:
            return "暂无对话记录"
        
        summary_lines = []
        for dialogue in recent_dialogues:
            content = dialogue["content"]
            summary_lines.append(f"{content['name']}: {content['message']}")
        
        return "\n".join(summary_lines)
    
    def save_conversation_summary(self, summary: str, count: int = 10):
        """
        保存对话总结
        
        Args:
            summary: 总结内容
            count: 被总结的对话数量
        """
        recent_dialogues = self.conversation_manager.get_recent_dialogues(count)
        self.conversation_manager.add_summary(summary, recent_dialogues)