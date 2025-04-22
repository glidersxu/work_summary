import unittest
from work_summary import WorkSummary
import sqlite3
import os
import json
from datetime import datetime, timedelta

class TestWorkSummary(unittest.TestCase):
    def setUp(self):
        self.plugin = WorkSummary()
        self.db_path = "test_work_records.db"
        self.plugin.db_path = self.db_path
        
    def test_database_initialization(self):
        """测试数据库初始化"""
        self.plugin.init_database()
        self.assertTrue(os.path.exists(self.db_path))
        
        # 验证表结构
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_records'")
            self.assertIsNotNone(cursor.fetchone())
            
    def test_add_content(self):
        """测试添加聊天记录"""
        self.plugin.init_database()
        
        # 模拟消息
        class MockMessage:
            def __init__(self):
                self.other_user_id = "test_group"
                self.actual_user_nickname = "test_user"
                self.content = "测试消息"
                self.create_time = datetime.now().timestamp()
        
        # 添加记录
        self.plugin.add_conetent(MockMessage())
        
        # 验证记录
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chat_records")
            records = cursor.fetchall()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0][2], "test_user")
            self.assertEqual(records[0][3], "测试消息")
            
    def test_config_loading(self):
        """测试配置文件加载"""
        config = self.plugin._load_config_template()
        self.assertIsNotNone(config)
        self.assertIn("open_ai_api_base", config)
        self.assertIn("open_ai_api_key", config)
        self.assertIn("open_ai_model", config)
        
    def tearDown(self):
        """清理测试数据"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

if __name__ == '__main__':
    unittest.main() 