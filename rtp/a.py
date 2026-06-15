#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯净合并模块 - 只合并，不测速
"""

import os
import re
from collections import defaultdict
from urllib.parse import quote

# ================= 配置区域 =================
SOURCE_TXT_DIR = "txt"
SOURCE_M3U_DIR = "m3u"

# 合并配置
MAX_SOURCES_PER_CHANNEL = 2       # 每个频道保留几个源
MAX_CHANNELS_PER_OPERATOR = 500   # 每个运营商最多频道数（0=不限制）

# 频道名称正则处理
ENABLE_CHANNEL_CLEAN = True

# 名称替换规则
CHANNEL_REPLACE_RULES = [
    (r'^4K[\s_\-]*(.+)$', r'\1 4K'),
    (r'^(.+?)4K$', r'\1 4K'),
    (r'4K', '4K'),
    (r'[Cc][Cc][Tt][Vv][-\s]*(\d+)[-\s]*\+', r'CCTV\1+'),
    (r'[Cc][Cc][Tt][Vv][-\s]*(\d+)[-\s]*(HD|高清)?', r'CCTV\1 \2'.strip()),
    (r'[Cc][Cc][Tt][Vv]([^0-9]+)', r'CCTV\1'),
    (r'([^,]+)卫视[-\s]*(HD|高清|4K|SD)?', r'\1卫视 \2'.strip()),
    (r'\s+', ' '),
    (r'^\s+', ''),
    (r'\s+$', ''),
]

# 是否分离4K频道
SPLIT_4K_SEPARATE = True

# 省份列表
PROVINCES = ["北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海",
             "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
             "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西",
             "甘肃", "青海", "宁夏", "新疆"]

# 运营商列表
OPERATORS = ["电信", "联通", "移动", "广电"]

# 合并文件名配置
MERGE_FILE_NAMES = {
    "电信": "电信组播",
    "联通": "联通组播",
    "移动": "移动组播",
    "广电": "广电组播",
    "未知": "其他组播",
}

MERGE_4K_FILE_NAMES = {
    "电信": "电信4K组播",
    "联通": "联通4K组播",
    "移动": "移动4K组播",
    "广电": "广电4K组播",
    "未知": "其他4K组播",
}

KEEP_ORIGIN_FILES = True
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
# ============================================


def clean_channel_name(name):
    """清理频道名称"""
    if not ENABLE_CHANNEL_CLEAN:
        return name.strip()
    
    result = name.strip()
    for pattern, replacement in CHANNEL_REPLACE_RULES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = ' '.join(result.split())
    return result


def parse_filename_info(filename):
    """从文件名解析省份和运营商"""
    province = None
    operator = None
    
    # 提取省份
    for p in PROVINCES:
        if p in filename:
            province = p
            break
    
    # 提取运营商
    for op in OPERATORS:
        if op in filename:
            operator = op
            break
    
    if province is None:
        province = "其他"
    if operator is None:
        operator = "未知"
    
    return province, operator


def is_4k_channel(name):
    """判断是否是4K频道"""
    return '4K' in name


def build_tvg_logo_url(channel_name):
    safe_name = quote(channel_name.strip(), safe="")
    return f"{TVG_LOGO_BASE_URL}{safe_name}.png"


def deduplicate_channels(channels, max_per_channel=2):
    """按频道名去重，每个频道只保留前N个"""
    if not channels:
        return []
    groups = defaultdict(list)
    for name, url in channels:
        groups[name].append((name, url))
    
    result = []
    for name, sources in groups.items():
        result.extend(sources[:max_per_channel])
        if len(sources) > max_per_channel:
            print(f"    [去重] {name}: {len(sources)}个源 → 保留{max_per_channel}个")
    
    return result


def read_all_channels(txt_dir):
    """读取所有txt文件中的频道，按运营商和省份分类"""
    # 结构: {运营商: {省份: [(频道名, URL)]}}
    all_data = {
        "电信": defaultdict(list),
        "联通": defaultdict(list),
        "移动": defaultdict(list),
        "广电": defaultdict(list),
        "未知": defaultdict(list)
    }
    
    if not os.path.exists(txt_dir):
        print(f"[-] 目录不存在: {txt_dir}")
        return all_data
    
    for file in os.listdir(txt_dir):
        if not file.endswith('.txt') or file == "output":
            continue
        
        province, operator = parse_filename_info(file)
        file_path = os.path.join(txt_dir, file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                name, url = line.split(',', 1)
                name = clean_channel_name(name)
                all_data[operator][province].append((name, url.strip()))
    
    return all_data


def save_merge_files_with_genre(txt_dir, m3u_dir, all_data):
    """保存合并文件，带 #genre# 分组"""
    print(f"\n{'='*50}")
    print(f"正在创建合并文件（目录: output）")
    print("="*50)
    
    txt_merge_dir = os.path.join(txt_dir, "output")
    m3u_merge_dir = os.path.join(m3u_dir, "output")
    
    os.makedirs(txt_merge_dir, exist_ok=True)
    os.makedirs(m3u_merge_dir, exist_ok=True)
    
    total_count = 0
    
    for operator, provinces_data in all_data.items():
        if not provinces_data:
            continue
        
        # 分离4K和非4K
        normal_provinces = defaultdict(list)
        _4k_provinces = defaultdict(list)
        
        for province, channels in provinces_data.items():
            for name, url in channels:
                if is_4k_channel(name):
                    _4k_provinces[province].append((name, url))
                else:
                    normal_provinces[province].append((name, url))
        
        # 保存非4K文件
        if normal_provinces:
            file_name = MERGE_FILE_NAMES.get(operator, operator)
            txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
            m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
            
            if os.path.exists(txt_path):
                os.remove(txt_path)
            if os.path.exists(m3u_path):
                os.remove(m3u_path)
            
            txt_lines = []
            m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
            
            for province in sorted(normal_provinces.keys()):
                channels = normal_provinces[province]
                if not channels:
                    continue
                
                channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
                
                if MAX_CHANNELS_PER_OPERATOR > 0 and len(channels) > MAX_CHANNELS_PER_OPERATOR:
                    channels = channels[:MAX_CHANNELS_PER_OPERATOR]
                
                if not channels:
                    continue
                
                # 添加分组标记
                group_name = f"{province}组播"
                txt_lines.append(f"{group_name},#genre#")
                m3u_lines.append(f'#EXTINF:-1 group-title="{group_name}",{group_name}')
                
                for name, url in channels:
                    txt_lines.append(f"{name},{url}")
                    m3u_lines.append(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{group_name}",{name}')
                    m3u_lines.append(url)
                
                print(f"  [{operator}] {province}: {len(channels)} 个频道")
                total_count += len(channels)
            
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(txt_lines))
            with open(m3u_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(m3u_lines))
            
            print(f"  ✓ {operator}: 已保存 -> output/{file_name}")
        
        # 保存4K文件
        if SPLIT_4K_SEPARATE and _4k_provinces:
            file_name = MERGE_4K_FILE_NAMES.get(operator, f"{operator}4K组播")
            txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
            m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
            
            if os.path.exists(txt_path):
                os.remove(txt_path)
            if os.path.exists(m3u_path):
                os.remove(m3u_path)
            
            txt_lines = []
            m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
            
            for province in sorted(_4k_provinces.keys()):
                channels = _4k_provinces[province]
                if not channels:
                    continue
                
                channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
                
                group_name = f"{province}4K组播"
                txt_lines.append(f"{group_name},#genre#")
                m3u_lines.append(f'#EXTINF:-1 group-title="{group_name}",{group_name}')
                
                for name, url in channels:
                    txt_lines.append(f"{name},{url}")
                    m3u_lines.append(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{group_name}",{name}')
                    m3u_lines.append(url)
                
                print(f"  [{operator} 4K] {province}: {len(channels)} 个频道")
                total_count += len(channels)
            
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(txt_lines))
            with open(m3u_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(m3u_lines))
            
            print(f"  ✓ {operator} 4K: 已保存 -> output/{file_name}")
    
    print(f"\n[+] 合并完成，共 {total_count} 个频道")


