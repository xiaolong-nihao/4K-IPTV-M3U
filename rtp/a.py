#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专业测速合并模块 - 基于 get_speed_with_download 逻辑
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

# 测速配置（完全按照原版）
SPEED_TEST_TIMEOUT = 5            # 测速超时时间(秒)
SPEED_TEST_CONCURRENT = 20        # 并发测速数
SPEED_TEST_FILTER_HOST = True     # 相同Host共享测速结果

# 缓存配置
ENABLE_CACHE = True

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


class SpeedTester:
    """专业测速器 - 完全按照原版 get_speed_with_download 逻辑"""
    
    def __init__(self, timeout=5, concurrent=20):
        self.timeout = timeout
        self.concurrent = concurrent
        self.cache = {}  # host -> list of results
        self.session = None
    
    async def _get_session(self):
        if self.session is None:
            self.session = ClientSession(
                connector=TCPConnector(ssl=False, limit=100),
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
        return self.session
    
    def extract_host(self, url):
        """提取Host用于缓存"""
        try:
            match = re.match(r'https?://([^/:]+)(?::(\d+))?', url)
            if match:
                return match.group(1)
            return url
        except:
            return url
    
    async def get_speed_with_download(self, url, session):
        """
        完全按照原版 get_speed_with_download 逻辑
        下载数据测速，返回 {speed, delay, size, time}
        """
        start_time = time.time()
        delay = -1
        total_size = 0
        
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    return {'speed': 0, 'delay': -1, 'size': 0, 'time': 0}
                
                delay = int(round((time.time() - start_time) * 1000))
                
                # 下载数据直到超时
                async for chunk in response.content.iter_any():
                    if chunk:
                        total_size += len(chunk)
                        
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        
        total_time = time.time() - start_time
        speed = total_size / total_time / 1024 / 1024 if total_time > 0 else 0
        
        return {
            'speed': speed,
            'delay': delay,
            'size': total_size,
            'time': total_time,
        }
    
    async def test_channel(self, name, url, session):
        """测试单个频道"""
        # 检查缓存
        host = self.extract_host(url)
        if ENABLE_CACHE and SPEED_TEST_FILTER_HOST and host in self.cache:
            cached = self.cache[host]
            if cached:
                avg_speed = sum(r['speed'] for r in cached) / len(cached)
                avg_delay = sum(r['delay'] for r in cached) / len(cached)
                print(f"      [缓存] {name}: {avg_speed:.2f}MB/s, {avg_delay:.0f}ms")
                return True, avg_speed, avg_delay
        
        # 测速
        result = await self.get_speed_with_download(url, session)
        speed = result['speed']
        delay = result['delay']
        
        if speed > 0 and delay > 0:
            print(f"      ✓ {name}: {speed:.2f}MB/s, {delay}ms")
            
            # 缓存结果
            if ENABLE_CACHE and SPEED_TEST_FILTER_HOST and host:
                self.cache.setdefault(host, []).append(result)
                # 限制缓存大小
                if len(self.cache[host]) > 5:
                    self.cache[host].pop(0)
            
            return True, speed, delay
        else:
            print(f"      ✗ {name}: 测速失败")
            return False, 0, 0
    
    async def batch_test(self, channels):
        """批量测试频道"""
        if not channels:
            return []
        
        session = await self._get_session()
        print(f"  [测速] 共 {len(channels)} 个频道，并发: {self.concurrent}")
        
        semaphore = asyncio.Semaphore(self.concurrent)
        
        async def test_one(name, url):
            async with semaphore:
                return await self.test_channel(name, url, session)
        
        tasks = [test_one(name, url) for name, url in channels]
        results = await asyncio.gather(*tasks)
        
        valid = []
        for i, (is_alive, speed, delay) in enumerate(results):
            if is_alive:
                name, url = channels[i]
                valid.append((name, url, speed, delay))
        
        # 按速度降序排序
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
    print(f"专业测速合并工具")
    print(f"测速配置: 超时={SPEED_TEST_TIMEOUT}s, 并发={SPEED_TEST_CONCURRENT}")
    print(f"Host缓存: {'启用' if SPEED_TEST_FILTER_HOST else '禁用'}")
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
    print("\n[2] 开始测速...")
    tester = SpeedTester(timeout=SPEED_TEST_TIMEOUT, concurrent=SPEED_TEST_CONCURRENT)
    
    for operator in all_channels:
        if all_channels[operator]:
            print(f"\n  [{operator}] 测速中...")
            channels = all_channels[operator]
            valid = await tester.batch_test(channels)
            all_channels[operator] = valid
    
    await tester.close()
    
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
