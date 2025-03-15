import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from config_utils import load_config
from telegram_bot import (
    start, set_115, bind, unbind, handle_message, 
    handle_transfer, handle_offline, handle_mixed, handle_interaction, handle_error, set_commands
)

def main():
    # 加载配置
    config = load_config()
    tg_token = config.get('tg_token')
    
    if not tg_token:
        print("错误: 未设置Telegram机器人令牌，请在config.json中设置tg_token")
        return
    
    # 创建应用
    application = Application.builder().token(tg_token).build()

    # 添加处理程序
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('115set', set_115))
    application.add_handler(CommandHandler('bind', bind))
    application.add_handler(CommandHandler('unbind', unbind))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(CallbackQueryHandler(handle_transfer, pattern=r'^transfer_'))
    application.add_handler(CallbackQueryHandler(handle_offline, pattern=r'^offline_'))
    application.add_handler(CallbackQueryHandler(handle_mixed, pattern=r'^mixed_'))  # 添加这行
    application.add_handler(CallbackQueryHandler(handle_interaction, pattern=r'^settings_'))
    application.add_error_handler(handle_error)

    # 创建一个新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 在事件循环中运行异步任务以设置命令菜单
    loop.run_until_complete(set_commands(application))

    # 启动 bot
    print("机器人已启动...")
    application.run_polling()

if __name__ == '__main__':
    main()
