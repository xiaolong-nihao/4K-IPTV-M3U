#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测速合并模块 - 调用 iptv_crawler.py 生成的文件进行测速和合并
使用方法: python merge_speedtest.py
"""

import os
import re
import time
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from urllib.parse import quote

# ================= 配置区域 =================
# 原文件生成的目录（相对于当前脚本）
SOURCE_TXT_DIR = "txt"      # 原文件生成的txt目录
SOURCE_M3U_DIR = "m3u"      # 原文件生成的m3u目录

# 测速配置
SPEEDTEST_TIMEOUT = 5        # 测速超时时间(秒)
SPEEDTEST_THREADS = 10       # 并发测速线程数
SPEEDTEST_CACHE_HOST = True  # 相同Host地址共享测速结果
SPEEDTEST_MAX_PER_SERVER = 3 # 每个服务器最多测试N个频道

# 合并文件配置
ENABLE_MERGE = True          # 是否启用合并文件功能

# 每个频道最多保留几个源（去重，只保留速度最快的）
MAX_SOURCES_PER_CHANNEL = 2

# 每个运营商最多保留多少个频道（0=不限制）
MAX_CHANNELS_PER_OPERATOR = 300

# 合并文件是否按速度排序
MERGE_SORT_BY_SPEED = True

# 合并文件名（可以随便改）
MERGE_FILE_NAMES = {
    "电信": "ChinaTelecom",
    "联通": "ChinaUnicom",
    "移动": "ChinaMobile",
    "广电": "ChinaBroadcast",
    "未知": "Other",
}

# 是否保留原文件（True=保留 / False=删除原文件只保留合并文件）
KEEP_ORIGIN_FILES = True

# EPG地址（用于M3U文件）
EPG_URL = "http://epg.51zmt.top:8000/e.xml.gz"
TVG_LOGO_BASE_URL = "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/"
# ============================================


class SpeedTester:
    """测速器"""
    
    def __init__(self, timeout=5, max_workers=10, cache_host=True, max_test_per_server=3):
        self.timeout = timeout
        self.max_workers = max_workers
        self.cache_host = cache_host
        self.max_test_per_server = max_test_per_server
        self.host_cache = {}
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    def _extract_host(self, url):
        try:
            if url.startswith(('rtp://', 'udp://', 'igmp://')):
                match = re.search(r'://([0-9.]+):(\d+)', url)
                if match:
                    return f"{match.group(1)}:{match.group(2)}"
            if '://' in url:
                return url.split('://')[1].split('/')[0].split(':')[0]
            return url
        except:
            return url
    
    def _test_url(self, url):
        start = time.time()
        try:
            if url.startswith(('rtp://', 'udp://', 'igmp://')):
                import socket
                match = re.search(r'://([0-9.]+):(\d+)', url)
                if match:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(self.timeout)
                    try:
                        sock.sendto(b'test', (match.group(1), int(match.group(2))))
                        sock.close()
                        return True, (time.time() - start) * 1000
                    except:
                        sock.close()
                        return False, 0
                return False, 0
            resp = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code in [200, 206, 302, 301]:
                return True, (time.time() - start) * 1000
            return False, 0
        except:
            return False, 0
    
    def test_channel(self, name, url):
        host = self._extract_host(url)
        if self.cache_host and host in self.host_cache:
            return self.host_cache[host]
        alive, speed = self._test_url(url)
        if self.cache_host:
            self.host_cache[host] = (alive, speed)
        return alive, speed
    
    def filter_channels(self, channels):
        if not channels:
            return []
        server_channels = defaultdict(list)
        for name, url in channels:
            server_channels[self._extract_host(url)].append((name, url))
        
        alive_servers = {}
        for host, chs in server_channels.items():
            for i in range(min(len(chs), self.max_test_per_server)):
                name, url = chs[i]
                alive, speed = self.test_channel(name, url)
                if alive:
                    alive_servers[host] = speed
                    break
        
        result = []
        for host, chs in server_channels.items():
            if host in alive_servers:
                for name, url in chs:
                    _, speed = self.test_channel(name, url)
                    result.append((name, url, speed))
        result.sort(key=lambda x: x[2])
        return result


def build_tvg_logo_url(channel_name):
    safe_name = quote(channel_name.strip(), safe="")
    return f"{TVG_LOGO_BASE_URL}{safe_name}.png"


def deduplicate_channels(channels, max_per_channel=2):
    """按频道名去重，每个频道只保留速度最快的N个"""
    if not channels:
        return []
    groups = defaultdict(list)
    for name, url, speed in channels:
        groups[name].append((name, url, speed))
    result = []
    for name, sources in groups.items():
        sources.sort(key=lambda x: x[2])
        result.extend(sources[:max_per_channel])
        if len(sources) > max_per_channel:
            print(f"    [去重] {name}: {len(sources)}个源 → 保留最快的{max_per_channel}个")
    result.sort(key=lambda x: x[2])
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
        if not file.endswith('.txt'):
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


def save_merge_files(txt_output_dir, m3u_output_dir, all_channels):
    """保存合并文件到 output 目录"""
    print(f"\n{'='*50}")
    print(f"正在创建合并文件（目录: output）")
    print("="*50)
    
    # 创建 output 目录
    txt_merge_dir = os.path.join(txt_output_dir, "output")
    m3u_merge_dir = os.path.join(m3u_output_dir, "output")
    os.makedirs(txt_merge_dir, exist_ok=True)
    os.makedirs(m3u_merge_dir, exist_ok=True)
    
    total_count = 0
    for operator, channels in all_channels.items():
        if not channels:
            print(f"[-] {operator}: 没有频道")
            continue
        
        # 按频道名去重
        channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
        
        # 限制总数量
        if MAX_CHANNELS_PER_OPERATOR > 0 and len(channels) > MAX_CHANNELS_PER_OPERATOR:
            channels = channels[:MAX_CHANNELS_PER_OPERATOR]
            print(f"  [限制] {operator}: 限制为 {MAX_CHANNELS_PER_OPERATOR} 个频道")
        
        # 按速度排序
        if MERGE_SORT_BY_SPEED:
            channels.sort(key=lambda x: x[2])
        
        # 获取文件名
        file_name = MERGE_FILE_NAMES.get(operator, operator)
        
        # 保存TXT
        txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            for name, url, speed in channels:
                f.write(f"{name},{url}\n")
        
        # 保存M3U
        m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
        with open(m3u_path, 'w', encoding='utf-8') as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            for name, url, speed in channels:
                speed_str = f" [{speed:.0f}ms]" if speed > 0 else ""
                f.write(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{operator}",{name}{speed_str}\n{url}\n')
        
        print(f"  ✓ {operator}: {len(channels)} 个频道 -> output/{file_name}")
        total_count += len(channels)
    
    print(f"\n[+] 合并完成，共 {total_count} 个频道")


def delete_origin_files(txt_dir, m3u_dir):
    """删除原文件（只保留合并文件）"""
    print("\n[*] 删除原文件...")
    
    # 要保留的文件名
    keep_txt = [f"{name}.txt" for name in MERGE_FILE_NAMES.values()]
    keep_m3u = [f"{name}.m3u" for name in MERGE_FILE_NAMES.values()]
    
    # 删除txt目录中的原文件
    if os.path.exists(txt_dir):
        for file in os.listdir(txt_dir):
            if file.endswith('.txt') and file not in keep_txt and file != "output":
                os.remove(os.path.join(txt_dir, file))
                print(f"  删除: txt/{file}")
    
    # 删除m3u目录中的原文件
    if os.path.exists(m3u_dir):
        for file in os.listdir(m3u_dir):
            if file.endswith('.m3u') and file not in keep_m3u and file != "output":
                os.remove(os.path.join(m3u_dir, file))
                print(f"  删除: m3u/{file}")


def main():
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    txt_dir = os.path.join(script_dir, SOURCE_TXT_DIR)
    m3u_dir = os.path.join(script_dir, SOURCE_M3U_DIR)
    
    print(f"\n{'='*50}")
    print(f"测速合并工具")
    print(f"TXT目录: {txt_dir}")
    print(f"M3U目录: {m3u_dir}")
    print(f"{'='*50}")
    
    # 1. 读取所有频道
    print("\n[1] 读取原文件...")
    all_channels = read_all_channels(txt_dir)
    
    total_raw = sum(len(v) for v in all_channels.values())
    print(f"    共读取 {total_raw} 个频道")
    for op, chs in all_channels.items():
        if chs:
            print(f"    - {op}: {len(chs)} 个")
    
    if total_raw == 0:
        print("[-] 没有找到任何频道，请先运行 iptv_crawler.py")
        return
    
    # 2. 测速
    print("\n[2] 开始测速...")
    tester = SpeedTester(
        timeout=SPEEDTEST_TIMEOUT,
        max_workers=SPEEDTEST_THREADS,
        cache_host=SPEEDTEST_CACHE_HOST,
        max_test_per_server=SPEEDTEST_MAX_PER_SERVER
    )
    
    for operator in all_channels:
        if all_channels[operator]:
            print(f"\n  [{operator}] 测速中...")
            all_channels[operator] = tester.filter_channels([(n, u) for n, u in all_channels[operator]])
            print(f"    存活: {len(all_channels[operator])} 个")
    
    # 3. 保存合并文件
    if ENABLE_MERGE:
        save_merge_files(txt_dir, m3u_dir, all_channels)
    
    # 4. 删除原文件（如果不保留）
    if not KEEP_ORIGIN_FILES:
        delete_origin_files(txt_dir, m3u_dir)
    
    print(f"\n[+] 全部完成！")


if __name__ == '__main__':
    main()
