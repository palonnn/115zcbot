import re
import time
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from p115 import P115Client

# 配置文件路径
config_file = 'config.json'

# 从 config.json 读取配置
def load_config():
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)

# 保存配置文件
def save_config(config_data):
    with open(config_file, 'w', encoding='utf-8') as file:
        json.dump(config_data, file, indent=4, ensure_ascii=False)

# 提取分享链接中的 share_code 和 receive_code
def extract_share_info(link: str):
    link = link.replace("#", "").replace("&", "").replace(" ", "")
    match = re.search(r's/(\w+)\?password=(\w+)', link)
    if match:
        return match.group(1), match.group(2)
    return None, None

# 同步转存分享链接
def save_share_links(cookie, content, share_cid):
    client = P115Client(cookie)
    fs = client.fs

    links = content.split('\n')
    links = [i.strip() for i in links if len(i.strip()) > 0]

    success_count = 0
    failure_count = 0
    failure_reasons = []
    for link in links:
        share_code, receive_code = extract_share_info(link)

        if share_code and receive_code:
            print(f"分享链接: {link}, share_code: {share_code}, receive_code: {receive_code}")
            try:
                res = share_save(client, share_code, receive_code, share_cid)
                print(f"API 返回: {res}")

                if res.get('state', False):
                    success_count += 1
                    print(f"转存成功: {link}")
                    time.sleep(0.1)
                else:
                    failure_count += 1
                    failure_reasons.append(f"{link}: {res.get('error', '未知错误')}")
                    print(f"转存失败: {link}, 原因: {res}")
            except Exception as e:
                failure_count += 1
                failure_reasons.append(f"{link}: {str(e)}")
                print(f"转存失败: {link}, 错误: {str(e)}")

    return success_count, failure_count, failure_reasons

# 异步转存分享链接
async def async_save_share_links(cookie, content, share_cid):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, save_share_links, cookie, content, share_cid)

# 分享转存的实际调用函数
def share_save(client, share_code, receive_code, share_cid):
    try:
        payload = {'share_code': share_code, 'receive_code': receive_code, 'cid': share_cid}
        res = client.share_receive(payload)
        return res
    except Exception as e:
        return {'error': str(e)}

# 检查用户是否绑定
def is_user_bound(user_id):
    config = load_config()
    return config.get("bound_user_id") == str(user_id)

# 判断是否已绑定且当前用户是否有权限操作
def has_permission(user_id):
    config = load_config()
    bound_id = config.get("bound_user_id")
    # 如果未绑定，任何人都有权限（保持原逻辑）
    if bound_id is None:
        return True
    # 如果已绑定，只有绑定用户有权限
    return str(user_id) == str(bound_id)