def delete_origin_files(txt_dir, m3u_dir):
    """删除原文件"""
    if not KEEP_ORIGIN_FILES:
        print("\n[*] 删除原文件...")
        keep = [f"{name}.txt" for name in MERGE_FILE_NAMES.values()]
        keep += [f"{name}.txt" for name in MERGE_4K_FILE_NAMES.values()]
        for file in os.listdir(txt_dir):
            if file.endswith('.txt') and file not in keep and file != "output":
                os.remove(os.path.join(txt_dir, file))
                print(f"  删除: txt/{file}")
        for file in os.listdir(m3u_dir):
            if file.endswith('.m3u') and file not in keep and file != "output":
                os.remove(os.path.join(m3u_dir, file))
                print(f"  删除: m3u/{file}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    txt_dir = os.path.join(project_root, SOURCE_TXT_DIR)
    m3u_dir = os.path.join(project_root, SOURCE_M3U_DIR)
    
    print(f"\n{'='*50}")
    print(f"纯净合并工具（不测速）")
    print(f"4K分离: {'是' if SPLIT_4K_SEPARATE else '否'}")
    print(f"TXT目录: {txt_dir}")
    print(f"{'='*50}")
    
    if not os.path.exists(txt_dir):
        print(f"[-] 目录不存在: {txt_dir}")
        return
    
    print("\n[1] 读取文件...")
    all_data = read_all_channels(txt_dir)
    
    total_raw = 0
    for operator, provinces in all_data.items():
        for province, channels in provinces.items():
            total_raw += len(channels)
    print(f"    共读取 {total_raw} 个频道")
    
    if total_raw == 0:
        print("[-] 没有找到频道")
        return
    
    save_merge_files_with_genre(txt_dir, m3u_dir, all_data)
    
    if not KEEP_ORIGIN_FILES:
        delete_origin_files(txt_dir, m3u_dir)
    
    print(f"\n[+] 全部完成！")


if __name__ == '__main__':
    main()
