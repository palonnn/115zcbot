import json
import os

# 配置文件路径
CONFIG_FILE = 'config.json'

# 默认配置
DEFAULT_CONFIG = {
    "tg_token": "",
    "bound_user_id": None,
    "cookies": {}
}

# 从配置文件读取配置
def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
        
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print("配置文件格式错误，重置为默认配置")
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG

# 保存配置文件
def save_config(config_data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as file:
        json.dump(config_data, file, indent=4, ensure_ascii=False)

# 检查用户是否绑定
def is_user_bound(user_id):
    config = load_config()
    return config.get("bound_user_id") == str(user_id)

# 判断是否已绑定且当前用户是否有权限操作
def has_permission(user_id):
    config = load_config()
    bound_id = config.get("bound_user_id")
    # 如果未绑定，任何人都有权限
    if bound_id is None:
        return True
    # 如果已绑定，只有绑定用户有权限
    return str(user_id) == str(bound_id)

# 添加/更新账号配置
def update_account(account_name, cookie, folder_name=None, cid=None):
    config = load_config()
    
    if account_name not in config['cookies']:
        config['cookies'][account_name] = {'cookie': cookie, 'cid': {}}
    else:
        config['cookies'][account_name]['cookie'] = cookie
        
    if folder_name and cid:
        config['cookies'][account_name]['cid'][folder_name] = cid
        
    save_config(config)
    return True

# 删除账号
def delete_account(account_name):
    config = load_config()
    if account_name in config['cookies']:
        del config['cookies'][account_name]
        save_config(config)
        return True
    return False

# 获取所有账号信息
def get_all_accounts():
    config = load_config()
    return config.get('cookies', {})
