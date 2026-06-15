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
MAX_SOURCES_PER_CHANNEL = 5       # 每个频道保留几个源（按文件顺序，取前N个）
MAX_CHANNELS_PER_OPERATOR = 500   # 每个运营商最多频道数

MERGE_FILE_NAMES = {
    "电信": "ChinaTelecom",
    "联通": "ChinaUnicom",
    "移动": "ChinaMobile",
    "广电": "ChinaBroadcast",
    "未知": "Other",
}

KEEP_ORIGIN_FILES = True
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
# ============================================


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
        # 保留前 max_per_channel 个
        result.extend(sources[:max_per_channel])
        if len(sources) > max_per_channel:
            print(f"    [去重] {name}: {len(sources)}个源 → 保留{max_per_channel}个")
    
    return result


def read_all_channels(txt_dir):
    """读取所有txt文件中的频道"""
    all_channels = {
        "电信": [],
        "联通": [],
        "移动": [],
        "广电": [],
        "未知": []
    }
    
    if not os.path.exists(txt_dir):
        print(f"[-] 目录不存在: {txt_dir}")
        return all_channels
    
    for file in os.listdir(txt_dir):
        if not file.endswith('.txt') or file == "output":
            continue
        
        file_path = os.path.join(txt_dir, file)
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                name, url = line.split(',', 1)
                
                # 判断运营商
                operator = "未知"
                for op in ["电信", "联通", "移动", "广电"]:
                    if op in file:
                        operator = op
                        break
                
                all_channels[operator].append((name.strip(), url.strip()))
    
    return all_channels


def save_merge_files(txt_dir, m3u_dir, all_channels):
    """保存合并文件到 output 目录"""
    print(f"\n{'='*50}")
    print(f"正在创建合并文件（目录: output）")
    print("="*50)
    
    txt_merge_dir = os.path.join(txt_dir, "output")
    m3u_merge_dir = os.path.join(m3u_dir, "output")
    os.makedirs(txt_merge_dir, exist_ok=True)
    os.makedirs(m3u_merge_dir, exist_ok=True)
    
    total_count = 0
    for operator, channels in all_channels.items():
        if not channels:
            continue
        
        # 去重
        channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
        
        # 限制数量
        if MAX_CHANNELS_PER_OPERATOR > 0 and len(channels) > MAX_CHANNELS_PER_OPERATOR:
            channels = channels[:MAX_CHANNELS_PER_OPERATOR]
            print(f"  [限制] {operator}: 限制为 {MAX_CHANNELS_PER_OPERATOR} 个频道")
        
        file_name = MERGE_FILE_NAMES.get(operator, operator)
        
        # 保存TXT
        txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            for name, url in channels:
                f.write(f"{name},{url}\n")
        
        # 保存M3U
        m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
        with open(m3u_path, 'w', encoding='utf-8') as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            for name, url in channels:
                f.write(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{operator}",{name}\n{url}\n')
        
        print(f"  ✓ {operator}: {len(channels)} 个频道 -> output/{file_name}")
        total_count += len(channels)
    
    print(f"\n[+] 合并完成，共 {total_count} 个频道")


def delete_origin_files(txt_dir, m3u_dir):
    """删除原文件"""
    if not KEEP_ORIGIN_FILES:
        print("\n[*] 删除原文件...")
        keep = [f"{name}.txt" for name in MERGE_FILE_NAMES.values()]
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
    print(f"TXT目录: {txt_dir}")
    print(f"{'='*50}")
    
    if not os.path.exists(txt_dir):
        print(f"[-] 目录不存在: {txt_dir}")
        return
    
    # 1. 读取频道
    print("\n[1] 读取文件...")
    all_channels = read_all_channels(txt_dir)
    total_raw = sum(len(v) for v in all_channels.values())
    print(f"    共读取 {total_raw} 个频道")
    for op, chs in all_channels.items():
        if chs:
            print(f"    - {op}: {len(chs)} 个")
    
    if total_raw == 0:
        print("[-] 没有找到频道")
        return
    
    # 2. 保存合并文件
    save_merge_files(txt_dir, m3u_dir, all_channels)
    
    # 3. 删除原文件
    if not KEEP_ORIGIN_FILES:
        delete_origin_files(txt_dir, m3u_dir)
    
    print(f"\n[+] 全部完成！")


if __name__ == '__main__':
    main()
