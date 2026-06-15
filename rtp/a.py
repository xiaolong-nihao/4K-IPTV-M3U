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
MAX_SOURCES_PER_CHANNEL = 5       # 每个频道保留几个源
MAX_CHANNELS_PER_OPERATOR = 0     # 每个运营商最多频道数（0=不限制）

# ========== 输出开关（True=生成，False=不生成）==========
ENABLE_OPERATOR_FILES = True      # 是否生成运营商分开的文件（普通频道）
ENABLE_4K_FILES = True            # 是否生成4K文件（按运营商分开）
ENABLE_CCTV_WS_FILES = True       # 是否生成央视卫视文件（按运营商分开）
ENABLE_OTHER_FILES = True         # 是否生成其他频道文件（按运营商分开）

# ========== 输出文件名配置 ==========
# 普通文件名（运营商分开）
OUTPUT_FILE_NAMES = {
    "电信": "CT",
    "联通": "CU",
    "移动": "CM",
    "广电": "CB",
    "未知": "OT",
}

# 4K文件名（运营商分开）
OUTPUT_4K_NAMES = {
    "电信": "CT4K",
    "联通": "CU4K",
    "移动": "CM4K",
    "广电": "CB4K",
    "未知": "OT4K",
}

# 央视卫视文件名（运营商分开）
OUTPUT_CCTV_WS_NAMES = {
    "电信": "CT_央视卫视",
    "联通": "CU_央视卫视",
    "移动": "CM_央视卫视",
    "广电": "CB_央视卫视",
    "未知": "OT_央视卫视",
}

# 其他频道文件名（运营商分开）
OUTPUT_OTHER_NAMES = {
    "电信": "CT_其他",
    "联通": "CU_其他",
    "移动": "CM_其他",
    "广电": "CB_其他",
    "未知": "OT_其他",
}

# 频道名称正则处理
ENABLE_CHANNEL_CLEAN = True

# 名称替换规则（按顺序执行）
CHANNEL_REPLACE_RULES = [
    # ========== 4K 处理 ==========
    (r'^4K[\s_\-]*(.+)$', r'\1 4K'),
    (r'^(.+?)4K$', r'\1 4K'),
    (r'(.+?)4K[\s_\-](.+)$', r'\1\2 4K'),
    
    # ========== HD/SD 处理（去掉标识）==========
    (r'^HD[\s_\-]*(.+)$', r'\1'),
    (r'^(.+?)HD$', r'\1'),
    (r'(.+?)HD[\s_\-](.+)$', r'\1\2'),
    (r'高清', ''),
    (r'^SD[\s_\-]*(.+)$', r'\1'),
    (r'^(.+?)SD$', r'\1'),
    (r'(.+?)SD[\s_\-](.+)$', r'\1\2'),
    
    # ========== CCTV 系列（统一格式）==========
    (r'[Cc][Cc][Tt][Vv][-\s]*1[-\s]*.*', 'CCTV1'),
    (r'[Cc][Cc][Tt][Vv][-\s]*2[-\s]*.*', 'CCTV2'),
    (r'[Cc][Cc][Tt][Vv][-\s]*3[-\s]*.*', 'CCTV3'),
    (r'[Cc][Cc][Tt][Vv][-\s]*4[-\s]*.*', 'CCTV4'),
    (r'[Cc][Cc][Tt][Vv][-\s]*5[-\s]*\+', 'CCTV5+'),
    (r'[Cc][Cc][Tt][Vv][-\s]*5[-\s]*.*', 'CCTV5'),
    (r'[Cc][Cc][Tt][Vv][-\s]*6[-\s]*.*', 'CCTV6'),
    (r'[Cc][Cc][Tt][Vv][-\s]*7[-\s]*.*', 'CCTV7'),
    (r'[Cc][Cc][Tt][Vv][-\s]*8[-\s]*.*', 'CCTV8'),
    (r'[Cc][Cc][Tt][Vv][-\s]*9[-\s]*.*', 'CCTV9'),
    (r'[Cc][Cc][Tt][Vv][-\s]*10[-\s]*.*', 'CCTV10'),
    (r'[Cc][Cc][Tt][Vv][-\s]*11[-\s]*.*', 'CCTV11'),
    (r'[Cc][Cc][Tt][Vv][-\s]*12[-\s]*.*', 'CCTV12'),
    (r'[Cc][Cc][Tt][Vv][-\s]*13[-\s]*.*', 'CCTV13'),
    (r'[Cc][Cc][Tt][Vv][-\s]*14[-\s]*.*', 'CCTV14'),
    (r'[Cc][Cc][Tt][Vv][-\s]*15[-\s]*.*', 'CCTV15'),
    (r'[Cc][Cc][Tt][Vv][-\s]*16[-\s]*.*', 'CCTV16'),
    (r'[Cc][Cc][Tt][Vv][-\s]*17[-\s]*.*', 'CCTV17'),
    
    # CETV 系列
    (r'[Cc][Ee][Tt][Vv](\d+)', r'CETV\1'),
    
    # CGTN 系列
    (r'[Cc][Gg][Tt][Nn]', r'CGTN'),
    
    # ========== 卫视系列（去掉HD/SD标识）==========
    (r'([^,]+)卫视[-\s]*[Hh][Dd]?', r'\1卫视'),
    (r'([^,]+)卫视[-\s]*[Ss][Dd]?', r'\1卫视'),
    (r'([^,]+)卫视高清', r'\1卫视'),
    
    # 清理多余空格和特殊字符
    (r'\s+', ' '),
    (r'^\s+', ''),
    (r'\s+$', ''),
]

