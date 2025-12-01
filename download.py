import os
import json
import hashlib
from pathlib import Path
import requests
from urllib.parse import urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import time
import re
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FastImageDownloadManager:
    # UA池 - 模拟真实浏览器
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]

    REFERER_POOL = [
        'https://www.google.com/',
        'https://www.bing.com/',
        'https://www.baidu.com/',
        '',  # 空Referer
    ]

    def __init__(self, url_folder='url', download_folder='download',
                 mapping_file='download_mapping.json', max_workers=8,
                 request_delay=(0.5, 2.0), enable_proxy=False,
                 proxy_list=None):
        """
        初始化下载管理器

        参数：
            url_folder: URL文件夹
            download_folder: 下载文件夹
            mapping_file: 映射文件
            max_workers: 最大线程数（建议5-8）
            request_delay: 请求延迟范围(最小, 最大)秒，单位为浮点数
            enable_proxy: 是否启用代理
            proxy_list: 代理列表，格式: ['http://ip:port', ...]
        """
        self.url_folder = url_folder
        self.download_folder = download_folder
        self.mapping_file = mapping_file
        self.max_workers = max_workers
        self.request_delay = request_delay
        self.enable_proxy = enable_proxy
        self.proxy_list = proxy_list or []
        self.current_proxy_index = 0

        self.url_mapping = self._load_mapping()
        self.session = self._create_session()

        # 记录上次请求时间，用于延迟控制
        self.last_request_time = 0

    def _create_session(self):
        """
        创建带有反爬措施的requests会话
        """
        session = requests.Session()

        # 配置自动重试策略（针对连接错误）
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # 设置完整的浏览器请求头
        session.headers.update(self._get_random_headers())

        # 禁用SSL警告（仅用于某些服务器）
        session.verify = True

        return session

    def _get_random_headers(self):
        """
        生成随机的浏览器请求头，每次调用返回不同的头部组合
        """
        return {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': random.choice(['zh-CN,zh;q=0.9,en;q=0.8', 'en-US,en;q=0.9', 'zh-CN,zh;q=0.9']),
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

    def _get_random_referer(self):
        """
        获取随机的Referer头
        """
        return random.choice(self.REFERER_POOL)

    def _apply_intelligent_delay(self):
        """
        应用智能延迟机制，模拟真实用户的请求间隔
        """
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        min_delay, max_delay = self.request_delay
        required_delay = random.uniform(min_delay, max_delay)

        if time_since_last_request < required_delay:
            sleep_time = required_delay - time_since_last_request
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _get_next_proxy(self):
        """
        从代理列表中获取下一个代理
        """
        if not self.enable_proxy or not self.proxy_list:
            return None

        proxy = self.proxy_list[self.current_proxy_index % len(self.proxy_list)]
        self.current_proxy_index += 1
        return {'http': proxy, 'https': proxy}

    def _load_mapping(self):
        if os.path.exists(self.mapping_file):
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_mapping(self):
        with open(self.mapping_file, 'w', encoding='utf-8') as f:
            json.dump(self.url_mapping, f, ensure_ascii=False, indent=2)

    def _extract_filename_from_response(self, response, url):
        """
        从响应头提取文件名，优先使用Content-Disposition，其次使用URL路径
        """
        # 方式1: 从 Content-Disposition 响应头获取
        content_disposition = response.headers.get('Content-Disposition', '')
        if content_disposition:
            # 处理 filename*=UTF-8''filename.ext 格式
            match = re.search(r"filename\*=(?:UTF-8'')?(.+?)(?:;|$)", content_disposition)
            if match:
                filename = unquote(match.group(1))
                if filename:
                    return filename.strip('"\'')

            # 处理 filename="filename.ext" 格式
            match = re.search(r'filename=(["\']?)(.+?)\1(?:;|$)', content_disposition)
            if match:
                filename = match.group(2)
                if filename:
                    return filename.strip('"\'')

        # 方式2: 从URL路径获取
        parsed_url = urlparse(url)
        filename = Path(parsed_url.path).name
        if filename and '.' in filename:
            return unquote(filename)

        # 方式3: 备选方案 - 从Content-Type推断扩展名
        content_type = response.headers.get('Content-Type', '').split(';')[0]
        ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/svg+xml': '.svg',
            'application/octet-stream': '.bin'
        }
        ext = ext_map.get(content_type, '.tmp')
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{url_hash}{ext}"

    def _ensure_dir(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)

    def download_with_retry(self, url, keyword_dir, max_retries=10):
        """
        带重试的下载函数，支持断点续传，返回本地文件路径
        """
        temp_path = None
        local_path = None

        for attempt in range(max_retries):
            try:
                # 应用请求前延迟
                self._apply_intelligent_delay()

                # 第一次请求时获取文件名
                if temp_path is None:
                    # 为HEAD请求添加随机头和代理
                    headers = self._get_random_headers()
                    headers['Referer'] = self._get_random_referer()
                    proxies = self._get_next_proxy()

                    response = self.session.head(
                        url,
                        headers=headers,
                        proxies=proxies,
                        timeout=15,
                        allow_redirects=True
                    )
                    response.raise_for_status()

                    filename = self._extract_filename_from_response(response, url)
                    local_path = os.path.join(keyword_dir, filename)
                    temp_path = local_path + '.tmp'

                # 检查已存在的临时文件大小
                resume_header = {}
                if os.path.exists(temp_path):
                    resume_header['Range'] = f'bytes={os.path.getsize(temp_path)}-'

                # 为GET请求添加随机头和代理
                headers = self._get_random_headers()
                headers['Referer'] = self._get_random_referer()
                headers.update(resume_header)
                proxies = self._get_next_proxy()

                response = self.session.get(
                    url,
                    headers=headers,
                    proxies=proxies,
                    timeout=15,
                    stream=True,
                    allow_redirects=True
                )
                response.raise_for_status()

                # 流式写入，避免内存溢出
                with open(temp_path, 'ab') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                # 下载成功，重命名临时文件
                shutil.move(temp_path, local_path)
                return local_path

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    # 重试时使用更长的退避延迟
                    wait_time = (2 ** min(attempt, 5)) + random.uniform(0, 1)
                    print(f"下载失败 (尝试 {attempt + 1}/{max_retries}): {url}")
                    print(f"等待 {wait_time:.1f} 秒后重试...")
                    time.sleep(wait_time)
                    # 重试前更新proxy索引
                    if self.enable_proxy and self.proxy_list:
                        self.current_proxy_index += 1
                else:
                    print(f"下载最终失败: {url} - {str(e)}")
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                    return None

        return None

    def _process_single_url(self, url, keyword_dir):
        """
        处理单个URL的下载或复制逻辑
        """
        if not url.strip():
            return

        url = url.strip()

        # 已下载过的链接，直接复制
        if url in self.url_mapping:
            source_file = self.url_mapping[url]
            if os.path.exists(source_file):
                target_file = os.path.join(keyword_dir, Path(source_file).name)
                if not os.path.exists(target_file):
                    shutil.copy2(source_file, target_file)
                print(f"✓ 复制: {url}")
                return

        # 新链接，进行下载
        local_path = self.download_with_retry(url, keyword_dir)

        if local_path:
            self.url_mapping[url] = local_path
            print(f"✓ 下载: {url}")
        else:
            print(f"✗ 失败: {url}")

    def process_all(self):
        """
        多线程处理所有txt文件
        """
        if not os.path.exists(self.url_folder):
            print(f"错误: {self.url_folder} 文件夹不存在")
            return

        txt_files = list(Path(self.url_folder).glob('*.txt'))
        print(f"找到 {len(txt_files)} 个txt文件，使用 {self.max_workers} 个线程下载\n")

        # 收集所有下载任务
        download_tasks = []

        for txt_file in txt_files:
            keyword = txt_file.stem
            keyword_dir = os.path.join(self.download_folder, keyword)
            self._ensure_dir(keyword_dir)

            with open(txt_file, 'r', encoding='utf-8') as f:
                for url in f:
                    download_tasks.append((url.strip(), keyword_dir))

        # 使用线程池并发下载
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._process_single_url, url, keyword_dir)
                for url, keyword_dir in download_tasks
            ]

            # 显示进度
            completed = 0
            total = len(futures)
            for future in as_completed(futures):
                completed += 1
                print(f"进度: {completed}/{total}")
                try:
                    future.result()
                except Exception as e:
                    print(f"任务出错: {str(e)}")

        self._save_mapping()
        print(f"\n✓ 全部完成！映射表已保存")

# 使用示例
if __name__ == '__main__':
    # 基础用法 - 无代理
    # manager = FastImageDownloadManager(max_workers=8)

    # 进阶用法 - 带反爬参数
    manager = FastImageDownloadManager(
        url_folder='url',
        download_folder='download',
        mapping_file='download_mapping.json',
        max_workers=12,  # 下载线程数，也可更多，考虑反爬
        request_delay=(1.0, 3.0),  # 请求延迟1-3秒
        enable_proxy=False,  # 设置为True启用代理
        proxy_list=[
            # 'http://proxy1.com:8080',
            # 'http://proxy2.com:8080',
        ]
    )

    manager.process_all()