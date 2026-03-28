# MediaMaster V2 项目文档

## 项目结构

```
mediamaster-v2-project/
├── app/                 # 主应用目录
│   ├── api/             # API 模块
│   │   ├── library.py   # 媒体库相关接口
│   │   ├── profile.py   # 用户个人资料相关接口
│   │   ├── subscriptions.py  # 订阅相关接口
│   │   └── system.py    # 系统相关接口
│   ├── auth/            # 认证模块
│   │   └── auth.py      # 登录、登出等认证功能
│   ├── core/            # 核心模块
│   │   ├── config.py     # 应用配置
│   │   ├── database.py   # 数据库管理
│   │   └── routes.py     # 路由注册
│   ├── models/          # 数据模型
│   ├── utils/           # 工具函数
│   │   ├── cache.py      # 缓存工具
│   │   └── validation.py # 数据验证
│   └── __init__.py      # 应用初始化
├── static/              # 静态文件
├── templates/           # 模板文件
├── main.py              # 主入口文件
├── requirements.txt     # 依赖包
└── README.md            # 项目说明
```

## 编码规范

### 命名规范
- **模块名**：小写字母，单词之间用下划线分隔（如 `user_profile.py`）
- **类名**：驼峰命名法（如 `DatabaseManager`）
- **函数名**：小写字母，单词之间用下划线分隔（如 `get_user_info`）
- **变量名**：小写字母，单词之间用下划线分隔（如 `user_id`）
- **常量名**：全大写字母，单词之间用下划线分隔（如 `MAX_RETRY_COUNT`）

### 文档规范
- 所有模块、类、函数都应包含文档字符串（docstring）
- 文档字符串应使用三引号包围
- 文档字符串应包含：功能描述、参数说明、返回值说明、异常说明

### 错误处理
- 使用 try-except 捕获异常
- 记录详细的错误日志
- 向用户返回友好的错误信息
- 避免裸 except 语句，应指定具体的异常类型

## 开发流程

1. **代码修改**：修改代码时应遵循编码规范
2. **测试**：修改后应进行测试
3. **提交**：提交代码时应包含清晰的提交信息
4. **部署**：部署前应进行全面测试

## API 文档

### 认证接口
- `POST /login` - 用户登录
- `GET /logout` - 用户登出

### 个人资料接口
- `POST /api/update_profile` - 更新用户资料
- `POST /api/change_password` - 修改密码

### 系统接口
- `GET /api/system_resources` - 获取系统资源信息
- `GET /api/system_processes` - 获取系统进程信息
- `GET /api/site_status` - 获取站点状态信息
- `POST /api/check_site_status` - 手动检查站点状态

### 订阅接口
- `POST /add_subscription` - 手动添加订阅
- `POST /cancel_subscription` - 取消订阅
- `POST /tmdb_subscriptions` - 从热门推荐中添加订阅
- `POST /check_subscriptions` - 检查订阅状态
- `GET|POST /edit_subscription/<type>/<id>` - 编辑订阅
- `POST /delete_subscription/<type>/<id>` - 删除订阅

### 媒体库接口
- `GET /api/search` - 搜索媒体
- `GET /library` - 媒体库页面

## 数据库结构

### 主要表结构
- `USERS` - 用户表
- `LIB_MOVIES` - 电影库表
- `LIB_TVS` - 电视剧库表
- `LIB_TV_SEASONS` - 电视剧季表
- `MISS_MOVIES` - 电影订阅表
- `MISS_TVS` - 电视剧订阅表
- `CONFIG` - 配置表

## 部署说明

### Docker 部署
```bash
docker-compose up -d
```

### 环境变量
- `UID` - 用户ID
- `GID` - 用户组ID
- `GIDLIST` - 用户附加组列表
- `TZ` - 时区设置

## 常见问题

### 1. 站点状态检测失败
- 检查网络连接
- 检查站点是否可访问
- 查看日志获取详细错误信息

### 2. 下载失败
- 检查下载器配置
- 检查网络连接
- 查看日志获取详细错误信息

### 3. 媒体库扫描失败
- 检查媒体库路径权限
- 检查媒体文件格式
- 查看日志获取详细错误信息
