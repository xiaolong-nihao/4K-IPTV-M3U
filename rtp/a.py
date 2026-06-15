#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组播代理测速合并模块 - 复用专业测速逻辑
"""

import os
import re
import time
import asyncio
import aiohttp
from datetime import datetime
from collections import defaultdict
from urllib.parse import quote
from aiohttp import ClientSession, TCPConnector

# ================= 配置区域 =================
SOURCE_TXT_DIR = "txt"
SOURCE_M3U_DIR = "m3u"

# 测速配置
ENABLE_SPEED_TEST = True          # 是否启用测速
SPEED_TEST_TIMEOUT = 5            # 测速超时时间(秒)
SPEED_TEST_CONCURRENT = 20        # 并发测速数

# 下载测速配置
MIN_DOWNLOAD_SIZE = 64 * 1024     # 最小下载64KB
MIN_MEASURE_TIME = 1.0            # 最短测量时间(秒)
STABILITY_WINDOW = 4              # 稳定性窗口大小
STABILITY_THRESHOLD = 0.12        # 波动小于12%认为稳定

# 缓存配置
ENABLE_CACHE = True               # 启用Host缓存
CACHE_MAX_PER_HOST = 5            # 每个Host最多缓存几个结果

# 合并配置
MAX_SOURCES_PER_CHANNEL = 2       # 每个频道保留几个源
MAX_CHANNELS_PER_OPERATOR = 500   # 每个运营商最多频道数
MERGE_SORT_BY_SPEED = True        # 按速度排序

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


class RtpProxyTester:
    """组播代理测速器 - 专门测试 /rtp/ 代理链接"""
    
    def __init__(self, timeout=5, concurrent=20):
        self.timeout = timeout
        self.concurrent = concurrent
        self.cache = {}
        self.session = None
    
    async def _get_session(self):
        if self.session is None:
            self.session = ClientSession(
                connector=TCPConnector(ssl=False, limit=100),
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
        return self.session
    
    def extract_host(self, url):
        """从URL中提取服务器地址"""
        try:
            match = re.match(r'https?://([^/:]+)(?::(\d+))?', url)
            if match:
                return match.group(1)
            return url
        except:
            return url
    
    def is_rtp_proxy(self, url):
        """判断是否是组播代理链接"""
        return '/rtp/' in url or '/udp/' in url or url.startswith('rtp://')
    
    async def get_speed_with_download(self, url, session):
        """
        下载测速 - 带稳定性检测
        返回: (是否可用, 速度MB/s, 延迟ms)
        """
        start_time = time.time()
        total_size = 0
        speed_samples = []
        last_sample_time = start_time
        last_sample_size = 0
        
        try:
            async with session.get(url, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return False, 0, -1
                
                delay = int(round((time.time() - start_time) * 1000))
                
                async for chunk in resp.content.iter_any():
                    if chunk:
                        total_size += len(chunk)
                        now = time.time()
                        elapsed = now - start_time
                        delta_t = now - last_sample_time
                        delta_b = total_size - last_sample_size
                        
                        if delta_t > 0 and delta_b > 0:
                            inst_speed = delta_b / delta_t / 1024 / 1024
                            speed_samples.append(inst_speed)
                            last_sample_time = now
                            last_sample_size = total_size
                        
                        # 稳定性检测
                        if (elapsed >= MIN_MEASURE_TIME and 
                            total_size >= MIN_DOWNLOAD_SIZE and
                            len(speed_samples) >= STABILITY_WINDOW):
                            
                            window = speed_samples[-STABILITY_WINDOW:]
                            mean = sum(window) / len(window)
                            if mean > 0 and (max(window) - min(window)) / mean < STABILITY_THRESHOLD:
                                total_time = time.time() - start_time
                                speed = total_size / total_time / 1024 / 1024
                                return True, speed, delay
                
                total_time = time.time() - start_time
                speed = total_size / total_time / 1024 / 1024 if total_time > 0 else 0
                return speed > 0, speed, delay
                
        except asyncio.TimeoutError:
            return False, 0, -1
        except Exception:
            return False, 0, -1
    
    async def test_channel(self, name, url):
        """测试单个频道"""
        session = await self._get_session()
        
        # 检查缓存
        host = self.extract_host(url)
        if ENABLE_CACHE and host in self.cache:
            cached = self.cache[host]
            if cached:
                avg_speed = sum(r[0] for r in cached) / len(cached)
                avg_delay = sum(r[1] for r in cached) / len(cached)
                print(f"      [缓存] {name}: {avg_speed:.2f}MB/s, {avg_delay:.0f}ms")
                return True, avg_speed, avg_delay
        
        # 测试
        is_alive, speed, delay = await self.get_speed_with_download(url, session)
        
        if is_alive and speed > 0:
            print(f"      ✓ {name}: {speed:.2f}MB/s, {delay}ms")
            
            # 缓存结果
            if ENABLE_CACHE and host:
                self.cache.setdefault(host, []).append((speed, delay))
                if len(self.cache[host]) > CACHE_MAX_PER_HOST:
                    self.cache[host].pop(0)
            
            return True, speed, delay
        else:
            print(f"      ✗ {name}: 测速失败")
            return False, 0, 0
    
    async def batch_test(self, channels):
        """批量测试频道"""
        if not channels:
            return []
        
        print(f"  [测速] 共 {len(channels)} 个频道，并发: {self.concurrent}")
        
        semaphore = asyncio.Semaphore(self.concurrent)
        
        async def test_one(name, url):
            async with semaphore:
                return await self.test_channel(name, url)
        
        tasks = [test_one(name, url) for name, url in channels]
        results = await asyncio.gather(*tasks)
        
        valid = []
        for i, (is_alive, speed, delay) in enumerate(results):
            if is_alive:
                name, url = channels[i]
                valid.append((name, url, speed, delay))
        
        valid.sort(key=lambda x: x[2], reverse=True)
        
        print(f"  [结果] 存活 {len(valid)}/{len(channels)} 个频道")
        if valid:
            print(f"  [结果] 最快: {valid[0][0]} ({valid[0][2]:.2f}MB/s)")
        
        return valid
    
    async def close(self):
        if self.session:
            await self.session.close()


def build_tvg_logo_url(channel_name):
    safe_name = quote(channel_name.strip(), safe="")
    return f"{TVG_LOGO_BASE_URL}{safe_name}.png"


def deduplicate_channels(channels, max_per_channel=2):
    """按频道名去重，每个频道只保留速度最快的N个"""
    if not channels:
        return []
    groups = defaultdict(list)
    for name, url, speed, delay in channels:
        groups[name].append((name, url, speed, delay))
    
    result = []
    for name, sources in groups.items():
        sources.sort(key=lambda x: x[2], reverse=True)
        result.extend(sources[:max_per_channel])
        if len(sources) > max_per_channel:
            print(f"    [去重] {name}: {len(sources)}个源 → 保留{max_per_channel}个")
    
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
        if not file.endswith('.txt') or file == "output":
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
        
        channels = deduplicate_channels(channels, MAX_SOURCES_PER_CHANNEL)
        
        if MAX_CHANNELS_PER_OPERATOR > 0 and len(channels) > MAX_CHANNELS_PER_OPERATOR:
            channels = channels[:MAX_CHANNELS_PER_OPERATOR]
            print(f"  [限制] {operator}: 限制为 {MAX_CHANNELS_PER_OPERATOR} 个频道")
        
        if MERGE_SORT_BY_SPEED:
            channels.sort(key=lambda x: x[2], reverse=True)
        
        file_name = MERGE_FILE_NAMES.get(operator, operator)
        
        # 保存TXT
        txt_path = os.path.join(txt_merge_dir, f"{file_name}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            for name, url, speed, delay in channels:
                f.write(f"{name},{url}\n")
        
        # 保存M3U
        m3u_path = os.path.join(m3u_merge_dir, f"{file_name}.m3u")
        with open(m3u_path, 'w', encoding='utf-8') as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            for name, url, speed, delay in channels:
                info = f" [{speed:.2f}MB/s|{delay:.0f}ms]" if speed > 0 else ""
                f.write(f'#EXTINF:-1 tvg-id="{name}" tvg-logo="{build_tvg_logo_url(name)}" group-title="{operator}",{name}{info}\n{url}\n')
        
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


async def main_async():
    """异步主函数"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    txt_dir = os.path.join(project_root, SOURCE_TXT_DIR)
    m3u_dir = os.path.join(project_root, SOURCE_M3U_DIR)
    
    print(f"\n{'='*50}")
    print(f"组播代理测速合并工具")
    print(f"测速配置: 超时={SPEED_TEST_TIMEOUT}s, 并发={SPEED_TEST_CONCURRENT}")
    print(f"下载测速: 最小{MIN_DOWNLOAD_SIZE//1024}KB, 稳定窗口{STABILITY_WINDOW}个样本, 波动<{STABILITY_THRESHOLD*100:.0f}%")
    print(f"缓存: {'启用' if ENABLE_CACHE else '禁用'}")
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
    
    # 2. 测速
    if ENABLE_SPEED_TEST:
        print("\n[2] 开始测速...")
        tester = RtpProxyTester(timeout=SPEED_TEST_TIMEOUT, concurrent=SPEED_TEST_CONCURRENT)
        
        for operator in all_channels:
            if all_channels[operator]:
                print(f"\n  [{operator}] 测速中...")
                channels = all_channels[operator]
                valid = await tester.batch_test(channels)
                all_channels[operator] = valid
        
        await tester.close()
    else:
        print("\n[2] 跳过测速，直接合并...")
        for operator in all_channels:
            all_channels[operator] = [(name, url, 1.0, 50) for name, url in all_channels[operator]]
    
    # 3. 保存合并文件
    save_merge_files(txt_dir, m3u_dir, all_channels)
    
    # 4. 删除原文件
    if not KEEP_ORIGIN_FILES:
        delete_origin_files(txt_dir, m3u_dir)
    
    print(f"\n[+] 全部完成！")


def main():
    """同步入口"""
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