# 央视和卫视关键词列表（用于分类）
CCTV_KEYWORDS = ['CCTV', 'CETV', 'CGTN']
WS_KEYWORDS = ['卫视']

KEEP_ORIGIN_FILES = True
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"

PROVINCES = ["北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海",
             "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
             "广东", "广西", "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西",
             "甘肃", "青海", "宁夏", "新疆"]

OPERATORS = ["电信", "联通", "移动", "广电"]
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


def is_cctv_ws_channel(name):
    """判断是否是央视或卫视频道"""
    for kw in CCTV_KEYWORDS:
        if kw in name:
            return True
    for kw in WS_KEYWORDS:
        if kw in name:
            return True
    return False


def parse_filename_info(filename):
    """从文件名解析省份和运营商"""
    province = None
    operator = None
    
    for p in PROVINCES:
        if p in filename:
            province = p
            break
    
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
    """读取所有txt文件中的频道"""
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


def save_operator_files(txt_merge_dir, m3u_merge_dir, provinces_data, operator, file_name, type_name, total_count):
    """通用保存函数"""
    txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
    m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
    
    if os.path.exists(txt_path):
        os.remove(txt_path)
    if os.path.exists(m3u_path):
        os.remove(m3u_path)
    
    txt_lines = []
    m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
    
    for province in sorted(provinces_data.keys()):
        channels = provinces_data[province]
        if not channels:
            continue
        
        channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
        
        if MAX_CHANNELS_PER_OPERATOR > 0 and len(channels) > MAX_CHANNELS_PER_OPERATOR:
            channels = channels[:MAX_CHANNELS_PER_OPERATOR]
        
        if not channels:
            continue
        
        group_name = f"{province}{type_name}"
        txt_lines.append(f"{group_name},#genre#")
        m3u_lines.append(f'#EXTINF:-1 group-title="{group_name}",{group_name}')
        
        for name, url in channels:
            txt_lines.append(f"{name},{url}")
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{group_name}",{name}')
            m3u_lines.append(url)
        
        print(f"  [{operator} {type_name}] {province}: {len(channels)} 个频道")
        total_count[0] += len(channels)
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(txt_lines))
    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_lines))
    
    print(f"  ✓ {operator} {type_name}: 已保存 -> output/{file_name}")
    return total_count


