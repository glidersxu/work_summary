# encoding:utf-8

# 导入必要的模块
import plugins  # 插件系统模块
from bridge.context import ContextType  # 上下文类型定义
from bridge.reply import Reply, ReplyType  # 回复类型定义
from channel.chat_message import ChatMessage  # 聊天消息处理
from common.log import logger  # 日志模块
from plugins import Plugin  # 插件基础类
from bridge.context import EventContext, EventAction  # 事件上下文
from common.event_msg import Event  # 事件定义
from config import conf  # 配置模块
import sqlite3  # SQLite数据库
from datetime import datetime  # 日期时间处理
import schedule  # 定时任务调度
import time  # 时间处理
import threading  # 多线程支持
import json  # JSON处理
import os  # 操作系统接口

# 注册插件
@plugins.register(
    name="work_summary",  # 插件名称
    desire_priority=89,  # 插件优先级
    hidden=True,  # 是否隐藏
    desc="工作总结",  # 插件描述
    version="0.1",  # 版本号
    author="胖加菲",  # 作者
)

# 工作总结插件类
class WorkSummary(Plugin):
    # 类属性定义
    open_ai_api_base = ""  # OpenAI API基础URL
    open_ai_api_key = ""  # OpenAI API密钥
    open_ai_model = "gpt-4-0613"  # 使用的模型
    white_chat_name = []  # 白名单群聊列表
    curdir = os.path.dirname(__file__)  # 当前文件所在目录
    db_path = os.path.join(curdir, "work_records.db")  # 数据库文件路径
    task_prompt = ""  # 任务提示词
    summary_time = "17:00"  # 默认总结时间
    cleanup_time = "01:00"  # 默认清理时间
    cleanup_days = 1  # 默认清理天数

    def __init__(self):
        """初始化插件"""
        super().__init__()
        try:
            # 加载配置
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
            
            # 从配置中读取参数
            self.open_ai_api_base = self.config.get("open_ai_api_base", self.open_ai_api_base)
            self.open_ai_api_key = self.config.get("open_ai_api_key", "")
            self.open_ai_model = self.config.get("open_ai_model", self.open_ai_model)
            self.white_chat_name = self.config.get("white_chat_name", [])
            self.task_prompt = self.config.get("task_prompt", "")
            self.summary_time = self.config.get("summary_time", self.summary_time)
            self.cleanup_time = self.config.get("cleanup_time", self.cleanup_time)
            self.cleanup_days = self.config.get("cleanup_days", self.cleanup_days)
            
            # 初始化数据库
            self.init_database()
            
            # 启动定时任务
            self.start_scheduled_tasks()
            
            # 注册事件处理器
            logger.info("[work_summary] inited")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            self.handlers[Event.ON_RECEIVE_MESSAGE] = self.on_receive_message
        except Exception as e:
            logger.error(f"[work_summary]初始化异常：{e}")
            raise "[work_summary] init failed, ignore "

    def init_database(self):
        """初始化数据库"""
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.cursor()
                # 创建聊天记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT,
                        group_name TEXT,
                        user_nickname TEXT,
                        content TEXT,
                        create_time TEXT,
                        UNIQUE(group_id, user_nickname, content, create_time)
                    )
                ''')
                # 创建索引
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_records_group_time ON chat_records(group_id, create_time)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_records_time ON chat_records(create_time)')
                
                # 创建群组信息表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_info (
                        group_id TEXT PRIMARY KEY,
                        group_name TEXT,
                        last_summary_time TEXT
                    )
                ''')
                conn.commit()
                logger.info("[work_summary] 数据库初始化成功")
        except Exception as e:
            logger.error(f"[work_summary] 数据库初始化异常：{e}")
            raise

    def start_scheduled_tasks(self):
        """启动定时任务"""
        def run_schedule():
            """运行定时任务的主循环"""
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(1)  # 减少CPU占用
                except Exception as e:
                    logger.error(f"[work_summary] 定时任务主循环异常：{e}")
                    time.sleep(5)  # 发生异常时等待5秒再继续

        def validate_time(time_str):
            """验证时间格式是否正确"""
            try:
                hour, minute = time_str.split(':')
                if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
                    return True
                return False
            except:
                return False

        def run_with_retry(func, max_retries=3):
            """带重试机制的任务执行"""
            for i in range(max_retries):
                try:
                    func()
                    return
                except Exception as e:
                    if i == max_retries - 1:
                        logger.error(f"[work_summary] 任务执行失败，已达到最大重试次数：{e}")
                    else:
                        logger.warning(f"[work_summary] 任务执行失败，第{i+1}次重试：{e}")
                        time.sleep(2 ** i)  # 指数退避

        try:
            # 设置总结定时任务
            if validate_time(self.summary_time):
                schedule.every().day.at(self.summary_time).do(
                    lambda: run_with_retry(self.generate_daily_task_summary)
                )
                logger.info(f"[work_summary] 设置总结时间为: {self.summary_time}")
            else:
                logger.error(f"[work_summary] 总结时间格式错误: {self.summary_time}")

            # 设置清理定时任务
            if validate_time(self.cleanup_time):
                schedule.every().day.at(self.cleanup_time).do(
                    lambda: run_with_retry(self.cleanup_old_records)
                )
                logger.info(f"[work_summary] 设置清理时间为: {self.cleanup_time}")
            else:
                logger.error(f"[work_summary] 清理时间格式错误: {self.cleanup_time}")

            # 在新线程中运行定时任务
            schedule_thread = threading.Thread(target=run_schedule)
            schedule_thread.daemon = True
            schedule_thread.start()
            logger.info("[work_summary] 定时任务线程启动成功")
        except Exception as e:
            logger.error(f"[work_summary] 启动定时任务异常: {e}")
            raise

    def generate_daily_task_summary(self):
        """生成每日任务总结"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            logger.info(f"[work_summary] 开始生成{today}的任务总结")
            
            for group_name in self.white_chat_name:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        # 获取当天的聊天记录
                        cursor.execute('''
                            SELECT user_nickname, content, create_time 
                            FROM chat_records 
                            WHERE group_id = ? AND date(create_time) = ?
                            ORDER BY create_time
                        ''', (group_name, today))
                        
                        records = cursor.fetchall()
                        if not records:
                            logger.info(f"[work_summary] 群组 {group_name} 今天没有聊天记录")
                            continue
                            
                        # 格式化聊天记录
                        chat_list = [
                            {
                                "user": record[0],
                                "content": record[1],
                                "time": record[2]
                            }
                            for record in records
                        ]
                        
                        logger.info(f"[work_summary] 群组 {group_name} 今天共有 {len(records)} 条聊天记录")
                        
                        # 生成任务总结
                        cont = self.task_prompt + "\n----聊天记录如下：" + json.dumps(chat_list, ensure_ascii=False)
                        task_summary = self.shyl(cont)
                        
                        if not task_summary:
                            logger.error(f"[work_summary] 生成任务总结失败")
                            continue
                            
                        # 发送任务总结到群组
                        reply = Reply()
                        reply.type = ReplyType.TEXT
                        reply.content = f"【{today} 工作任务总结】\n\n{task_summary}"
                        
                        # 获取群组ID并发送消息
                        group_id = self.get_group_id_by_name(group_name)
                        if group_id:
                            if self.send_message(group_id, reply):
                                logger.info(f"[work_summary] 成功发送任务总结到群组 {group_name}")
                            else:
                                logger.error(f"[work_summary] 发送任务总结到群组 {group_name} 失败")
                        else:
                            logger.error(f"[work_summary] 未找到群组 {group_name} 的ID")
                except Exception as e:
                    logger.error(f"[work_summary] 处理群组 {group_name} 时发生异常: {e}")
                    continue
                    
            logger.info(f"[work_summary] 完成{today}的任务总结生成")
        except Exception as e:
            logger.error(f"[work_summary] 生成任务总结时发生异常: {e}")

    def get_group_id_by_name(self, group_name):
        """根据群组名称获取群组ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT group_id 
                    FROM chat_records 
                    WHERE group_name = ?
                    LIMIT 1
                ''', (group_name,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"[work_summary]获取群组ID异常：{e}")
            return None

    def send_message(self, group_id, reply, max_retries=3):
        """发送消息到群组"""
        for attempt in range(max_retries):
            try:
                # 使用桥接器直接发送消息
                from bridge.bridge import Bridge
                bridge = Bridge()
                bridge.send_text_message(reply.content, group_id)
                logger.info(f"[work_summary] 消息发送成功到群组 {group_id}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"[work_summary] 发送消息失败，第{attempt + 1}次重试: {e}")
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"[work_summary] 发送消息失败，已达到最大重试次数: {e}")
                    return False

    def cleanup_old_records(self):
        """清理旧记录"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 开启事务
                cursor.execute('BEGIN TRANSACTION')
                
                try:
                    # 获取要删除的记录数
                    cursor.execute('''
                        SELECT COUNT(*) 
                        FROM chat_records 
                        WHERE date(create_time) < date('now', ?)
                    ''', (f'-{self.cleanup_days} days',))
                    count = cursor.fetchone()[0]
                    
                    if count > 0:
                        # 批量删除旧记录
                        cursor.execute('''
                            DELETE FROM chat_records 
                            WHERE date(create_time) < date('now', ?)
                        ''', (f'-{self.cleanup_days} days',))
                        deleted_count = cursor.rowcount
                        conn.commit()
                        logger.info(f"[work_summary] 已清理 {deleted_count} 条过期记录")
                    else:
                        conn.commit()
                        logger.info("[work_summary] 没有需要清理的记录")
                except Exception as e:
                    conn.rollback()
                    raise e
        except Exception as e:
            logger.error(f"[work_summary]清理旧记录异常：{e}")

    def on_handle_context(self, e_context: EventContext):
        """处理上下文事件"""
        try:
            if e_context["context"].type not in [ContextType.TEXT]:
                return
                
            msg: ChatMessage = e_context["context"]["msg"]
            content = e_context["context"].content.strip()
            
            if not content.startswith("总结聊天"):
                return
                
            reply = Reply()
            reply.type = ReplyType.TEXT
            
            # 检查是否是群聊
            if not e_context["context"]["isgroup"]:
                reply.content = "只支持群聊总结"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 检查是否在白名单中
            if msg.other_user_nickname not in self.white_chat_name:
                reply.content = "该群未开启工作总结功能"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
                
            # 解析聊天记录数量
            number = content[4:].strip()
            number_int = 99  # 默认值
            if number.isdigit():
                number_int = int(number)
                if number_int <= 0:
                    reply.content = "请输入大于0的数字"
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
                    return
                    
            try:
                # 从数据库获取聊天记录
                with sqlite3.connect(self.db_path, timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT user_nickname, content, create_time 
                        FROM chat_records 
                        WHERE group_id = ? 
                        ORDER BY create_time DESC 
                        LIMIT ?
                    ''', (msg.other_user_id, number_int))
                    
                    records = cursor.fetchall()
                    if not records:
                        reply.content = "暂无聊天记录"
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                        return
                        
                    # 格式化聊天记录
                    chat_list = [
                        {
                            "user": record[0],
                            "content": record[1],
                            "time": record[2]
                        }
                        for record in records
                    ]
                    chat_list.reverse()  # 按时间正序排列
                    
                    # 生成任务总结
                    cont = self.task_prompt + "\n----聊天记录如下：" + json.dumps(chat_list, ensure_ascii=False)
                    reply.content = self.shyl(cont)
                    
            except sqlite3.Error as e:
                logger.error(f"[work_summary] 数据库操作异常: {e}")
                reply.content = "获取聊天记录失败，请稍后重试"
            except Exception as e:
                logger.error(f"[work_summary] 处理聊天记录异常: {e}")
                reply.content = "处理聊天记录失败，请稍后重试"
                
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            
        except Exception as e:
            logger.error(f"[work_summary] 处理上下文事件异常: {e}")
            # 确保即使发生异常也能正确设置回复
            if not e_context.get("reply"):
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "处理请求时发生错误，请稍后重试"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS

    def add_content(self, message):
        """添加聊天记录到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 将时间戳转换为字符串格式
                time_str = datetime.fromtimestamp(message.create_time).strftime('%Y-%m-%d %H:%M:%S')
                # 插入数据
                cursor.execute('''
                    INSERT OR IGNORE INTO chat_records (group_id, group_name, user_nickname, content, create_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    message.other_user_id,
                    message.other_user_nickname,  # 群组名称
                    message.actual_user_nickname,  # 用户昵称
                    message.content,
                    time_str
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[work_summary]添加聊天记录异常：{e}")

    def on_receive_message(self, e_context: EventContext):
        """接收消息事件处理"""
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        if msg.other_user_nickname in self.white_chat_name:
            self.add_content(msg)

    def get_help_text(self, **kwargs):
        """获取帮助文本"""
        help_text = "总结聊天+数量；例：总结聊天 30"
        return help_text

    def shyl(self, content, max_retries=3, timeout=30):
        """调用OpenAI API生成总结
        
        Args:
            content: 需要总结的内容
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
        
        Returns:
            str: 生成的总结内容
        """
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # 创建带重试机制的会话
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        url = self.open_ai_api_base + "/chat/completions"
        payload = {
            "model": self.open_ai_model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        headers = {
            'Authorization': f'Bearer {self.open_ai_api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = session.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()  # 抛出非200响应的异常
            
            if response.status_code == 200:
                response_json = response.json()
                content = response_json['choices'][0]['message']['content']
                return content
            
        except requests.exceptions.Timeout:
            logger.error("[work_summary] OpenAI API 请求超时")
            return '请求超时，请稍后重试'
        except requests.exceptions.RequestException as e:
            logger.error(f"[work_summary] OpenAI API 请求异常: {e}")
            return '请求异常，请稍后重试'
        except KeyError as e:
            logger.error(f"[work_summary] OpenAI API 响应格式异常: {e}")
            return '响应格式异常，请稍后重试'
        except Exception as e:
            logger.error(f"[work_summary] OpenAI API 未知异常: {e}")
            return '发生未知错误，请稍后重试'

    def _load_config_template(self):
        """加载配置模板"""
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if not os.path.exists(plugin_config_path):
                logger.error("[work_summary] 配置模板文件不存在")
                return None
                
            with open(plugin_config_path, "r", encoding="utf-8") as f:
                plugin_conf = json.load(f)
                
            # 验证必要配置项
            required_fields = {
                "open_ai_api_base": "OpenAI API基础URL",
                "open_ai_api_key": "OpenAI API密钥",
                "open_ai_model": "OpenAI模型名称",
                "white_chat_name": "白名单群聊列表"
            }
            
            missing_fields = []
            for field, desc in required_fields.items():
                if field not in plugin_conf:
                    missing_fields.append(f"{desc}({field})")
            
            if missing_fields:
                logger.error(f"[work_summary] 配置缺少必要字段: {', '.join(missing_fields)}")
                return None
                
            # 验证配置值的有效性
            if not isinstance(plugin_conf["white_chat_name"], list):
                logger.error("[work_summary] white_chat_name 必须是列表类型")
                return None
                
            if not plugin_conf["open_ai_api_base"].startswith(("http://", "https://")):
                logger.error("[work_summary] open_ai_api_base 必须是有效的URL")
                return None
                
            if not plugin_conf["open_ai_api_key"]:
                logger.error("[work_summary] open_ai_api_key 不能为空")
                return None
                
            return plugin_conf
            
        except json.JSONDecodeError as e:
            logger.error(f"[work_summary] 配置文件JSON格式错误: {e}")
            return None
        except Exception as e:
            logger.error(f"[work_summary] 加载配置模板异常: {e}")
            return None

    def add_group(self, group_id, group_name, summary_time=None):
        """添加群组到白名单"""
        if summary_time is None:
            summary_time = self.summary_time
        if group_name not in self.white_chat_name:
            self.white_chat_name.append(group_name)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO group_info (group_id, group_name, last_summary_time)
                    VALUES (?, ?, ?)
                ''', (group_id, group_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                logger.info(f"[work_summary] 成功添加群组: {group_name}")
        else:
            logger.info(f"[work_summary] 群组已存在: {group_name}")


