
# 115zcbot

## 简介

该项目是一个基于 [p115client](https://github.com/ChenyangGao/p115client) 的 Telegram 机器人应用程序，支持发送115分享链接给机器人转存，支持多个115分享链接转存，支持管理账户信息和转存目录等。用户可以通过 Telegram 机器人与该系统进行交互，发送115分享链接机器人会转存到指定115目录。

## 配置说明

在项目根目录下，您需要创建一个名为 `config.json` 的配置文件，文件内容应如下所示：

```json
{
    "cookies": {
        "账号名称": {
            "cookie": "UID=1234; CID=1234; SEID=1234; KID=1234",
            "cid": {
                "目录名称": "目录cid"
            }
        }
    },
    "tg_token": "tg机器人api token",
    "bound_user_id": "tg用户id"
}
```

### **配置项说明**

- **cookies**: 存储用户的 Cookie 信息。
  - **账号名称**: 您的账户名称，可自定义账号名称。
    - **cookie**: 包含用户的 Cookie 字符串，格式为 `UID=...; CID=...; SEID=...; KID=...`。
    - **cid**: 账户相关的目录id。
      - **目录名称**: 目录的名称，可自定义目录名称。
  
- **tg_token**: 您的 Telegram 机器人 API 令牌，用于与 Telegram 进行交互。请替换为您实际的机器人令牌。

- **bound_user_id**: 与 Telegram 用户相关联的用户 ID，填写自己的ID。

## 使用说明

1. 确保您已安装 Python 和所需的库（如 `运行pip install -r requirements.txt`）。
2. 创建并配置 `config.json` 文件，如上所示。
3. 运行程序：
   ```bash
   python 115zcbot.py
   ```
4. 启动后，您可以通过 Telegram 与机器人进行交互，通过发送115分享链接进行转存，获取和管理账户信息。

## 贡献

欢迎任何形式的贡献！请提交问题、功能请求或直接提交拉取请求。

## 许可证

本项目遵循 MIT 许可证。有关详细信息，请参阅 `LICENSE` 文件。