#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测速合并模块 - 读取 b.py 生成的文件进行测速和合并
运行方式：由 b.py 自动调用，也可单独运行 python a.py
"""

import os
import re
import time
import socket
import struct
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from urllib.parse import quote

# ================= 配置区域 =================
# 原文件生成的目录（相对于项目根目录）
SOURCE_TXT_DIR = "txt"
SOURCE_M3U_DIR = "m3u"

# 测速配置
SPEED_TEST_TIMEOUT = 5        # 测速超时时间(秒)
SPEED_TEST_THREADS = 10       # 并发测速线程数
MIN_SPEED_KBPS = 100          # 最低速度要求(Kbps)，低于此值过滤
DOWNLOAD_SIZE_KB = 64         # HTTP测速下载大小(KB)

# 服务器缓存配置（大幅减少测速时间）
SPEEDTEST_CACHE_HOST = True   # 相同Host地址共享测速结果（启用可减少90%测速时间）
SPEEDTEST_MAX_PER_SERVER = 3  # 每个服务器最多测试N个频道（判断服务器可用性）

# 合并文件配置
ENABLE_MERGE = True           # 是否启用合并文件
MAX_SOURCES_PER_CHANNEL = 3   # 每个频道最多保留几个源（去重，只保留速度最快的）
MAX_CHANNELS_PER_OPERATOR = 0  # 每个运营商最多保留多少个频道（0=不限制）
MERGE_SORT_BY_SPEED = True    # 合并文件是否按速度排序

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
    """增强版测速器 - 支持服务器缓存和真实测速"""
    
    def __init__(self, timeout=5, max_workers=10, min_speed=100, 
                 download_size=64, cache_host=True, max_test_per_server=3):
        self.timeout = timeout
        self.max_workers = max_workers
        self.min_speed_kbps = min_speed
        self.download_size = download_size * 1024
        self.cache_host = cache_host
        self.max_test_per_server = max_test_per_server
        self.host_cache = {}  # host -> (可用, 速度, 延迟)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_host(self, url):
        """提取Host地址用于缓存"""
        try:
            if url.startswith(('rtp://', 'udp://', 'igmp://')):
                match = re.search(r'://[@]?([0-9.]+):(\d+)', url)
                if match:
                    return f"{match.group(1)}:{match.group(2)}"
            if '://' in url:
                parts = url.split('://')[1]
                host = parts.split('/')[0].split(':')[0]
                return host
            return url
        except:
            return url
    
    def extract_host_port(self, url):
        """提取IP和端口"""
        try:
            if url.startswith(('rtp://', 'udp://', 'igmp://')):
                match = re.search(r'://[@]?([0-9.]+):(\d+)', url)
                if match:
                    return match.group(1), int(match.group(2))
            if '://' in url:
                parts = url.split('://')[1]
                host_port = parts.split('/')[0]
                if ':' in host_port:
                    host, port = host_port.split(':')
                    return host, int(port)
                return host_port, 80 if url.startswith('http://') else 443
        except:
            pass
        return None, None
    
    def test_http_channel(self, url):
        """测试HTTP/HTTPS流 - 下载数据计算真实速度"""
        start_time = time.time()
        try:
            head_resp = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            if head_resp.status_code not in [200, 206, 302, 301]:
                return False, 0, 0
            
            headers = {'Range': f'bytes=0-{self.download_size - 1}'}
            resp = self.session.get(url, timeout=self.timeout, stream=True, headers=headers)
            
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded >= self.download_size:
                    break
            
            elapsed = time.time() - start_time
            if elapsed < 0.001:
                elapsed = 0.001
            speed_kbps = (downloaded / 1024) / elapsed * 8
            resp.close()
            
            if speed_kbps >= self.min_speed_kbps:
                return True, speed_kbps, elapsed * 1000
            return False, speed_kbps, elapsed * 1000
        except Exception:
            return False, 0, 0
    
    def test_multicast_channel(self, url):
        """测试组播地址 - UDP socket测试连通性"""
        start_time = time.time()
        host, port = self.extract_host_port(url)
        
        if not host or not port:
            return False, 0, 0
        
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            if host.startswith(('239.', '224.')):
                try:
                    mreq = struct.pack("4sl", socket.inet_aton(host), socket.INADDR_ANY)
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                except:
                    pass
            
            sock.sendto(b'GET / HTTP/1.0\r\n\r\n', (host, port))
            data, addr = sock.recvfrom(1024)
            elapsed = (time.time() - start_time) * 1000
            
            if len(data) > 0:
                speed_kbps = (len(data) / 1024) / (elapsed / 1000) * 8
                if speed_kbps < 1:
                    speed_kbps = self.min_speed_kbps
                return True, speed_kbps, elapsed
            return False, 0, elapsed
        except socket.timeout:
            return False, 0, self.timeout * 1000
        except Exception:
            return False, 0, 0
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass
    
    def test_single_channel(self, name, url):
        """单个频道测速入口 - 自动识别协议"""
        if url.startswith(('http://', 'https://')):
            is_alive, speed, ms = self.test_http_channel(url)
        elif url.startswith(('rtp://', 'udp://', 'igmp://')):
            is_alive, speed, ms = self.test_multicast_channel(url)
        else:
            return False, 0, 0
        
        if is_alive:
            print(f"      ✓ {name}: {speed:.0f}Kbps ({ms:.0f}ms)")
        return is_alive, speed, ms
    
    def test_host_availability(self, host, sample_urls):
        """测试一个服务器的可用性（只测试前N个样本）"""
        test_count = min(len(sample_urls), self.max_test_per_server)
        for i in range(test_count):
            name, url = sample_urls[i]
            is_alive, speed, ms = self.test_single_channel(name, url)
            if is_alive:
                return True, speed, ms
        return False, 0, 0
    
    def batch_test_channels(self, channels):
        """批量测速（带服务器缓存）"""
        if not channels:
            return []
        
        # 1. 按服务器分组
        server_groups = defaultdict(list)
        for name, url in channels:
            host = self.extract_host(url)
            server_groups[host].append((name, url))
        
        print(f"  [测速] 共 {len(server_groups)} 个服务器")
        if self.cache_host:
            print(f"  [缓存] 每个服务器最多测试 {self.max_test_per_server} 个频道")
        
        # 2. 测试每个服务器的可用性
        alive_servers = {}
        for host, urls in server_groups.items():
            if self.cache_host and host in self.host_cache:
                is_alive, speed, ms = self.host_cache[host]
                print(f"    [缓存] {host} -> {'可用' if is_alive else '不可用'}")
                alive_servers[host] = (is_alive, speed, ms)
                continue
            
            print(f"    [探测] {host}...")
            is_alive, speed, ms = self.test_host_availability(host, urls)
            alive_servers[host] = (is_alive, speed, ms)
            if self.cache_host:
                self.host_cache[host] = (is_alive, speed, ms)
            
            if is_alive:
                print(f"      ✓ 服务器可用 ({speed:.0f}Kbps, {ms:.0f}ms)")
            else:
                print(f"      ✗ 服务器不可用")
        
        # 3. 收集所有可用服务器的频道
        results = []
        for host, urls in server_groups.items():
            is_alive, speed, ms = alive_servers.get(host, (False, 0, 0))
            if is_alive:
                for name, url in urls:
                    results.append((name, url, speed, ms))
        
        # 按速度排序
        results.sort(key=lambda x: x[2], reverse=True)
        
        print(f"  [结果] 存活 {len(results)}/{len(channels)} 个频道")
        if results:
            print(f"  [结果] 最快: {results[0][0]} ({results[0][2]:.0f}Kbps)")
        
        return results


def build_tvg_logo_url(channel_name):
    safe_name = quote(channel_name.strip(), safe="")
    return f"{TVG_LOGO_BASE_URL}{safe_name}.png"


def deduplicate_channels(channels, max_per_channel=2):
    """按频道名去重，每个频道只保留速度最快的N个"""
    if not channels:
        return []
    groups = defaultdict(list)
    for name, url, speed, ms in channels:
        groups[name].append((name, url, speed, ms))
    result = []
    for name, sources in groups.items():
        sources.sort(key=lambda x: x[2], reverse=True)
        result.extend(sources[:max_per_channel])
        if len(sources) > max_per_channel:
            print(f"    [去重] {name}: {len(sources)}个源 → 保留最快的{max_per_channel}个")
    result.sort(key=lambda x: x[2], reverse=True)
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
        if file == "output":
            continue
        
        file_path = os.path.join(txt_dir, file)
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or ',' not in line:
                    continue
                name, url = line.split(',', 1)
                
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
    
    txt_merge_dir = os.path.join(txt_output_dir, "output")
    m3u_merge_dir = os.path.join(m3u_output_dir, "output")
    os.makedirs(txt_merge_dir, exist_ok=True)
    os.makedirs(m3u_merge_dir, exist_ok=True)
    
    total_count = 0
    for operator, channels in all_channels.items():
        if not channels:
            continue
        
        channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
        
        if MAX_CHANNELS_PER_OPERATOR > 0 and len(channels) > MAX_CHANNELS_PER_OPERATOR:
            channels = channels[:MAX_CHANNELS_PER_OPERATOR]
            print(f"  [限制] {operator}: 限制为 {MAX_CHANNELS_PER_OPERATOR} 个频道")
        
        if MERGE_SORT_BY_SPEED:
            channels.sort(key=lambda x: x[2], reverse=True)
        
        file_name = MERGE_FILE_NAMES.get(operator, operator)
        
        txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            for name, url, speed, ms in channels:
                f.write(f"{name},{url}\n")
        
        m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
        with open(m3u_path, 'w', encoding='utf-8') as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            for name, url, speed, ms in channels:
                speed_str = f" [{speed:.0f}Kbps|{ms:.0f}ms]"
                f.write(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{operator}",{name}{speed_str}\n{url}\n')
        
        print(f"  ✓ {operator}: {len(channels)} 个频道 -> output/{file_name}")
        total_count += len(channels)
    
    print(f"\n[+] 合并完成，共 {total_count} 个频道")


def delete_origin_files(txt_dir, m3u_dir):
    """删除原文件"""
    print("\n[*] 删除原文件...")
    keep_txt = [f"{name}.txt" for name in MERGE_FILE_NAMES.values()]
    keep_m3u = [f"{name}.m3u" for name in MERGE_FILE_NAMES.values()]
    
    if os.path.exists(txt_dir):
        for file in os.listdir(txt_dir):
            if file.endswith('.txt') and file not in keep_txt and file != "output":
                os.remove(os.path.join(txt_dir, file))
                print(f"  删除: txt/{file}")
    
    if os.path.exists(m3u_dir):
        for file in os.listdir(m3u_dir):
            if file.endswith('.m3u') and file not in keep_m3u and file != "output":
                os.remove(os.path.join(m3u_dir, file))
                print(f"  删除: m3u/{file}")


def main():
    # 获取项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    txt_dir = os.path.join(project_root, SOURCE_TXT_DIR)
    m3u_dir = os.path.join(project_root, SOURCE_M3U_DIR)
    
    print(f"\n{'='*50}")
    print(f"测速合并工具 a.py")
    print(f"测速配置: 超时={SPEED_TEST_TIMEOUT}s, 并发={SPEED_TEST_THREADS}, 最低速度={MIN_SPEED_KBPS}Kbps")
    print(f"服务器缓存: {'启用' if SPEEDTEST_CACHE_HOST else '禁用'}, 每服务器测试{SPEEDTEST_MAX_PER_SERVER}个频道")
    print(f"TXT目录: {txt_dir}")
    print(f"M3U目录: {m3u_dir}")
    print(f"{'='*50}")
    
    if not os.path.exists(txt_dir):
        print(f"[-] 目录不存在: {txt_dir}")
        print("[*] 请先运行 b.py 生成文件")
        return
    
    # 1. 读取所有频道
    print("\n[1] 读取b.py生成的文件...")
    all_channels = read_all_channels(txt_dir)
    
    total_raw = sum(len(v) for v in all_channels.values())
    print(f"    共读取 {total_raw} 个频道")
    for op, chs in all_channels.items():
        if chs:
            print(f"    - {op}: {len(chs)} 个")
    
    if total_raw == 0:
        print("[-] 没有找到任何频道")
        return
    
    # 2. 测速
    print("\n[2] 开始测速...")
    tester = SpeedTester(
        timeout=SPEED_TEST_TIMEOUT,
        max_workers=SPEED_TEST_THREADS,
        min_speed=MIN_SPEED_KBPS,
        download_size=DOWNLOAD_SIZE_KB,
        cache_host=SPEEDTEST_CACHE_HOST,
        max_test_per_server=SPEEDTEST_MAX_PER_SERVER
    )
    
    for operator in all_channels:
        if all_channels[operator]:
            print(f"\n  [{operator}] 测速中...")
            channels = [(name, url) for name, url in all_channels[operator]]
            valid = tester.batch_test_channels(channels)
            all_channels[operator] = valid
    
    # 3. 保存合并文件
    if ENABLE_MERGE:
        save_merge_files(txt_dir, m3u_dir, all_channels)
    
    # 4. 删除原文件
    if not KEEP_ORIGIN_FILES:
        delete_origin_files(txt_dir, m3u_dir)
    
    print(f"\n[+] 全部完成！")


if __name__ == '__main__':
    main()
