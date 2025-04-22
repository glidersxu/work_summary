# 工作总结插件

这是一个基于 OpenAI API 的群聊工作总结插件，可以自动分析群聊内容，提取工作任务并生成总结。

## 功能特点

1. **自动总结**：在指定时间自动分析群聊内容，生成工作任务总结
2. **手动触发**：支持通过命令手动触发总结
3. **群组管理**：支持多群组管理，可配置不同群组的总结时间
4. **数据清理**：自动清理过期聊天记录
5. **智能分析**：使用 OpenAI API 智能分析聊天内容，提取工作任务

## 安装说明

1. 克隆仓库到本地：
```bash
git clone https://github.com/gliders/work_summary.git
cd work_summary
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置插件：
   - 复制 `config.json.template` 为 `config.json`
   - 修改 `config.json` 中的配置项

## 配置说明

配置文件 `config.json` 包含以下配置项：

```json
{
    "open_ai_api_base": "http:///v1",  // OpenAI API基础URL
    "open_ai_api_key": "sk-",          // OpenAI API密钥
    "open_ai_model": "gpt-4o-mini",    // 使用的模型
    "white_chat_name": ["群聊1", "群聊2"],  // 白名单群聊列表
    "summary_time": "16:00",           // 自动总结时间
    "cleanup_time": "01:00",           // 数据清理时间
    "cleanup_days": 3,                 // 数据保留天数
    "task_prompt": "..."               // 任务提取提示词
}
```

### 配置项说明

- `open_ai_api_base`：OpenAI API的基础URL
- `open_ai_api_key`：OpenAI API的访问密钥
- `open_ai_model`：使用的OpenAI模型名称
- `white_chat_name`：需要监控的群聊名称列表
- `summary_time`：自动生成总结的时间，格式为"HH:MM"
- `cleanup_time`：清理过期数据的时间，格式为"HH:MM"
- `cleanup_days`：聊天记录保留的天数
- `task_prompt`：用于提取工作任务的提示词模板

## 使用说明

### 自动总结

插件会在配置的 `summary_time` 时间自动：
1. 获取当天的聊天记录
2. 使用 OpenAI API 分析内容
3. 提取工作任务
4. 生成总结并发送到群组

### 手动触发

在群聊中发送以下命令触发总结：
```
总结聊天 [数量]
```
例如：
```
总结聊天 30  // 总结最近30条消息
总结聊天     // 总结最近99条消息（默认）
```

### 任务提取规则

插件会按照以下规则提取工作任务：
1. 必须是明确提出的工作任务
2. 必须包含具体的执行要求或目标
3. 必须明确指定负责人或执行者
4. 如果有截止时间，必须明确提取

### 输出格式

总结会按照以下格式输出：
```
【编号】：1
【负责人】：张三,李四
【工作要求】：具体的工作内容和要求
【截止时间】：2024-04-25
------------
```

## 数据库结构

插件使用 SQLite 数据库存储数据，包含以下表：

1. `chat_records`：聊天记录表
   - id：记录ID
   - group_id：群组ID
   - group_name：群组名称
   - user_nickname：用户昵称
   - content：消息内容
   - create_time：创建时间

2. `group_info`：群组信息表
   - group_id：群组ID
   - group_name：群组名称
   - last_summary_time：最后总结时间

## 注意事项

1. 确保 OpenAI API 配置正确
2. 群组名称必须与配置中的 `white_chat_name` 匹配
3. 时间格式必须为 "HH:MM"
4. 建议定期备份数据库文件

## 常见问题

1. **总结没有生成**
   - 检查 OpenAI API 配置是否正确
   - 确认群组名称是否在白名单中
   - 查看日志文件排查问题

2. **消息发送失败**
   - 检查网络连接
   - 确认群组ID是否正确
   - 查看错误日志获取详细信息

3. **数据清理异常**
   - 检查数据库文件权限
   - 确认清理时间格式是否正确
   - 查看日志文件排查问题

## 更新日志

### v0.1
- 初始版本发布
- 支持自动总结和手动触发
- 支持多群组管理
- 实现数据自动清理

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进这个项目。

## 许可证

MIT License
