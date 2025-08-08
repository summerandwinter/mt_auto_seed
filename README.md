# M-Team 自动种子上传工具

## 项目简介
这是一个自动从M-Team PT站点下载种子并上传到Transmission BT客户端的工具。它可以帮助用户自动管理和同步种子，减少手动操作的繁琐。经过优化，现在支持配置文件管理、错误处理、并行处理和状态持久化等功能。

## 功能特点
- 自动从M-Team站点下载种子
- 使用torrentool库计算种子哈希值
- 与Transmission客户端交互，检查和添加种子
- 实现Transmission连接池，减少重复连接开销
- 支持配置下载参数和连接设置
- 支持并行处理多个种子，提高效率
- 实现状态持久化，记录已处理种子和最后处理页码
- 增强错误处理和重试机制，提高稳定性
- 完善的日志系统，便于调试和监控

## 安装依赖
1. 确保已安装Python 3.8或更高版本
2. 安装所需依赖包：
```bash
pip install -r requirements.txt
```

## 配置说明
1. 复制配置模板文件并修改：
```bash
cp config.yaml.template config.yaml
```

2. 在`config.yaml`文件中配置以下参数：
   - `mt.api_key`: M-Team API密钥
   - `mt.teams`: 要下载种子的团队列表
   - `transmission.host`: Transmission服务器地址
   - `transmission.port`: Transmission服务器端口
   - `transmission.user`: Transmission用户名
   - `transmission.password`: Transmission密码
   - `transmission.save_path`: Transmission下载保存路径
   - `transmission.labels`: Transmission标签
   - `download.request_interval`: 请求间隔(秒)，避免触发反爬
   - `download.max_download_count`: 最大下载数量
   - `download.page_size`: 每页下载数量
   - `retry.initial_retry_delay`: 初始重试延迟(秒)
   - `retry.max_retries`: 最大重试次数
   - `retry.max_retry_delay`: 最大重试延迟(秒)
   - `log.level`: 日志级别 (DEBUG, INFO, WARNING, ERROR)
   - `log.file`: 日志文件路径

## 使用方法
1. 配置好`config.yaml`文件
2. 运行脚本：
```bash
python main.py
```

## 注意事项
1. 请确保遵守M-Team站点规则，合理设置请求间隔
2. 请妥善保管您的API密钥和登录信息
3. 首次运行前请确保Transmission服务器已启动并可访问
4. 工具会自动创建下载目录和存储种子文件
5. `config.yaml`文件包含敏感信息，已被添加到`.gitignore`中，请不要将其提交到代码仓库
6. 状态文件`state.json`和日志文件`mt_auto_seed.log`也已被添加到忽略列表
7. 如遇到连接问题，请检查网络设置和Transmission配置

## 项目结构
```
mt_auto_seed/
├── .gitignore              # Git忽略文件
├── README.md               # 项目说明
├── config.yaml             # 配置文件(本地)
├── config.yaml.template    # 配置模板文件
├── exceptions.py           # 自定义异常类
├── main.py                 # 主程序
├── mt_auto_seed.log        # 日志文件
├── requirements.txt        # 依赖包列表
├── state.json              # 状态文件
├── state_manager.py        # 状态管理模块
├── test_mt_auto_seed.py    # 单元测试
└── torrents/               # 种子文件目录
```

## 依赖包
- requests: 用于HTTP请求
- transmission-rpc: 与Transmission客户端交互
- torrentool: 解析种子文件和计算哈希值
- PyYAML: 解析YAML配置文件