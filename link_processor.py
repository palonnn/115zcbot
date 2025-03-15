import re
import urllib.parse
from p115 import P115Client, P115Offline
from p115_transfer import extract_share_info, find_valid_links, share_save

# 提取所有类型的链接并分类
def extract_all_links(content, entities=None):
    # 结果字典
    result = {
        "share_links": [],  # 115分享链接
        "url_links": [],    # HTTP/HTTPS/FTP链接
        "magnet_links": [], # 磁力链接
        "ed2k_links": []    # 电驴链接
    }
    
    # 1. 从实体中提取text_link类型的URL (Telegram特有)
    if entities:
        for entity in entities:
            if entity.type == 'text_link' and entity.url:
                url = entity.url
                # 检查是否是115分享链接
                if any(domain in url for domain in ["115.com/s/", "115cdn.com/s/", "anxia.com/s/"]):
                    result["share_links"].append(url)
                elif url.startswith("magnet:?xt="):
                    result["magnet_links"].append(url)
                elif url.startswith("ed2k://"):
                    result["ed2k_links"].append(url)
                else:
                    result["url_links"].append(url)
    
    # 2. 从文本内容中提取常规链接
    lines = content.split('\n')
    
    for line in lines:
        # 首先检查行中是否包含关键词
        if "115.com" in line or "115cdn.com" in line or "anxia.com" in line:
            # 1. 首先尝试提取标准URL (带http/https)
            urls = re.findall(r'https?://(?:115\.com|115cdn\.com|anxia\.com)/s/[^\s]+', line)
            
            # 2. 如果没找到标准URL，尝试提取无协议前缀的URL
            if not urls:
                # 匹配115.com或anxia.com开头的文本直到空格或行末
                domain_matches = re.findall(r'((?:115\.com|115cdn\.com|anxia\.com)/s/[^\s]+)', line)
                urls = ["https://" + match for match in domain_matches]
            
            for url in urls:
                # 清理URL末尾可能的标点符号
                url = url.rstrip(',.;:"\']')
                share_code, receive_code = extract_share_info(url)
                if share_code and receive_code and url not in result["share_links"]:
                    result["share_links"].append(url)
        
        # 提取磁力链接
        if "magnet:" in line:
            magnet_urls = re.findall(r'magnet:\?xt=[^\s]+', line)
            for url in magnet_urls:
                url = url.rstrip(',.;:"\']')
                if url not in result["magnet_links"]:
                    result["magnet_links"].append(url)
        
        # 提取电驴链接
        if "ed2k:" in line:
            ed2k_matches = re.findall(r'ed2k://\|[^\s]+', line)
            for url in ed2k_matches:
                url = url.rstrip(',.;:"\']')
                if url not in result["ed2k_links"]:
                    result["ed2k_links"].append(url)
        
        # 提取其他HTTP链接 (排除已经找到的115链接)
        http_urls = re.findall(r'https?://[^\s]+', line)
        for url in http_urls:
            url = url.rstrip(',.;:"\']')
            if not any(domain in url for domain in ["115.com/s/", "115cdn.com/s/", "anxia.com/s/"]) and url not in result["url_links"]:
                result["url_links"].append(url)
    
    return result

# 混合处理所有类型链接
async def process_mixed_links(cookie, content, folder_id, entities=None):
    # 提取并分类所有链接
    links = extract_all_links(content, entities)
    
    # 结果统计
    results = {
        "share": {"success": 0, "failure": 0, "reasons": []},
        "offline": {"success": 0, "failure": 0, "reasons": []}
    }
    
    client = P115Client(cookie)
    
    # 1. 处理115分享链接
    if links["share_links"]:
        share_links = links["share_links"]
        for link in share_links:
            try:
                share_code, receive_code = extract_share_info(link)
                if share_code and receive_code:
                    res = share_save(client, share_code, receive_code, folder_id)
                    if res.get('state', False):
                        results["share"]["success"] += 1
                    else:
                        results["share"]["failure"] += 1
                        results["share"]["reasons"].append(f"{link}: {res.get('error', '未知错误')}")
            except Exception as e:
                results["share"]["failure"] += 1
                results["share"]["reasons"].append(f"{link}: {str(e)}")
    
    # 2. 处理HTTP/HTTPS/FTP链接
    url_links = links["url_links"]
    if url_links:
        try:
            payload = {}
            if len(url_links) == 1:
                payload["url"] = url_links[0]
                if folder_id:
                    payload["wp_path_id"] = folder_id
                result = await client.offline_add_url(payload, async_=True)
            else:
                for i, url in enumerate(url_links):
                    payload[f"url[{i}]"] = url
                if folder_id:
                    payload["wp_path_id"] = folder_id
                result = await client.offline_add_urls(payload, async_=True)
                
            if result.get("state", False):
                results["offline"]["success"] += len(url_links)
            else:
                results["offline"]["failure"] += len(url_links)
                error_msg = result.get("error_msg", '未知错误')
                results["offline"]["reasons"].append(f"URL链接添加失败: {error_msg}")
        except Exception as e:
            results["offline"]["failure"] += len(url_links)
            results["offline"]["reasons"].append(f"URL链接添加失败: {str(e)}")
    
    # 3. 处理电驴链接 - 单独处理每个电驴链接
    for ed2k in links["ed2k_links"]:
        try:
            print(f"正在处理电驴链接: {ed2k}")
            
            # 电驴链接单独处理，每个链接一个请求
            payload = {"url": ed2k}
            if folder_id:
                payload["wp_path_id"] = folder_id
                
            # 使用最直接的API调用
            result = await client.offline_add_url(payload, async_=True)
            print(f"API响应: {result}")
            
            if result.get("state", False):
                results["offline"]["success"] += 1
                print(f"电驴链接添加成功: {ed2k}")
            else:
                results["offline"]["failure"] += 1
                error_msg = result.get("error_msg", "未知错误")
                results["offline"]["reasons"].append(f"电驴链接添加失败: {error_msg}")
                print(f"电驴链接添加失败: {ed2k}, 原因: {error_msg}")
        except Exception as e:
            results["offline"]["failure"] += 1
            results["offline"]["reasons"].append(f"电驴链接添加失败: {str(e)}")
            print(f"电驴链接添加失败(异常): {ed2k}, 错误: {str(e)}")
    
    # 4. 处理磁力链接
    for magnet in links["magnet_links"]:
        try:
            print(f"正在处理磁力链接: {magnet}")
            payload = {"url": magnet}
            if folder_id:
                payload["wp_path_id"] = folder_id
                
            result = await client.offline_add_url(payload, async_=True)
            
            if result.get("state", False):
                results["offline"]["success"] += 1
                print(f"磁力链接添加成功: {magnet}")
            else:
                results["offline"]["failure"] += 1
                error_msg = result.get("error_msg", "未知错误")
                results["offline"]["reasons"].append(f"{magnet}: {error_msg}")
                print(f"磁力链接添加失败: {magnet}, 原因: {error_msg}")
        except Exception as e:
            results["offline"]["failure"] += 1
            results["offline"]["reasons"].append(f"{magnet}: {str(e)}")
            print(f"磁力链接添加失败(异常): {magnet}, 错误: {str(e)}")
    
    # 确保即使没有链接也显示结果
    if not links["share_links"] and not links["url_links"] and not links["magnet_links"] and not links["ed2k_links"]:
        results["offline"]["reasons"].append("未找到任何有效链接")
    
    return results
