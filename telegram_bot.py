import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

from config_utils import load_config, save_config, is_user_bound, has_permission
from p115_transfer import extract_share_info, batch_transfer, find_valid_links
from link_processor import process_mixed_links

# 异步转存分享链接
async def async_transfer(cookie, content, share_cid):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, batch_transfer, cookie, content, share_cid)

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
        await update.message.reply_text("请发送分享链接或下载链接，我会帮你转存或添加离线下载任务。")

    await asyncio.sleep(1)
    await update.message.delete()

# 删除所有相关消息
async def delete_all_messages(context: CallbackContext, chat_id: int):
    if 'message_ids' in context.user_data:
        await asyncio.sleep(1)  
        for message_id in list(context.user_data['message_ids']):  # 使用 list() 以避免运行时修改
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass 
        context.user_data['message_ids'].clear()  # 确保清除列表以避免重复尝试删除

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

# 构建结果消息
def build_result_message(results):
    result_message = "*处理结果汇总:*\n"
    
    has_share = results["share"]["success"] > 0 or results["share"]["failure"] > 0
    has_offline = results["offline"]["success"] > 0 or results["offline"]["failure"] > 0
    
    # 115分享链接结果
    if has_share:
        result_message += "\n*【115分享链接】*"
        result_message += f"\n转存成功: {results['share']['success']} 个"
        if results["share"]["failure"] > 0:
            result_message += f"\n转存失败: {results['share']['failure']} 个"
            if results["share"]["reasons"]:
                result_message += "\n失败原因:\n" + "\n".join(results["share"]["reasons"][:5])
                if len(results["share"]["reasons"]) > 5:
                    result_message += f"\n...等共 {len(results['share']['reasons'])} 个失败原因"
    
    # 离线下载链接结果
    if has_offline:
        # 根据是否有分享链接结果来决定是否添加额外空行
        if has_share:
            result_message += "\n\n*【离线下载链接】*"
        else:
            result_message += "\n*【离线下载链接】*"
            
        result_message += f"\n添加成功: {results['offline']['success']} 个"
        if results["offline"]["failure"] > 0:
            result_message += f"\n添加失败: {results['offline']['failure']} 个"
            if results["offline"]["reasons"]:
                result_message += "\n失败原因:\n" + "\n".join(results["offline"]["reasons"][:5])
                if len(results["offline"]["reasons"]) > 5:
                    result_message += f"\n...等共 {len(results['offline']['reasons'])} 个失败原因"
    
    # 如果没有任何内容，显示未找到链接的提示
    if not has_share and not has_offline:
        result_message += "\n未找到任何有效链接或处理过程中出现错误"
        
    return result_message

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

    # 获取消息文本和实体
    message = update.message
    user_message = message.text if message.text else message.caption or ""
    entities = message.entities if message.text else message.caption_entities or []

    # 检查消息是否包含任何我们支持的链接类型或实体
    if ("115.com" in user_message or "115cdn.com" in user_message or "anxia.com" in user_message or
        "http://" in user_message or "https://" in user_message or "ftp://" in user_message or 
        "magnet:" in user_message or "ed2k://" in user_message or
        any(entity.type == 'text_link' for entity in entities)):
        
        config = load_config()
        cookies = config["cookies"]
        
        if len(cookies) == 1:
            # 只有一个账号的情况
            account_name, account_data = list(cookies.items())[0]
            cookie = account_data["cookie"]
            cid_map = account_data["cid"]

            if len(cid_map) == 1:
                # 只有一个 CID，直接使用
                folder_id = list(cid_map.values())[0]
                
                # 使用新的混合处理函数，传递实体
                results = await process_mixed_links(cookie, user_message, folder_id, entities)
                
                # 构建结果消息
                result_message = build_result_message(results)
                
                await update.message.reply_text(result_message, parse_mode='Markdown')
            else:
                # 多个 CID，需要选择
                keyboard = [
                    [InlineKeyboardButton(text=folder_name, callback_data=f"mixed_{account_name}|{cid}")]
                    for folder_name, cid in cid_map.items()
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                # 保存消息和实体信息
                context.user_data['user_message'] = user_message
                context.user_data['message_entities'] = entities
                await update.message.reply_text("请选择要保存内容的文件夹：", reply_markup=reply_markup)
        else:
            # 多个账号的情况
            keyboard = [
                [InlineKeyboardButton(text=account_name, callback_data=f"mixed_{account_name}|select")]
                for account_name in cookies.keys()
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.user_data['user_message'] = user_message
            context.user_data['message_entities'] = entities
            await update.message.reply_text("请选择要使用的账号：", reply_markup=reply_markup)
        return

    # 处理 /115set 相关的消息
    if 'action' in context.user_data:
        config_data = load_config()
        if 'message_ids' not in context.user_data:
            context.user_data['message_ids'] = []
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

            # 检查是否与其他账号名重复(排除当前账号)
            if new_account_name in config_data['cookies'] and new_account_name != account_name:
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
            account_name = context.user_data['selected_account']
            
            # 检查是否与其他账号的Cookie重复(排除当前账号)
            if any(new_cookie_value == info['cookie'] for name, info in config_data['cookies'].items() if name != account_name):
                message = await update.message.reply_text("Cookie值重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            if account_name in config_data['cookies']:
                # 如果账号名没变，就只更新Cookie
                if new_account_name == account_name:
                    config_data['cookies'][account_name]['cookie'] = new_cookie_value
                else:
                    # 否则创建新账号并删除旧账号
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

            # 检查是否与其他CID名称重复(排除当前CID)
            if new_cid_name in config_data['cookies'][account_name]['cid'] and new_cid_name != cid_name:
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

            # 检查与其他CID值是否重复(排除当前CID)
            current_cid_value = config_data['cookies'][account_name]['cid'].get(cid_name)
            other_cid_values = [v for k, v in config_data['cookies'][account_name]['cid'].items() if k != cid_name]
            if new_cid_value in other_cid_values:
                message = await update.message.reply_text("CID值重复，请重新输入。")
                context.user_data['message_ids'].append(message.message_id)
                return

            if account_name in config_data['cookies'] and 'cid' in config_data['cookies'][account_name]:
                if cid_name in config_data['cookies'][account_name]['cid']:
                    # 如果CID名称没变，就只更新值
                    if new_cid_name == cid_name:
                        config_data['cookies'][account_name]['cid'][cid_name] = new_cid_value
                    else:
                        # 否则创建新CID并删除旧CID
                        config_data['cookies'][account_name]['cid'][new_cid_name] = new_cid_value
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
                success_count, failure_count, failure_reasons = await async_transfer(cookie, user_message, share_cid)

                result_message = f"*转存结果:*\n\n转存成功 {success_count} 个链接"
                if failure_count > 0:
                    result_message += f"\n转存失败 {failure_count} 个链接"
                    if len(failure_reasons) > 0 and failure_reasons[0] != "未在消息中找到有效的115分享链接":
                        result_message += f"\n失败原因如下："
                        result_message += "\n" + "\n".join(failure_reasons)
                await query.edit_message_text(result_message, parse_mode='Markdown')
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
            success_count, failure_count, failure_reasons = await async_transfer(cookie, user_message, share_cid)

            result_message = f"*转存结果:*\n\n转存成功 {success_count} 个链接"
            if failure_count > 0:
                result_message += f"\n转存失败 {failure_count} 个链接"
                if len(failure_reasons) > 0 and failure_reasons[0] != "未在消息中找到有效的115分享链接":
                    result_message += f"\n失败原因如下："
                    result_message += "\n" + "\n".join(failure_reasons)
            await query.edit_message_text(result_message, parse_mode='Markdown')
        else:
            await query.edit_message_text("未找到有效的分享链接，操作失败！")
    await query.answer()

# 处理离线下载按钮点击事件
async def handle_offline(update: Update, context: CallbackContext):
    # 保留此方法以兼容旧版本，但将所有处理转交给handle_mixed
    await handle_mixed(update, context)

# 处理混合链接按钮点击事件
async def handle_mixed(update: Update, context: CallbackContext):
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
    pattern = r'^mixed_|^offline_'  # 同时支持mixed_和offline_前缀
    
    # 检测前缀并统一处理
    prefix = "mixed_" if data.startswith("mixed_") else "offline_"
    
    config = load_config()
    cookies = config["cookies"]

    if "|select" in data:
        account_name = data.split("|")[0].replace(prefix, "")
        account_data = cookies[account_name]
        cid_map = account_data["cid"]

        # 检查 CID 数量
        if len(cid_map) == 1:
            # 如果只有一个 CID，直接使用
            folder_id = list(cid_map.values())[0]
            cookie = account_data["cookie"]
            user_message = context.user_data.get('user_message', '')
            entities = context.user_data.get('message_entities', [])

            if user_message:
                await query.edit_message_text("正在处理链接，请稍候...")
                
                # 使用混合处理函数，传递实体
                results = await process_mixed_links(cookie, user_message, folder_id, entities)
                
                # 构建结果消息
                result_message = build_result_message(results)
                
                await query.edit_message_text(result_message, parse_mode='Markdown')
            else:
                await query.edit_message_text("未找到有效的链接，操作失败！")
        else:
            # 多个 CID，需要选择
            keyboard = [
                [InlineKeyboardButton(text=folder_name, callback_data=f"{prefix}{account_name}|{cid}")]
                for folder_name, cid in cid_map.items()
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("请选择要保存内容的文件夹：", reply_markup=reply_markup)
    else:
        account_name, folder_id = data.replace(prefix, "").split("|")
        account_data = cookies[account_name]
        cookie = account_data["cookie"]

        user_message = context.user_data.get('user_message', '')
        entities = context.user_data.get('message_entities', [])

        if user_message:
            await query.edit_message_text("正在处理链接，请稍候...")
            
            # 使用混合处理函数，传递实体
            results = await process_mixed_links(cookie, user_message, folder_id, entities)
            
            # 构建结果消息
            result_message = build_result_message(results)
            
            await query.edit_message_text(result_message, parse_mode='Markdown')
        else:
            await query.edit_message_text("未找到有效的链接，操作失败！")
    await query.answer()

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
    
    # 确保message_ids列表存在
    if 'message_ids' not in context.user_data:
        context.user_data['message_ids'] = []

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
        parts = data.split('_', 4)
        if len(parts) >= 4:
            account_name = parts[3]
            cid_name = parts[4] if len(parts) > 4 else ""
            context.user_data['selected_account'] = account_name
            context.user_data['selected_cid'] = cid_name
            message = await query.edit_message_text(f"请发送 {cid_name} 的新CID名称：")
            context.user_data['message_ids'].append(message.message_id)
            context.user_data['action'] = 'change_cid_name'
        else:
            await query.edit_message_text("无效的请求，缺少账号或CID信息。")

    elif data.startswith('settings_delete_cid_'):
        parts = data.split('_', 4)
        if len(parts) >= 4:
            account_name = parts[3]
            cid_name = parts[4] if len(parts) > 4 else ""
            context.user_data['selected_account'] = account_name
            context.user_data['selected_cid'] = cid_name

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
        account_name = data.split('settings_add_cid_', 1)[1]
        context.user_data['selected_account'] = account_name
        message = await query.edit_message_text(f"请发送CID的名称：")
        context.user_data['message_ids'].append(message.message_id)
        context.user_data['action'] = 'add_cid_name'

    elif data.startswith('settings_change_cookie_'):
        account_name = data.split('settings_change_cookie_', 1)[1]
        context.user_data['selected_account'] = account_name
        message = await query.edit_message_text(f"请发送 {account_name} 的新账号名：")
        context.user_data['message_ids'].append(message.message_id)
        context.user_data['action'] = 'change_account_name'

    elif data.startswith('settings_delete_cookie_'):
        account_name = data.split('settings_delete_cookie_', 1)[1]
        context.user_data['selected_account'] = account_name

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

# 错误处理
async def handle_error(update: Update, context: CallbackContext):
    print(f'错误: {update} 引发错误 {context.error}')
