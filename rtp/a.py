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

# 名称替换规则（按顺序执行）
CHANNEL_REPLACE_RULES = [
    # ========== 4K 处理 ==========
    (r'^4K[\s_\-]*(.+)$', r'\1 4K'),
    (r'^(.+?)4K$', r'\1 4K'),
    (r'(.+?)4K[\s_\-](.+)$', r'\1\2 4K'),
    
    # ========== HD/SD 处理 ==========
    (r'^HD[\s_\-]*(.+)$', r'\1 HD'),
    (r'^(.+?)HD$', r'\1 HD'),
    (r'(.+?)HD[\s_\-](.+)$', r'\1\2 HD'),
    (r'高清', 'HD'),
    (r'^SD[\s_\-]*(.+)$', r'\1 SD'),
    (r'^(.+?)SD$', r'\1 SD'),
    (r'(.+?)SD[\s_\-](.+)$', r'\1\2 SD'),
    
    # ========== CCTV 系列（统一格式）==========
    # CCTV1 各种写法 -> CCTV1
    (r'[Cc][Cc][Tt][Vv][-\s]*1[-\s]*[Hh][Dd]?', 'CCTV1'),
    (r'[Cc][Cc][Tt][Vv][-\s]*1[-\s]*[Ss][Dd]?', 'CCTV1'),
    (r'[Cc][Cc][Tt][Vv][-\s]*1[-\s]*综合', 'CCTV1'),
    (r'[Cc][Cc][Tt][Vv]1[-\s]*', 'CCTV1'),
    
    # CCTV2
    (r'[Cc][Cc][Tt][Vv][-\s]*2[-\s]*[Hh][Dd]?', 'CCTV2'),
    (r'[Cc][Cc][Tt][Vv][-\s]*2[-\s]*[Ss][Dd]?', 'CCTV2'),
    (r'[Cc][Cc][Tt][Vv]2[-\s]*', 'CCTV2'),
    
    # CCTV3
    (r'[Cc][Cc][Tt][Vv][-\s]*3[-\s]*[Hh][Dd]?', 'CCTV3'),
    (r'[Cc][Cc][Tt][Vv][-\s]*3[-\s]*[Ss][Dd]?', 'CCTV3'),
    (r'[Cc][Cc][Tt][Vv]3[-\s]*', 'CCTV3'),
    
    # CCTV4
    (r'[Cc][Cc][Tt][Vv][-\s]*4[-\s]*[Hh][Dd]?', 'CCTV4'),
    (r'[Cc][Cc][Tt][Vv][-\s]*4[-\s]*[Ss][Dd]?', 'CCTV4'),
    (r'[Cc][Cc][Tt][Vv]4[-\s]*', 'CCTV4'),
    
    # CCTV5
    (r'[Cc][Cc][Tt][Vv][-\s]*5[-\s]*[Hh][Dd]?', 'CCTV5'),
    (r'[Cc][Cc][Tt][Vv][-\s]*5[-\s]*[Ss][Dd]?', 'CCTV5'),
    (r'[Cc][Cc][Tt][Vv]5[-\s]*', 'CCTV5'),
    (r'[Cc][Cc][Tt][Vv]5\+', 'CCTV5+'),
    
    # CCTV6
    (r'[Cc][Cc][Tt][Vv][-\s]*6[-\s]*[Hh][Dd]?', 'CCTV6'),
    (r'[Cc][Cc][Tt][Vv][-\s]*6[-\s]*[Ss][Dd]?', 'CCTV6'),
    (r'[Cc][Cc][Tt][Vv]6[-\s]*', 'CCTV6'),
    
    # CCTV7
    (r'[Cc][Cc][Tt][Vv][-\s]*7[-\s]*[Hh][Dd]?', 'CCTV7'),
    (r'[Cc][Cc][Tt][Vv][-\s]*7[-\s]*[Ss][Dd]?', 'CCTV7'),
    (r'[Cc][Cc][Tt][Vv]7[-\s]*', 'CCTV7'),
    
    # CCTV8
    (r'[Cc][Cc][Tt][Vv][-\s]*8[-\s]*[Hh][Dd]?', 'CCTV8'),
    (r'[Cc][Cc][Tt][Vv][-\s]*8[-\s]*[Ss][Dd]?', 'CCTV8'),
    (r'[Cc][Cc][Tt][Vv]8[-\s]*', 'CCTV8'),
    
    # CCTV9
    (r'[Cc][Cc][Tt][Vv][-\s]*9[-\s]*[Hh][Dd]?', 'CCTV9'),
    (r'[Cc][Cc][Tt][Vv][-\s]*9[-\s]*[Ss][Dd]?', 'CCTV9'),
    (r'[Cc][Cc][Tt][Vv]9[-\s]*', 'CCTV9'),
    
    # CCTV10
    (r'[Cc][Cc][Tt][Vv][-\s]*10[-\s]*[Hh][Dd]?', 'CCTV10'),
    (r'[Cc][Cc][Tt][Vv][-\s]*10[-\s]*[Ss][Dd]?', 'CCTV10'),
    (r'[Cc][Cc][Tt][Vv]10[-\s]*', 'CCTV10'),
    
    # CCTV11
    (r'[Cc][Cc][Tt][Vv][-\s]*11[-\s]*[Hh][Dd]?', 'CCTV11'),
    (r'[Cc][Cc][Tt][Vv][-\s]*11[-\s]*[Ss][Dd]?', 'CCTV11'),
    (r'[Cc][Cc][Tt][Vv]11[-\s]*', 'CCTV11'),
    
    # CCTV12
    (r'[Cc][Cc][Tt][Vv][-\s]*12[-\s]*[Hh][Dd]?', 'CCTV12'),
    (r'[Cc][Cc][Tt][Vv][-\s]*12[-\s]*[Ss][Dd]?', 'CCTV12'),
    (r'[Cc][Cc][Tt][Vv]12[-\s]*', 'CCTV12'),
    
    # CCTV13
    (r'[Cc][Cc][Tt][Vv][-\s]*13[-\s]*[Hh][Dd]?', 'CCTV13'),
    (r'[Cc][Cc][Tt][Vv][-\s]*13[-\s]*[Ss][Dd]?', 'CCTV13'),
    (r'[Cc][Cc][Tt][Vv]13[-\s]*', 'CCTV13'),
    
    # CCTV14
    (r'[Cc][Cc][Tt][Vv][-\s]*14[-\s]*[Hh][Dd]?', 'CCTV14'),
    (r'[Cc][Cc][Tt][Vv][-\s]*14[-\s]*[Ss][Dd]?', 'CCTV14'),
    (r'[Cc][Cc][Tt][Vv]14[-\s]*', 'CCTV14'),
    
    # CCTV15
    (r'[Cc][Cc][Tt][Vv][-\s]*15[-\s]*[Hh][Dd]?', 'CCTV15'),
    (r'[Cc][Cc][Tt][Vv][-\s]*15[-\s]*[Ss][Dd]?', 'CCTV15'),
    (r'[Cc][Cc][Tt][Vv]15[-\s]*', 'CCTV15'),
    
    # CCTV16
    (r'[Cc][Cc][Tt][Vv][-\s]*16[-\s]*[Hh][Dd]?', 'CCTV16'),
    (r'[Cc][Cc][Tt][Vv][-\s]*16[-\s]*[Ss][Dd]?', 'CCTV16'),
    (r'[Cc][Cc][Tt][Vv]16[-\s]*', 'CCTV16'),
    
    # CCTV17
    (r'[Cc][Cc][Tt][Vv][-\s]*17[-\s]*[Hh][Dd]?', 'CCTV17'),
    (r'[Cc][Cc][Tt][Vv][-\s]*17[-\s]*[Ss][Dd]?', 'CCTV17'),
    (r'[Cc][Cc][Tt][Vv]17[-\s]*', 'CCTV17'),
    
    # CCTV其他（数字+）
    (r'[Cc][Cc][Tt][Vv][-\s]*(\d+)[-\s]*\+', r'CCTV\1+'),
    (r'[Cc][Cc][Tt][Vv][-\s]*(\d+)[-\s]*[Hh][Dd]', r'CCTV\1'),
    (r'[Cc][Cc][Tt][Vv][-\s]*(\d+)[-\s]*[Ss][Dd]', r'CCTV\1'),
    (r'[Cc][Cc][Tt][Vv][-\s]*(\d+)', r'CCTV\1'),
    (r'[Cc][Cc][Tt][Vv](\d+)', r'CCTV\1'),
    
    # CETV 系列
    (r'[Cc][Ee][Tt][Vv](\d+)', r'CETV\1'),
    
    # CGTN 系列
    (r'[Cc][Gg][Tt][Nn]', r'CGTN'),
    
    # ========== 卫视系列（统一格式）==========
    # 北京卫视
    (r'北京卫视[-\s]*[Hh][Dd]?', '北京卫视'),
    (r'北京卫视[-\s]*[Ss][Dd]?', '北京卫视'),
    (r'北京卫视高清', '北京卫视'),
    (r'北京卫视HD', '北京卫视'),
    
    # 湖南卫视
    (r'湖南卫视[-\s]*[Hh][Dd]?', '湖南卫视'),
    (r'湖南卫视[-\s]*[Ss][Dd]?', '湖南卫视'),
    (r'湖南卫视高清', '湖南卫视'),
    (r'湖南卫视HD', '湖南卫视'),
    
    # 浙江卫视
    (r'浙江卫视[-\s]*[Hh][Dd]?', '浙江卫视'),
    (r'浙江卫视[-\s]*[Ss][Dd]?', '浙江卫视'),
    (r'浙江卫视高清', '浙江卫视'),
    (r'浙江卫视HD', '浙江卫视'),
    
    # 江苏卫视
    (r'江苏卫视[-\s]*[Hh][Dd]?', '江苏卫视'),
    (r'江苏卫视[-\s]*[Ss][Dd]?', '江苏卫视'),
    (r'江苏卫视高清', '江苏卫视'),
    (r'江苏卫视HD', '江苏卫视'),
    
    # 东方卫视
    (r'东方卫视[-\s]*[Hh][Dd]?', '东方卫视'),
    (r'东方卫视[-\s]*[Ss][Dd]?', '东方卫视'),
    (r'东方卫视高清', '东方卫视'),
    (r'东方卫视HD', '东方卫视'),
    
    # 广东卫视
    (r'广东卫视[-\s]*[Hh][Dd]?', '广东卫视'),
    (r'广东卫视[-\s]*[Ss][Dd]?', '广东卫视'),
    (r'广东卫视高清', '广东卫视'),
    (r'广东卫视HD', '广东卫视'),
    
    # 深圳卫视
    (r'深圳卫视[-\s]*[Hh][Dd]?', '深圳卫视'),
    (r'深圳卫视[-\s]*[Ss][Dd]?', '深圳卫视'),
    (r'深圳卫视高清', '深圳卫视'),
    (r'深圳卫视HD', '深圳卫视'),
    
    # 山东卫视
    (r'山东卫视[-\s]*[Hh][Dd]?', '山东卫视'),
    (r'山东卫视[-\s]*[Ss][Dd]?', '山东卫视'),
    (r'山东卫视高清', '山东卫视'),
    (r'山东卫视HD', '山东卫视'),
    
    # 天津卫视
    (r'天津卫视[-\s]*[Hh][Dd]?', '天津卫视'),
    (r'天津卫视[-\s]*[Ss][Dd]?', '天津卫视'),
    (r'天津卫视高清', '天津卫视'),
    (r'天津卫视HD', '天津卫视'),
    
    # 四川卫视
    (r'四川卫视[-\s]*[Hh][Dd]?', '四川卫视'),
    (r'四川卫视[-\s]*[Ss][Dd]?', '四川卫视'),
    (r'四川卫视高清', '四川卫视'),
    (r'四川卫视HD', '四川卫视'),
    
    # 湖北卫视
    (r'湖北卫视[-\s]*[Hh][Dd]?', '湖北卫视'),
    (r'湖北卫视[-\s]*[Ss][Dd]?', '湖北卫视'),
    (r'湖北卫视高清', '湖北卫视'),
    (r'湖北卫视HD', '湖北卫视'),
    
    # 安徽卫视
    (r'安徽卫视[-\s]*[Hh][Dd]?', '安徽卫视'),
    (r'安徽卫视[-\s]*[Ss][Dd]?', '安徽卫视'),
    (r'安徽卫视高清', '安徽卫视'),
    (r'安徽卫视HD', '安徽卫视'),
    
    # 江西卫视
    (r'江西卫视[-\s]*[Hh][Dd]?', '江西卫视'),
    (r'江西卫视[-\s]*[Ss][Dd]?', '江西卫视'),
    (r'江西卫视高清', '江西卫视'),
    (r'江西卫视HD', '江西卫视'),
    
    # 河南卫视
    (r'河南卫视[-\s]*[Hh][Dd]?', '河南卫视'),
    (r'河南卫视[-\s]*[Ss][Dd]?', '河南卫视'),
    (r'河南卫视高清', '河南卫视'),
    (r'河南卫视HD', '河南卫视'),
    
    # 河北卫视
    (r'河北卫视[-\s]*[Hh][Dd]?', '河北卫视'),
    (r'河北卫视[-\s]*[Ss][Dd]?', '河北卫视'),
    (r'河北卫视高清', '河北卫视'),
    (r'河北卫视HD', '河北卫视'),
    
    # 辽宁卫视
    (r'辽宁卫视[-\s]*[Hh][Dd]?', '辽宁卫视'),
    (r'辽宁卫视[-\s]*[Ss][Dd]?', '辽宁卫视'),
    (r'辽宁卫视高清', '辽宁卫视'),
    (r'辽宁卫视HD', '辽宁卫视'),
    
    # 黑龙江卫视
    (r'黑龙江卫视[-\s]*[Hh][Dd]?', '黑龙江卫视'),
    (r'黑龙江卫视[-\s]*[Ss][Dd]?', '黑龙江卫视'),
    (r'黑龙江卫视高清', '黑龙江卫视'),
    (r'黑龙江卫视HD', '黑龙江卫视'),
    
    # 吉林卫视
    (r'吉林卫视[-\s]*[Hh][Dd]?', '吉林卫视'),
    (r'吉林卫视[-\s]*[Ss][Dd]?', '吉林卫视'),
    (r'吉林卫视高清', '吉林卫视'),
    (r'吉林卫视HD', '吉林卫视'),
    
    # 贵州卫视
    (r'贵州卫视[-\s]*[Hh][Dd]?', '贵州卫视'),
    (r'贵州卫视[-\s]*[Ss][Dd]?', '贵州卫视'),
    (r'贵州卫视高清', '贵州卫视'),
    (r'贵州卫视HD', '贵州卫视'),
    
    # 云南卫视
    (r'云南卫视[-\s]*[Hh][Dd]?', '云南卫视'),
    (r'云南卫视[-\s]*[Ss][Dd]?', '云南卫视'),
    (r'云南卫视高清', '云南卫视'),
    (r'云南卫视HD', '云南卫视'),
    
    # 广西卫视
    (r'广西卫视[-\s]*[Hh][Dd]?', '广西卫视'),
    (r'广西卫视[-\s]*[Ss][Dd]?', '广西卫视'),
    (r'广西卫视高清', '广西卫视'),
    (r'广西卫视HD', '广西卫视'),
    
    # 陕西卫视
    (r'陕西卫视[-\s]*[Hh][Dd]?', '陕西卫视'),
    (r'陕西卫视[-\s]*[Ss][Dd]?', '陕西卫视'),
    (r'陕西卫视高清', '陕西卫视'),
    (r'陕西卫视HD', '陕西卫视'),
    
    # 甘肃卫视
    (r'甘肃卫视[-\s]*[Hh][Dd]?', '甘肃卫视'),
    (r'甘肃卫视[-\s]*[Ss][Dd]?', '甘肃卫视'),
    (r'甘肃卫视高清', '甘肃卫视'),
    (r'甘肃卫视HD', '甘肃卫视'),
    
    # 宁夏卫视
    (r'宁夏卫视[-\s]*[Hh][Dd]?', '宁夏卫视'),
    (r'宁夏卫视[-\s]*[Ss][Dd]?', '宁夏卫视'),
    (r'宁夏卫视高清', '宁夏卫视'),
    (r'宁夏卫视HD', '宁夏卫视'),
    
    # 青海卫视
    (r'青海卫视[-\s]*[Hh][Dd]?', '青海卫视'),
    (r'青海卫视[-\s]*[Ss][Dd]?', '青海卫视'),
    (r'青海卫视高清', '青海卫视'),
    (r'青海卫视HD', '青海卫视'),
    
    # 新疆卫视
    (r'新疆卫视[-\s]*[Hh][Dd]?', '新疆卫视'),
    (r'新疆卫视[-\s]*[Ss][Dd]?', '新疆卫视'),
    (r'新疆卫视高清', '新疆卫视'),
    (r'新疆卫视HD', '新疆卫视'),
    
    # 西藏卫视
    (r'西藏卫视[-\s]*[Hh][Dd]?', '西藏卫视'),
    (r'西藏卫视[-\s]*[Ss][Dd]?', '西藏卫视'),
    (r'西藏卫视高清', '西藏卫视'),
    (r'西藏卫视HD', '西藏卫视'),
    
    # 内蒙古卫视
    (r'内蒙古卫视[-\s]*[Hh][Dd]?', '内蒙古卫视'),
    (r'内蒙古卫视[-\s]*[Ss][Dd]?', '内蒙古卫视'),
    (r'内蒙古卫视高清', '内蒙古卫视'),
    (r'内蒙古卫视HD', '内蒙古卫视'),
    
    # 山西卫视
    (r'山西卫视[-\s]*[Hh][Dd]?', '山西卫视'),
    (r'山西卫视[-\s]*[Ss][Dd]?', '山西卫视'),
    (r'山西卫视高清', '山西卫视'),
    (r'山西卫视HD', '山西卫视'),
    
    # 东南卫视
    (r'东南卫视[-\s]*[Hh][Dd]?', '东南卫视'),
    (r'东南卫视[-\s]*[Ss][Dd]?', '东南卫视'),
    (r'东南卫视高清', '东南卫视'),
    (r'东南卫视HD', '东南卫视'),
    
    # 旅游卫视
    (r'旅游卫视[-\s]*[Hh][Dd]?', '旅游卫视'),
    (r'旅游卫视[-\s]*[Ss][Dd]?', '旅游卫视'),
    (r'旅游卫视高清', '旅游卫视'),
    (r'旅游卫视HD', '旅游卫视'),
    
    # 兵团卫视
    (r'兵团卫视[-\s]*[Hh][Dd]?', '兵团卫视'),
    (r'兵团卫视[-\s]*[Ss][Dd]?', '兵团卫视'),
    
    # 金鹰卡通
    (r'金鹰卡通[-\s]*[Hh][Dd]?', '金鹰卡通'),
    (r'金鹰卡通[-\s]*[Ss][Dd]?', '金鹰卡通'),
    
    # 卡酷少儿
    (r'卡酷少儿[-\s]*[Hh][Dd]?', '卡酷少儿'),
    (r'卡酷少儿[-\s]*[Ss][Dd]?', '卡酷少儿'),
    
    # 山东教育卫视
    (r'山东教育卫视[-\s]*[Hh][Dd]?', '山东教育卫视'),
    (r'山东教育卫视[-\s]*[Ss][Dd]?', '山东教育卫视'),
    
    # 其他频道
    (r'CETV(\d+)', r'CETV\1'),
    (r'CHC([^,]*)', r'CHC\1'),
    
    # 统一大小写和格式
    (r'[Hh][Dd]', 'HD'),
    (r'[Ss][Dd]', 'SD'),
    (r'高清', 'HD'),
    (r'标清', 'SD'),
    
    # 清理多余空格
    (r'\s+', ' '),
    (r'^\s+', ''),
    (r'\s+$', ''),
]

MERGE_FILE_NAMES = {
    "电信": "电信组播",
    "联通": "联通组播",
    "移动": "移动组播",
    "广电": "广电组播",
    "未知": "其他组播",
}

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
    
    # 去除多余空格
    result = ' '.join(result.split())
    return result


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


def save_merge_files(txt_dir, m3u_dir, all_data):
    """保存合并文件"""
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
        if _4k_provinces:
            file_name = f"{operator}4K组播"
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
        keep += [f"{name}4K组播.txt" for name in MERGE_FILE_NAMES.values() if name != "其他组播"]
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
