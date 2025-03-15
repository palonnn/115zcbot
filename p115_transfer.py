import re
import time
from p115 import P115Client

# 改进的分享链接提取函数
def extract_share_info(link: str):
    # 处理链接并提取关键信息
    link = link.replace("#", "").replace("&", "").replace(" ", "")
    
    if "115.com/s/" in link or "115cdn.com/s/" in link or "anxia.com/s/" in link:
        match = re.search(r's/(\w+)\?password=(\w+)', link)
        if match:
            return match.group(1), match.group(2)
    
    return None, None

# 在整个文本中查找有效链接
def find_valid_links(content: str):
    lines = content.split('\n')
    valid_links = []
    
    for line in lines:
        # 首先检查行中是否包含关键词
        if "115.com" in line or "115cdn.com" in line or "anxia.com" in line:
            # 1. 首先尝试提取标准URL (带http/https)
            urls = re.findall(r'https?://[^\s]+', line)
            
            # 2. 如果没找到标准URL，尝试提取无协议前缀的URL
            if not urls:
                # 匹配115.com或anxia.com开头的文本直到空格或行末
                domain_matches = re.findall(r'((?:115\.com|115cdn\.com|anxia\.com)/s/[^\s]+)', line)
                urls = ["https://" + match for match in domain_matches]
            
            for url in urls:
                # 清理URL末尾可能的标点符号
                url = url.rstrip(',.;:"\']')
                share_code, receive_code = extract_share_info(url)
                if share_code and receive_code:
                    valid_links.append(url)
    
    return valid_links

# 改进的批量转存函数
def batch_transfer(cookie, content, share_cid):
    client = P115Client(cookie)
    
    # 查找有效链接
    valid_links = find_valid_links(content)
    
    if not valid_links:
        return 0, 0, ["未在消息中找到有效的115分享链接"]
    
    success_count = 0
    failure_count = 0
    failure_reasons = []
    
    for link in valid_links:
        share_code, receive_code = extract_share_info(link)
        
        print(f"处理分享链接: {link}")
        try:
            res = share_save(client, share_code, receive_code, share_cid)
            
            if res.get('state', False):
                success_count += 1
                print(f"转存成功: {link}")
                time.sleep(0.1)  # 避免请求过快
            else:
                failure_count += 1
                failure_reasons.append(f"{link}: {res.get('error', '未知错误')}")
                print(f"转存失败: {link}, 原因: {res}")
        except Exception as e:
            failure_count += 1
            failure_reasons.append(f"{link}: {str(e)}")
            print(f"转存失败: {link}, 错误: {str(e)}")
            
    return success_count, failure_count, failure_reasons

# 单个链接转存
def share_save(client, share_code, receive_code, share_cid):
    try:
        payload = {'share_code': share_code, 'receive_code': receive_code, 'cid': share_cid}
        res = client.share_receive(payload)
        return res
    except Exception as e:
        return {'error': str(e), 'state': False}

# 验证Cookie是否有效
def verify_cookie(cookie):
    try:
        client = P115Client(cookie)
        # 尝试获取用户信息或执行简单操作来验证cookie
        info = client.get_user_info()
        return True, info.get('data', {}).get('user_name', '未知用户')
    except Exception as e:
        return False, str(e)