def save_merge_files(txt_dir, m3u_dir, all_data):
    """保存合并文件"""
    print(f"\n{'='*50}")
    print(f"正在创建合并文件（目录: output）")
    print("="*50)
    
    txt_merge_dir = os.path.join(txt_dir, "output")
    m3u_merge_dir = os.path.join(m3u_dir, "output")
    
    os.makedirs(txt_merge_dir, exist_ok=True)
    os.makedirs(m3u_merge_dir, exist_ok=True)
    
    total_count = [0]
    
    # 收集各类数据
    normal_data = {op: defaultdict(list) for op in OPERATORS + ["未知"]}
    _4k_data = {op: defaultdict(list) for op in OPERATORS + ["未知"]}
    cctv_ws_data = {op: defaultdict(list) for op in OPERATORS + ["未知"]}
    other_data = {op: defaultdict(list) for op in OPERATORS + ["未知"]}
    
    for operator, provinces_data in all_data.items():
        if not provinces_data:
            continue
        
        for province, channels in provinces_data.items():
            for name, url in channels:
                if is_4k_channel(name):
                    _4k_data[operator][province].append((name, url))
                elif is_cctv_ws_channel(name):
                    cctv_ws_data[operator][province].append((name, url))
                else:
                    other_data[operator][province].append((name, url))
                
                # 普通文件（所有非4K频道）
                if not is_4k_channel(name):
                    normal_data[operator][province].append((name, url))
    
    # 保存普通文件
    if ENABLE_OPERATOR_FILES:
        for operator, provinces_data in normal_data.items():
            if provinces_data:
                file_name = OUTPUT_FILE_NAMES.get(operator, operator)
                save_operator_files(txt_merge_dir, m3u_merge_dir, provinces_data, operator, file_name, "组播", total_count)
    
    # 保存4K文件
    if ENABLE_4K_FILES:
        for operator, provinces_data in _4k_data.items():
            if provinces_data:
                file_name = OUTPUT_4K_NAMES.get(operator, f"{operator}4K")
                save_operator_files(txt_merge_dir, m3u_merge_dir, provinces_data, operator, file_name, "4K组播", total_count)
    
    # 保存央视卫视文件
    if ENABLE_CCTV_WS_FILES:
        for operator, provinces_data in cctv_ws_data.items():
            if provinces_data:
                file_name = OUTPUT_CCTV_WS_NAMES.get(operator, f"{operator}_央视卫视")
                save_operator_files(txt_merge_dir, m3u_merge_dir, provinces_data, operator, file_name, "央视卫视", total_count)
    
    # 保存其他频道文件
    if ENABLE_OTHER_FILES:
        for operator, provinces_data in other_data.items():
            if provinces_data:
                file_name = OUTPUT_OTHER_NAMES.get(operator, f"{operator}_其他")
                save_operator_files(txt_merge_dir, m3u_merge_dir, provinces_data, operator, file_name, "其他", total_count)
    
    print(f"\n[+] 合并完成，共 {total_count[0]} 个频道")


def delete_origin_files(txt_dir, m3u_dir):
    """删除原文件"""
    if not KEEP_ORIGIN_FILES:
        print("\n[*] 删除原文件...")
        keep = [f"{name}.txt" for name in OUTPUT_FILE_NAMES.values()]
        keep += [f"{name}.txt" for name in OUTPUT_4K_NAMES.values()]
        keep += [f"{name}.txt" for name in OUTPUT_CCTV_WS_NAMES.values()]
        keep += [f"{name}.txt" for name in OUTPUT_OTHER_NAMES.values()]
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
    print(f"输出配置:")
    print(f"  普通文件: {'是' if ENABLE_OPERATOR_FILES else '否'}")
    print(f"  4K文件: {'是' if ENABLE_4K_FILES else '否'}")
    print(f"  央视卫视文件: {'是' if ENABLE_CCTV_WS_FILES else '否'}")
    print(f"  其他频道文件: {'是' if ENABLE_OTHER_FILES else '否'}")
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
    
    save_merge_files(txt_dir, m3u_dir, all_data)
    
    if not KEEP_ORIGIN_FILES:
        delete_origin_files(txt_dir, m3u_dir)
    
    print(f"\n[+] 全部完成！")


if __name__ == '__main__':
    main()