# 绑定用户 ID
async def bind(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    args = context.args
    config = load_config()

    # 检查权限
    if not has_permission(user_id):
        await update.message.reply_text("无权限操作")
        return

    # 检查是否已绑定
    if config.get("bound_user_id") is not None:
        await update.message.reply_text("您已绑定，请勿重复绑定。")
        await asyncio.sleep(1)
        await update.message.delete()
        return

    # 检查参数
    if not args or len(args) != 1:
        await update.message.reply_text("请输入 /bind 用户id来绑定。")
        await asyncio.sleep(1)
        await update.message.delete()
        return
    
    bind_id = args[0]

    # 验证发送者ID与绑定ID是否一致
    if str(user_id) != str(bind_id):
        await update.message.reply_text("绑定失败：绑定的ID必须与您的用户ID一致。")
        await asyncio.sleep(1)
        await update.message.delete()
        return

    # 执行绑定
    config["bound_user_id"] = bind_id
    save_config(config)
    await update.message.reply_text(f"成功绑定 {bind_id}")

    await asyncio.sleep(1)
    await update.message.delete()

# 解除绑定用户 ID
async def unbind(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    config = load_config()

    # 检查权限
    if not has_permission(user_id):
        await update.message.reply_text("无权限操作")
        return

    if not is_user_bound(user_id):
        await update.message.reply_text("请输入 /bind 用户id来绑定。")
    else:
        config["bound_user_id"] = None
        save_config(config)
        await update.message.reply_text("成功解除绑定。")

    await asyncio.sleep(1)
    await update.message.delete()

# 处理用户发来的消息
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    # 检查权限
    if not has_permission(user_id):
        await update.message.reply_text("无权限操作")
        return

    if not is_user_bound(update.message.from_user.id):
        await update.message.reply_text("请绑定 ID 使用此机器人。")
        return

    user_message = ""
    if update.message.text:
        user_message = update.message.text.strip()
    elif update.message.caption:
        user_message = update.message.caption.strip()

    # 处理转存相关的消息
    if "115" in user_message or "anxia" in user_message:
        config = load_config()
        cookies = config["cookies"]

        share_code, receive_code = extract_share_info(user_message)
        if share_code and receive_code:
            print(f"识别到分享链接: {user_message}")

            if len(cookies) == 1:
                # 只有一个账号的情况
                account_name, account_data = list(cookies.items())[0]
                cookie = account_data["cookie"]
                cid_map = account_data["cid"]

                if len(cid_map) == 1:
                    # 只有一个 CID，直接使用
                    share_cid = list(cid_map.values())[0]
                    success_count, failure_count, failure_reasons = await async_save_share_links(cookie, user_message, share_cid)

                    result_message = f"转存成功 {success_count} 个链接"
                    if failure_count > 0:
                        result_message += f"\n转存失败 {failure_count} 个链接，失败原因如下："
                        result_message += "\n" + "\n".join(failure_reasons)
                    await update.message.reply_text(result_message)
                else:
                    # 多个 CID，需要选择
                    keyboard = [
                        [InlineKeyboardButton(text=folder_name, callback_data=f"transfer_{account_name}|{cid}")]
                        for folder_name, cid in cid_map.items()
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    context.user_data['user_message'] = user_message
                    await update.message.reply_text("请选择要转存的文件夹：", reply_markup=reply_markup)
            else:
                # 多个账号的情况
                keyboard = [
                    [InlineKeyboardButton(text=account_name, callback_data=f"transfer_{account_name}|select")]
                    for account_name in cookies.keys()
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                context.user_data['user_message'] = user_message
                await update.message.reply_text("请选择要转存的账号：", reply_markup=reply_markup)
        else:
            await update.message.reply_text("未识别到有效的分享链接，请重新发送。")

    # 处理 /115set 相关的消息
    if 'action' in context.user_data:
        config_data = load_config()
        context.user_data['message_ids'].append(update.message.message_id)

        if context.user_data['action'] == 'add_cookie':
            # 账号名
            if 'account' not in context.user_data:
                account_name = update.message.text
                # 检查账号名重复
                if account_name in config_data['cookies']:
                    message = await update.message.reply_text("账号名重复，请重新输入。")
                    context.user_data['message_ids'].append(message.message_id)
                    return

                context.user_data['account'] = account_name
                message = await update.message.reply_text(f"请发送 {account_name} 的 Cookie：")
                context.user_data['message_ids'].append(message.message_id)

            # Cookie
            elif 'cookie' not in context.user_data:
                cookie_value = update.message.text
                # 检查Cookie值重复
                if any(cookie_value == info['cookie'] for info in config_data['cookies'].values()):
                    message = await update.message.reply_text("Cookie值重复，请重新输入。")
                    context.user_data['message_ids'].append(message.message_id)
                    return

                context.user_data['cookie'] = cookie_value
                message = await update.message.reply_text(f"请发送 {context.user_data['account']} 的文件夹名：")
                context.user_data['message_ids'].append(message.message_id)

            # 文件夹名
            elif 'folder' not in context.user_data:
                folder_name = update.message.text
                account = context.user_data['account']

                # 确保 'cid' 字段存在
                if account not in config_data['cookies']:
                    config_data['cookies'][account] = {'cid': {}}
                if 'cid' not in config_data['cookies'][account]:
                    config_data['cookies'][account]['cid'] = {}

                # 检查文件夹名重复
                if folder_name in config_data['cookies'][account]['cid']:
                    message = await update.message.reply_text("文件夹名重复，请重新输入。")
                    context.user_data['message_ids'].append(message.message_id)
                    return

                context.user_data['folder'] = folder_name
                message = await update.message.reply_text(f"请发送 {context.user_data['account']} 的 CID：")
                context.user_data['message_ids'].append(message.message_id)

            # CID
            elif 'cid' not in context.user_data:
                cid_value = update.message.text
                account = context.user_data['account']

                # 确保 'cid' 字段存在
                if account not in config_data['cookies']:
                    config_data['cookies'][account] = {'cid': {}}
                if 'cid' not in config_data['cookies'][account]:
                    config_data['cookies'][account]['cid'] = {}

                # 检查CID值重复
                if cid_value in config_data['cookies'][account]['cid'].values():
                    message = await update.message.reply_text("CID值重复，请重新输入。")
                    context.user_data['message_ids'].append(message.message_id)
                    return

                context.user_data['cid'] = cid_value

                # 更新配置文件
                account = context.user_data['account']
                cookie = context.user_data['cookie']
                folder = context.user_data['folder']
                cid = context.user_data['cid']

                # 添加账号和Cookie
                config_data['cookies'][account] = {
                    'cookie': cookie,
                    'cid': {}
                }
                # 添加文件夹和CID
                config_data['cookies'][account]['cid'][folder] = cid
                save_config(config_data)

                # 清除缓存数据
                del context.user_data['action']
                del context.user_data['account']
                del context.user_data['cookie']
                del context.user_data['folder']
                del context.user_data['cid']

                message = await update.message.reply_text(f"添加成功！账号 {account} Cookie 和 CID 已成功添加。")
                context.user_data['message_ids'].append(message.message_id)
                await delete_all_messages(context, update.message.chat_id)

        elif context.user_data['action'] == 'change_account_name':
            account_name = context.user_data['selected_account']
            new_account_name = update.message.text

            if new_account_name in config_data['cookies']:
                message = await update.message.reply_text("账号名重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            context.user_data['new_account_name'] = new_account_name
            context.user_data['action'] = 'wait_for_cookie'

            message = await update.message.reply_text(f"请输入新的Cookie：")
            context.user_data['message_ids'].append(message.message_id)

        elif context.user_data['action'] == 'wait_for_cookie':
            new_account_name = context.user_data['new_account_name']
            new_cookie_value = update.message.text

            if any(new_cookie_value == info['cookie'] for info in config_data['cookies'].values()):
                message = await update.message.reply_text("Cookie值重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            account_name = context.user_data['selected_account']

            if account_name in config_data['cookies']:
                config_data['cookies'][new_account_name] = {
                    'cookie': new_cookie_value,
                    'cid': config_data['cookies'][account_name].get('cid', {})
                }

                del config_data['cookies'][account_name]

                save_config(config_data)

                message = await update.message.reply_text(f"更改成功！")
                context.user_data['message_ids'].append(message.message_id)
                await delete_all_messages(context, update.message.chat_id)

                del context.user_data['action']
                del context.user_data['selected_account']
                del context.user_data['new_account_name']
            else:
                message = await update.message.reply_text(f"错误：账号 {account_name} 未找到。请确保你选择了正确的账号进行更改。")
                context.user_data['message_ids'].append(message.message_id)

        elif context.user_data['action'] == 'change_cid_name':
            account_name = context.user_data['selected_account']
            cid_name = context.user_data['selected_cid']
            new_cid_name = update.message.text

            if new_cid_name in config_data['cookies'][account_name]['cid']:
                message = await update.message.reply_text("CID名称重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            context.user_data['new_cid_name'] = new_cid_name
            context.user_data['action'] = 'wait_for_cid_value'

            message = await update.message.reply_text(f"请输入新的CID：")
            context.user_data['message_ids'].append(message.message_id)

        elif context.user_data['action'] == 'wait_for_cid_value':
            account_name = context.user_data['selected_account']
            new_cid_name = context.user_data['new_cid_name']
            new_cid_value = update.message.text

            cid_name = context.user_data['selected_cid']

            if new_cid_value in config_data['cookies'][account_name]['cid'].values():
                message = await update.message.reply_text("CID值重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            if account_name in config_data['cookies'] and 'cid' in config_data['cookies'][account_name]:
                if cid_name in config_data['cookies'][account_name]['cid']:
                    config_data['cookies'][account_name]['cid'][new_cid_name] = new_cid_value

                    if new_cid_name != cid_name:
                        del config_data['cookies'][account_name]['cid'][cid_name]

                    save_config(config_data)

                    message = await update.message.reply_text(f"CID修改成功！")
                    context.user_data['message_ids'].append(message.message_id)
                    await delete_all_messages(context, update.message.chat_id)

                    del context.user_data['action']
                    del context.user_data['selected_account']
                    del context.user_data['selected_cid']
                    del context.user_data['new_cid_name']
                else:
                    message = await update.message.reply_text(f"错误：CID {cid_name} 未找到。")
                    context.user_data['message_ids'].append(message.message_id)
            else:
                message = await update.message.reply_text(f"错误：无法修改CID。请确保选择了正确的账号和CID。")
                context.user_data['message_ids'].append(message.message_id)

        elif context.user_data['action'] == 'add_cid_name':
            account_name = context.user_data['selected_account']
            new_cid_name = update.message.text

            if new_cid_name in config_data['cookies'][account_name]['cid']:
                message = await update.message.reply_text("CID名称重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            context.user_data['new_cid_name'] = new_cid_name
            context.user_data['action'] = 'add_cid_value'

            message = await update.message.reply_text("请输入CID：")
            context.user_data['message_ids'].append(message.message_id)

        elif context.user_data['action'] == 'add_cid_value':
            account_name = context.user_data['selected_account']
            new_cid_name = context.user_data['new_cid_name']
            new_cid_value = update.message.text

            if new_cid_value in config_data['cookies'][account_name]['cid'].values():
                message = await update.message.reply_text("CID值重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            if 'cid' not in config_data['cookies'][account_name]:
                config_data['cookies'][account_name]['cid'] = {}

            config_data['cookies'][account_name]['cid'][new_cid_name] = new_cid_value
            save_config(config_data)

            message = await update.message.reply_text("CID添加成功！")
            context.user_data['message_ids'].append(message.message_id)
            await delete_all_messages(context, update.message.chat_id)

            del context.user_data['action']
            del context.user_data['selected_account']
            del context.user_data['new_cid_name']

        else:
            message = await update.message.reply_text("请先选择一个操作。")
            context.user_data['message_ids'].append(message.message_id)

# 处理转存按钮点击事件
async def handle_transfer(update: Update, context: CallbackContext):
    user_id = update.callback_query.from_user.id

    # 检查权限
    if not has_permission(user_id):
        await update.callback_query.answer("无权限操作")
        return

    if not is_user_bound(update.callback_query.from_user.id):
        await update.callback_query.answer("请绑定用户 ID 才能使用此功能。")
        return

    query = update.callback_query
    data = query.data
    config = load_config()
    cookies = config["cookies"]

    if "|select" in data:
        account_name = data.split("|")[0].replace("transfer_", "")
        account_data = cookies[account_name]
        cid_map = account_data["cid"]

        # 检查 CID 数量
        if len(cid_map) == 1:
            # 如果只有一个 CID，直接使用
            share_cid = list(cid_map.values())[0]
            cookie = account_data["cookie"]
            user_message = context.user_data.get('user_message', '')

            if user_message:
                success_count, failure_count, failure_reasons = await async_save_share_links(cookie, user_message, share_cid)

                result_message = f"转存成功 {success_count} 个链接"
                if failure_count > 0:
                    result_message += f"\n转存失败 {failure_count} 个链接，失败原因如下："
                    result_message += "\n" + "\n".join(failure_reasons)
                await query.edit_message_text(result_message)
            else:
                await query.edit_message_text("未找到有效的分享链接，操作失败！")
        else:
            # 多个 CID，需要选择
            keyboard = [
                [InlineKeyboardButton(text=folder_name, callback_data=f"transfer_{account_name}|{cid}")]
                for folder_name, cid in cid_map.items()
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("请选择要转存的文件夹：", reply_markup=reply_markup)
    else:
        account_name, share_cid = data.replace("transfer_", "").split("|")
        account_data = cookies[account_name]
        cookie = account_data["cookie"]

        user_message = context.user_data.get('user_message', '')

        if user_message:
            success_count, failure_count, failure_reasons = await async_save_share_links(cookie, user_message, share_cid)

            result_message = f"转存成功 {success_count} 个链接"
            if failure_count > 0:
                result_message += f"\n转存失败 {failure_count} 个链接，失败原因如下："
                result_message += "\n" + "\n".join(failure_reasons)
            await query.edit_message_text(result_message)
        else:
            await query.edit_message_text("未找到有效的分享链接，操作失败！")
    await query.answer()

# 错误处理
async def handle_error(update: Update, context: CallbackContext):
    print(f'错误: {update} 引发错误 {context.error}')

# 设置命令菜单
async def set_commands(application: Application):
    # 清除旧的命令
    await application.bot.delete_my_commands()
    
    # 设置新的命令
    commands = [
        ('start', '开始'),
        ('115set', '115设置'),
        ('bind', '绑定'),
        ('unbind', '解绑')
    ]
    await application.bot.set_my_commands(commands)

# 处理/start命令
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    # 检查权限
    if not has_permission(user_id):
        await update.message.reply_text("无权限操作")
        return

    if not is_user_bound(update.message.from_user.id):
        await update.message.reply_text("请绑定用户 ID 才能使用此机器人。")
    else:
        await update.message.reply_text("请发送分享链接，我会帮你转存。")

    await asyncio.sleep(1)
    await update.message.delete()

# 创建账号列表菜单
def create_account_keyboard(cookies):
    keyboard = []
    row = []
    for account in cookies.keys():
        row.append(InlineKeyboardButton(account, callback_data=f'settings_account_{account}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("添加", callback_data='settings_add_cookie'), InlineKeyboardButton("退出", callback_data='settings_exit')])
    return InlineKeyboardMarkup(keyboard)

# 优化后的/115set命令，直接显示账号列表
async def set_115(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # 检查权限
    if not has_permission(user_id):
        await update.message.reply_text("无权限操作")
        return

    if not is_user_bound(update.message.from_user.id):
        await update.message.reply_text("请绑定用户 ID 才能使用此功能。")
        await asyncio.sleep(1)
        await update.message.delete()
    else:
        config_data = load_config()
        reply_markup = create_account_keyboard(config_data.get('cookies', {}))
        context.user_data['message_ids'] = [update.message.message_id]
        message = await update.message.reply_text('选择账号管理:', reply_markup=reply_markup)
        context.user_data['message_ids'].append(message.message_id) 
    
# 删除所有相关消息
async def delete_all_messages(context: CallbackContext, chat_id: int):
    if 'message_ids' in context.user_data:
        await asyncio.sleep(1)  
        for message_id in list(context.user_data['message_ids']):  # 使用 list() 以避免运行时修改
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass  # 忽略删除失败的异常
        context.user_data['message_ids'].clear()  # 确保清除列表以避免重复尝试删除

# 处理交互式菜单
async def handle_interaction(update: Update, context: CallbackContext) -> None:
    user_id = update.callback_query.from_user.id

    # 检查权限
    if not has_permission(user_id):
        await update.callback_query.answer("无权限操作")
        return

    if not is_user_bound(update.callback_query.from_user.id):
        await update.callback_query.answer("请绑定用户 ID 才能使用此功能。")
        return

    query = update.callback_query
    await query.answer()

    data = query.data

    # 处理 /115set 的交互
    if data.startswith('settings_account_'):
        account_name = data.split('settings_account_', 1)[1]
        context.user_data['selected_account'] = account_name

        config_data = load_config()
        if account_name in config_data['cookies']:
            account_info = config_data['cookies'][account_name]

            keyboard = [
                [
                    InlineKeyboardButton("更改", callback_data=f'settings_change_cookie_{account_name}'),
                    InlineKeyboardButton("删除", callback_data=f'settings_delete_cookie_{account_name}'),
                    InlineKeyboardButton("CID", callback_data=f'settings_manage_cid_{account_name}')
                ],
                [InlineKeyboardButton("返回", callback_data='settings_back_to_accounts'), InlineKeyboardButton("退出", callback_data='settings_exit')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            message = await query.edit_message_text(f"账号名: {account_name}\nCookie: {account_info.get('cookie')}", reply_markup=reply_markup)
            context.user_data['message_ids'].append(message.message_id)
        else:
            message = await query.edit_message_text(f"错误：未找到账号 {account_name} 的配置。")
            context.user_data['message_ids'].append(message.message_id)

    elif data == 'settings_add_cookie':
        message = await query.edit_message_text(text="请发送账号名：")
        context.user_data['message_ids'].append(message.message_id)
        context.user_data['action'] = 'add_cookie'

    elif data.startswith('settings_manage_cid_'):
        account_name = data.split('settings_manage_cid_', 1)[1]
        context.user_data['selected_account'] = account_name

        config_data = load_config()
        if account_name in config_data['cookies']:
            cid_data = config_data['cookies'][account_name].get('cid', {})

            # 横向排列CID按钮
            keyboard = []
            row = []
            for cid_name in cid_data.keys():
                row.append(InlineKeyboardButton(cid_name, callback_data=f'settings_cid_{account_name}_{cid_name}'))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)

            keyboard.append([InlineKeyboardButton("添加", callback_data=f'settings_add_cid_{account_name}')])
            keyboard.append([InlineKeyboardButton("返回", callback_data=f'settings_account_{account_name}'), InlineKeyboardButton("退出", callback_data='settings_exit')])

            reply_markup = InlineKeyboardMarkup(keyboard)
            message = await query.edit_message_text(f"账号名: {account_name} 的CID:", reply_markup=reply_markup)
            context.user_data['message_ids'].append(message.message_id)
        else:
            message = await query.edit_message_text(f"错误：未找到账号 {account_name} 的配置。")
            context.user_data['message_ids'].append(message.message_id)

    elif data.startswith('settings_cid_'):
        parts = data.split('_', 3)
        if len(parts) == 4:
            _, _, account_name, cid_name = parts
            context.user_data['selected_account'] = account_name
            context.user_data['selected_cid'] = cid_name

            config_data = load_config()
            if account_name in config_data['cookies']:
                cid_value = config_data['cookies'][account_name]['cid'].get(cid_name, '未设置')

                keyboard = [
                    [InlineKeyboardButton("更改", callback_data=f'settings_change_cid_{account_name}_{cid_name}'),
                     InlineKeyboardButton("删除", callback_data=f'settings_delete_cid_{account_name}_{cid_name}')],
                    [InlineKeyboardButton("返回", callback_data=f'settings_manage_cid_{account_name}'),
                     InlineKeyboardButton("退出", callback_data='settings_exit')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message = await query.edit_message_text(f"名称: {cid_name}\nCID: {cid_value}", reply_markup=reply_markup)
                context.user_data['message_ids'].append(message.message_id)
            else:
                message = await query.edit_message_text(f"错误：未找到CID {cid_name} 的配置。")
                context.user_data['message_ids'].append(message.message_id)
        else:
            await query.edit_message_text("无效的 CID 数据格式。")

    elif data.startswith('settings_change_cid_'):
        account_name = context.user_data.get('selected_account')
        cid_name = context.user_data.get('selected_cid')
        if account_name and cid_name:
            message = await query.edit_message_text(f"请发送 {cid_name} 的新CID名称：")
            context.user_data['message_ids'].append(message.message_id)
            context.user_data['action'] = 'change_cid_name'
        else:
            await query.edit_message_text("无效的请求，缺少账号或CID信息。")

    elif data.startswith('settings_delete_cid_'):
        account_name = context.user_data.get('selected_account')
        cid_name = context.user_data.get('selected_cid')
        if account_name and cid_name:
            config_data = load_config()

            if account_name in config_data['cookies'] and cid_name in config_data['cookies'][account_name]['cid']:
                del config_data['cookies'][account_name]['cid'][cid_name]
                save_config(config_data)
                message = await query.edit_message_text(f"CID {cid_name} 已删除。")
                context.user_data['message_ids'].append(message.message_id)
                await delete_all_messages(context, query.message.chat_id)
            else:
                message = await query.edit_message_text(f"错误：未找到CID {cid_name} 的配置。")
                context.user_data['message_ids'].append(message.message_id)
        else:
            await query.edit_message_text("无效的请求，缺少账号或CID信息。")

    elif data.startswith('settings_add_cid_'):
        account_name = context.user_data.get('selected_account')
        if account_name:
            message = await query.edit_message_text(f"请发送CID的名称：")
            context.user_data['message_ids'].append(message.message_id)
            context.user_data['action'] = 'add_cid_name'
        else:
            await query.edit_message_text("无效的请求，缺少账号信息。")

    elif data.startswith('settings_change_cookie_'):
        account_name = context.user_data.get('selected_account')
        if account_name:
            message = await query.edit_message_text(f"请发送 {account_name} 的新账号名：")
            context.user_data['message_ids'].append(message.message_id)
            context.user_data['action'] = 'change_account_name'
        else:
            await query.edit_message_text("无效的请求，缺少账号信息。")

    elif data.startswith('settings_delete_cookie_'):
        account_name = context.user_data.get('selected_account')
        if account_name:
            config_data = load_config()
            
            if account_name in config_data['cookies']:
                del config_data['cookies'][account_name]
                save_config(config_data)
                message = await query.edit_message_text(f"账号名: {account_name} 已删除。")
                context.user_data['message_ids'].append(message.message_id)
                await delete_all_messages(context, query.message.chat_id)
            else:
                message = await query.edit_message_text(f"错误：未找到账号 {account_name} 的配置。")
                context.user_data['message_ids'].append(message.message_id)
        else:
            await query.edit_message_text("无效的请求，缺少账号信息。")

    elif data == 'settings_back_to_accounts':
        config_data = load_config()
        reply_markup = create_account_keyboard(config_data.get('cookies', {}))
        message = await query.edit_message_text('选择账号管理:', reply_markup=reply_markup)
        context.user_data['message_ids'].append(message.message_id)

    elif data == 'settings_exit':
        await query.delete_message()
        await delete_all_messages(context, query.message.chat_id)
    else:
        await query.edit_message_text("无效的请求。")

def main():
    tg_token = load_config()['tg_token']
    application = Application.builder().token(tg_token).build()

    # 添加处理程序
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('115set', set_115))
    application.add_handler(CommandHandler('bind', bind))
    application.add_handler(CommandHandler('unbind', unbind))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(CallbackQueryHandler(handle_transfer, pattern=r'^transfer_'))
    application.add_handler(CallbackQueryHandler(handle_interaction, pattern=r'^settings_'))
    application.add_error_handler(handle_error)

    # 创建一个新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 在事件循环中运行异步任务以设置命令菜单
    loop.run_until_complete(set_commands(application))

    # 启动 bot
    application.run_polling()

if __name__ == '__main__':
    main()