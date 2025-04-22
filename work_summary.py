# encoding:utf-8

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from common.log import logger
from plugins import *
from config import conf
import sqlite3
from datetime import datetime
import schedule
import time
import threading
import json
import os

@plugins.register(
    name="work_summary",
    desire_priority=89,
    hidden=True,
    desc="工作总结",
    version="0.1",
    author="wangcl",
)


class WorkSummary(Plugin):

    open_ai_api_base = ""
    open_ai_api_key = ""
    open_ai_model = "gpt-4-0613"
    white_chat_name = []
    curdir = os.path.dirname(__file__)
    db_path = os.path.join(curdir, "work_records.db")
    task_prompt = ""
    summary_schedule = "0 0 * * *"
    cleanup_schedule = "0 1 * * *"
    def __init__(self):
        
        super().__init__()
        try:
            self.config = super().load_config()
            if not self.config:
                self.config = self._load_config_template()
            self.open_ai_api_base = self.config.get("open_ai_api_base", self.open_ai_api_base)
            self.open_ai_api_key = self.config.get("open_ai_api_key", "")
            self.open_ai_model = self.config.get("open_ai_model", self.open_ai_model)
            self.white_chat_name = self.config.get("white_chat_name", [])
            self.task_prompt = self.config.get("task_prompt", "")
            self.summary_schedule = self.config.get("summary_schedule", "0 0 * * *")
            self.cleanup_schedule = self.config.get("cleanup_schedule", "0 1 * * *")
            
            # 初始化数据库
            self.init_database()
            
            # 启动定时任务
            self.start_scheduled_tasks()
            
            logger.info("[work_summary] inited")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            self.handlers[Event.ON_RECEIVE_MESSAGE] = self.on_receive_message
        except Exception as e:
            logger.error(f"[work_summary]初始化异常：{e}")
            raise "[work_summary] init failed, ignore "

    def init_database(self):
        """初始化数据库"""
       
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 创建聊天记录表，将 create_time 改为 TEXT 类型
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT,
                        user_nickname TEXT,
                        content TEXT,
                        create_time TEXT,
                        UNIQUE(group_id, user_nickname, content, create_time)
                    )
                ''')
                conn.commit()
                logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"[work_summary]数据库初始化异常：{e}")

    def start_scheduled_tasks(self):
        """启动定时任务"""
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(60)

        def validate_time(time_str):
            """验证时间格式"""
            try:
                parts = time_str.split()
                if len(parts) >= 2:
                    hour, minute = parts[1].split(':')
                    if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
                        return True
                return False
            except:
                return False

        try:
            # 验证时间格式
            if validate_time(self.summary_schedule):
                schedule.every().day.at(self.summary_schedule.split()[1]).do(self.generate_daily_task_summary)
            else:
                logger.error(f"[work_summary] 总结定时时间格式错误: {self.summary_schedule}")

            if validate_time(self.cleanup_schedule):
                schedule.every().day.at(self.cleanup_schedule.split()[1]).do(self.cleanup_old_records)
            else:
                logger.error(f"[work_summary] 清理定时时间格式错误: {self.cleanup_schedule}")

            # 在新线程中运行定时任务
            schedule_thread = threading.Thread(target=run_schedule)
            schedule_thread.daemon = True
            schedule_thread.start()
        except Exception as e:
            logger.error(f"[work_summary] 启动定时任务异常: {e}")

    def generate_daily_task_summary(self):
        """生成每日任务总结"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            logger.info(f"[work_summary] 开始生成{today}的任务总结")
            
            for group_name in self.white_chat_name:
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
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
                            
                        chat_list = [
                            {
                                "user": record[0],
                                "content": record[1],
                                "time": record[2]
                            }
                            for record in records
                        ]
                        
                        logger.info(f"[work_summary] 群组 {group_name} 今天共有 {len(records)} 条聊天记录")
                        
                        cont = self.task_prompt + "\n----聊天记录如下：" + json.dumps(chat_list, ensure_ascii=False)
                        task_summary = self.shyl(cont)
                        
                        if not task_summary:
                            logger.error(f"[work_summary] 生成任务总结失败")
                            continue
                            
                        # 发送任务总结到群组
                        reply = Reply()
                        reply.type = ReplyType.TEXT
                        reply.content = f"【{today} 工作任务总结】\n\n{task_summary}"
                        
                        # 获取群组ID
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
                    WHERE group_id = ?
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
                context = {
                    "type": ContextType.TEXT,
                    "content": reply.content,
                    "isgroup": True,
                    "msg": {
                        "other_user_id": group_id
                    }
                }
                self.on_handle_context(context)
                logger.info(f"[work_summary] 消息发送成功到群组 {group_id}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"[work_summary] 发送消息失败，第{attempt + 1}次重试: {e}")
                    time.sleep(2 ** attempt)  # 指数退避
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
                    # 先获取要删除的记录数
                    cursor.execute('''
                        SELECT COUNT(*) 
                        FROM chat_records 
                        WHERE date(create_time) < date('now', '-3 days')
                    ''')
                    count = cursor.fetchone()[0]
                    
                    if count > 0:
                        # 批量删除
                        cursor.execute('''
                            DELETE FROM chat_records 
                            WHERE date(create_time) < date('now', '-3 days')
                        ''')
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
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
       
        content = e_context["context"].content.strip()
        if content.startswith("总结聊天"):
            reply = Reply()
            reply.type = ReplyType.TEXT
            if msg.other_user_nickname in self.white_chat_name:
                reply.content = "我母鸡啊"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            number = content[4:].strip()
            number_int=99
            if number.isdigit():
                # 转换为整数
                number_int = int(number)
            if e_context["context"]["isgroup"]:
                try:
                    # 从数据库获取聊天记录
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT user_nickname, content, create_time 
                            FROM chat_records 
                            WHERE group_id = ? 
                            ORDER BY create_time DESC 
                            LIMIT ?
                        ''', (msg.other_user_id, number_int))
                        
                        records = cursor.fetchall()
                        chat_list = [
                            {
                                "user": record[0],
                                "content": record[1],
                                "time": record[2]
                            }
                            for record in records
                        ]
                        chat_list.reverse()  # 按时间正序排列
                        
                        cont = self.task_prompt + "----聊天记录如下：" + json.dumps(chat_list, ensure_ascii=False)
                        reply.content = self.shyl(cont)
                except Exception as e:
                    logger.error(f"[work_summary]获取聊天记录异常：{e}")
                    reply.content = "获取聊天记录失败"
            else:
                    reply.content = "只做群聊总结"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑

    def on_receive_message(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        msg: ChatMessage = e_context["context"]["msg"]
        if msg.other_user_nickname in self.white_chat_name:
            self.add_conetent(msg)
    def add_conetent(self, message):
        """添加聊天记录到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 将时间戳转换为字符串格式
                time_str = datetime.fromtimestamp(message.create_time).strftime('%Y-%m-%d %H:%M:%S')
                # 插入数据
                cursor.execute('''
                    INSERT OR IGNORE INTO chat_records (group_id, user_nickname, content, create_time)
                    VALUES (?, ?, ?, ?)
                ''', (
                    message.other_user_id,
                    message.actual_user_nickname,
                    message.content,
                    time_str
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[work_summary]添加聊天记录异常：{e}")
    def get_help_text(self, **kwargs):
        help_text = "总结聊天+数量；例：总结聊天 30"
        return help_text
    def shyl(self,content):
        import requests
        import json
        url = self.open_ai_api_base+"/chat/completions"
        payload = json.dumps({
            "model": self.open_ai_model,
         "messages": [{"role": "user", "content": content}],
         "stream": False
        })
        headers = {
           'Authorization': 'Bearer '+self.open_ai_api_key,
           'Content-Type': 'application/json'
        }
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
            # 检查响应状态码
            if response.status_code == 200:
                # 使用.json()方法将响应内容转换为JSON
                response_json = response.json()
                # 提取"content"字段
                content = response_json['choices'][0]['message']['content']
                return content
            else:
                print(f"请求失败，状态码：{response.status_code}")
                return '模型请求失败了，呵呵'
        except:
            return '模型请求失败了，呵呵'
    def _load_config_template(self):
        logger.info("[work_summary]use config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)


