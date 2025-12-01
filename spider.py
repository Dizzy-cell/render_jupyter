import asyncio
import logging
import random
import time
import string
from typing import List, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser
from collections import deque
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AntiSpiderConfig:
    """
    反爬虫配置类
    """

    # User-Agent池
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    ]

    # HTTP请求头
    COMMON_HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Pragma': 'no-cache',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
    }

    # 代理服务器列表 (可选，需自行配置)
    PROXIES = []  # 格式: ["http://IP:PORT", "http://IP:PORT"]

    # 访问频率控制
    MAX_REQUESTS_PER_MINUTE = 30  # 每分钟最多请求数
    MIN_REQUEST_INTERVAL = 1.5  # 最小请求间隔(秒)

    # 随机延迟配置
    SCROLL_DELAY_MIN = 2.0
    SCROLL_DELAY_MAX = 5.0
    CLICK_DELAY_MIN = 1.0
    CLICK_DELAY_MAX = 3.0

    # 重试配置 - 指数退避
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 2  # 2秒、4秒、8秒

    # 响应验证
    CHECK_RESPONSE_VALIDITY = True


class RateLimiter:
    """
    访问频率限制器 - 基于令牌桶算法
    防止短时间内发送过多请求而被限流
    """

    def __init__(self, max_requests: int, time_window: int = 60):
        """
        Args:
            max_requests: 时间窗口内的最大请求数
            time_window: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_times = deque()

    async def acquire(self):
        """获取令牌，如果超过限制则等待"""
        now = time.time()

        # 清除时间窗口外的请求记录
        while self.request_times and self.request_times[0] < now - self.time_window:
            self.request_times.popleft()

        # 如果达到限制，计算需要等待的时间
        if len(self.request_times) >= self.max_requests:
            sleep_time = self.time_window - (now - self.request_times[0]) + 0.1
            if sleep_time > 0:
                logger.info(f"⏳ 频率限制触发，等待 {sleep_time:.2f}秒...")
                await asyncio.sleep(sleep_time)

        self.request_times.append(time.time())


class AntiSpiderHelper:
    """
    反爬虫辅助类
    提供反爬虫工具函数
    """

    @staticmethod
    def get_random_user_agent() -> str:
        """随机获取User-Agent，增加多样性"""
        return random.choice(AntiSpiderConfig.USER_AGENTS)

    @staticmethod
    def get_headers_with_referer(referer: str = "https://www.google.com/") -> dict:
        """
        获取完整的HTTP请求头
        Args:
            referer: 来源页面，默认谷歌搜索
        """
        headers = AntiSpiderConfig.COMMON_HEADERS.copy()
        headers['User-Agent'] = AntiSpiderHelper.get_random_user_agent()
        headers['Referer'] = referer
        return headers

    @staticmethod
    async def random_delay(min_delay: float, max_delay: float, jitter: bool = True):
        """
        生成随机延迟，模拟人类行为

        Args:
            min_delay: 最小延迟
            max_delay: 最大延迟
            jitter: 是否添加抖动，增加不规律性
        """
        delay = random.uniform(min_delay, max_delay)

        # 添加高斯分布的抖动，更符合人类行为
        if jitter:
            jitter_value = random.gauss(0, (max_delay - min_delay) * 0.1)
            delay = max(min_delay, min(max_delay, delay + jitter_value))

        await asyncio.sleep(delay)

    @staticmethod
    async def simulate_mouse_movement(page: Page):
        """
        模拟鼠标随机移动，增加真实性
        """
        try:
            x = random.randint(100, 1000)
            y = random.randint(100, 800)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            logger.debug(f"鼠标移动失败: {e}")

    @staticmethod
    async def simulate_random_pause(page: Page, probability: float = 0.3):
        """
        模拟用户随机停顿浏览（概率性），更像真实用户

        Args:
            page: Playwright Page对象
            probability: 触发暂停的概率
        """
        if random.random() < probability:
            pause_duration = random.uniform(2, 8)
            logger.info(f"模拟用户停顿浏览 {pause_duration:.2f}秒...")
            await asyncio.sleep(pause_duration)

    @staticmethod
    async def validate_page_response(page: Page) -> bool:
        """
        验证页面响应是否有效
        检查是否被重定向到验证页面、是否有反爬标记等
        """
        try:
            # 检查页面标题
            title = await page.title()
            if not title:
                logger.warning("页面标题为空，可能被反爬")
                return False

            # 检查页面内容
            content = await page.content()
            if len(content) < 1000:
                logger.warning("页面内容过少，可能被反爬或页面加载失败")
                return False

            # 检查常见的反爬提示词
            forbidden_keywords = ['429', 'Too Many Requests', 'Cloudflare', 'challenge']
            if any(keyword in content for keyword in forbidden_keywords):
                logger.warning("检测到反爬标记")
                return False

            return True
        except Exception as e:
            logger.error(f"页面响应验证失败: {e}")
            return False

    @staticmethod
    def get_random_proxy() -> Optional[str]:
        """随机获取代理IP"""
        if AntiSpiderConfig.PROXIES:
            return random.choice(AntiSpiderConfig.PROXIES)
        return None


class UnsplashScraper:
    """
    Unsplash图片爬虫
    功能：点击Load more按钮，持续滚动加载
    含多层次反爬措施
    """

    TARGET_URL = "https://unsplash.com/s/photos/people"
    LOAD_MORE_SELECTOR = "button.loadMoreButton-pYP1fq"
    LOAD_MORE_XPATH = "//button[@type='button' and contains(@class, 'loadMoreButton')]"
    SCROLL_PAUSE = 2
    LOAD_TIMEOUT = 10
    MAX_SCROLL_ATTEMPTS = 10000

    def __init__(self, search_keyword="people", save_threshold=10000):
        """
        初始化爬虫配置

        Args:
            search_keyword (str): 搜索词
            save_threshold (int): 保存文件的链接数量阈值
        """
        self.search_keyword = search_keyword
        self.save_threshold = save_threshold

        self.TARGET_URL = f"https://unsplash.com/s/photos/{search_keyword}"
        self.LOAD_MORE_SELECTOR = "button.loadMoreButton-pYP1fq"
        self.LOAD_MORE_XPATH = "//button[@type='button' and contains(@class, 'loadMoreButton')]"
        self.SCROLL_PAUSE = 2
        self.LOAD_TIMEOUT = 10
        self.MAX_SCROLL_ATTEMPTS = 10000

        self.browser: Browser = None
        self.page: Page = None
        self.download_links = set()
        self.output_file = f"{search_keyword}_0.txt"
        self.total_saved_links = 0

        # 反爬虫相关成员
        self.rate_limiter = RateLimiter(
            max_requests=AntiSpiderConfig.MAX_REQUESTS_PER_MINUTE,
            time_window=60
        )
        self.request_count = 0  # 请求计数
        self.last_request_time = 0  # 最后请求时间
        self.playwright = None

    async def initialize(self):
        """初始化浏览器 """
        try:
            self.playwright = await async_playwright().start()

            # 获取代理和User-Agent
            proxy = AntiSpiderHelper.get_random_proxy()

            # 浏览器启动参数 - 规避反爬检测
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",  # 降低内存占用
                "--no-sandbox",  # 禁用沙箱
                "--disable-gpu",  # 禁用GPU
                "--disable-web-resources",  # 禁用某些资源
            ]

            browser_kwargs = {
                "headless": True,
                "args": launch_args,
            }

            # 如果配置了代理，添加到浏览器启动参数
            if proxy:
                browser_kwargs["proxy"] = {"server": proxy}
                logger.info(f"使用代理: {proxy}")

            self.browser = await self.playwright.chromium.launch(**browser_kwargs)

            # 创建新页面
            self.page = await self.browser.new_page()

            # 设置HTTP请求头和User-Agent
            headers = AntiSpiderHelper.get_headers_with_referer()
            await self.page.set_extra_http_headers(headers)

            # 注入JavaScript，规避反爬检测脚本
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh'],
                });
                window.chrome = { runtime: {} };
            """)

            # 设置viewport，模拟真实浏览器
            await self.page.set_viewport_size(
                {"width": random.randint(1200, 1920), "height": random.randint(800, 1080)})

            logger.info("✓ 浏览器初始化完成（含反爬增强）")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise

    async def navigate_to_target(self):
        """导航到目标页面 - 加入速率限制和响应验证"""
        try:
            # 获取频率限制令牌
            await self.rate_limiter.acquire()

            logger.info(f"正在访问: {self.TARGET_URL}")

            # 随机延迟，模拟真实用户行为
            await AntiSpiderHelper.random_delay(1.5, 3.5)

            await self.page.goto(
                self.TARGET_URL,
                wait_until="load",
                timeout=30000
            )

            # 页面响应验证
            if AntiSpiderConfig.CHECK_RESPONSE_VALIDITY:
                is_valid = await AntiSpiderHelper.validate_page_response(self.page)
                if not is_valid:
                    logger.warning("页面可能被反爬检测，但继续尝试...")

            # 等待动态内容加载
            await asyncio.sleep(random.uniform(2, 4))

            # 模拟随机暂停浏览
            await AntiSpiderHelper.simulate_random_pause(self.page, probability=0.2)

            self.request_count += 1
            logger.info("✓ 页面加载完成")

        except Exception as e:
            logger.error(f"页面访问失败: {e}")
            raise

    async def click_load_more_button(self) -> bool:
        """
        点击Load more按钮 - 原爬取逻辑不变
        添加反爬增强：频率限制、随机延迟、鼠标模拟
        """
        retry_count = 0

        while retry_count < AntiSpiderConfig.MAX_RETRIES:
            try:
                # 获取频率限制令牌
                await self.rate_limiter.acquire()

                # 模拟鼠标移动
                await AntiSpiderHelper.simulate_mouse_movement(self.page)

                load_more_btn = self.page.locator(self.LOAD_MORE_SELECTOR)

                if await load_more_btn.count() == 0:
                    logger.warning("Load more按钮不存在，可能已加载全部内容")
                    return False

                await load_more_btn.first.wait_for(state="visible", timeout=5000)
                await load_more_btn.first.scroll_into_view_if_needed()

                # 随机延迟后再点击
                await AntiSpiderHelper.random_delay(
                    AntiSpiderConfig.CLICK_DELAY_MIN,
                    AntiSpiderConfig.CLICK_DELAY_MAX
                )

                await load_more_btn.first.click()

                # 点击后的随机延迟
                await AntiSpiderHelper.random_delay(
                    AntiSpiderConfig.SCROLL_DELAY_MIN,
                    AntiSpiderConfig.SCROLL_DELAY_MAX
                )

                self.request_count += 1
                logger.info("✓ Load more按钮点击成功")
                return True

            except Exception as e:
                retry_count += 1
                logger.warning(f"第 {retry_count} 次点击失败: {e}")

                if retry_count < AntiSpiderConfig.MAX_RETRIES:
                    # 指数退避重试
                    backoff_time = AntiSpiderConfig.RETRY_BACKOFF_FACTOR ** retry_count
                    logger.info(f"等待 {backoff_time} 秒后重试...")
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error("点击按钮重试次数已达上限")
                    return False

    async def scroll_page(self) -> bool:
        """
        滚动页面 - 原爬取逻辑不变
        添加反爬增强：随机延迟、抖动、鼠标模拟
        """
        retry_count = 0

        while retry_count < AntiSpiderConfig.MAX_RETRIES:
            try:
                # 获取频率限制令牌
                await self.rate_limiter.acquire()

                before_height = await self.page.evaluate("document.body.scrollHeight")

                # 模拟鼠标移动和随机停顿
                await AntiSpiderHelper.simulate_mouse_movement(self.page)
                await AntiSpiderHelper.simulate_random_pause(self.page, probability=0.15)

                # 滚动到页面底部
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                # 使用配置的随机延迟，添加抖动
                await AntiSpiderHelper.random_delay(
                    AntiSpiderConfig.SCROLL_DELAY_MIN,
                    AntiSpiderConfig.SCROLL_DELAY_MAX,
                    jitter=True
                )

                after_height = await self.page.evaluate("document.body.scrollHeight")

                self.request_count += 1

                if after_height > before_height:
                    logger.info(f"✓ 新内容加载成功，高度增加: {after_height - before_height}px")
                    return True
                else:
                    logger.info("页面高度无变化，可能已到底部")
                    return False

            except Exception as e:
                retry_count += 1
                logger.warning(f"第 {retry_count} 次滚动失败: {e}")

                if retry_count < AntiSpiderConfig.MAX_RETRIES:
                    backoff_time = AntiSpiderConfig.RETRY_BACKOFF_FACTOR ** retry_count
                    await asyncio.sleep(backoff_time)
                else:
                    return False

    async def extract_download_links(self):
        """
        从当前页面提取所有图片下载链接
        """
        try:
            download_buttons = await self.page.locator(
                '[data-testid="non-sponsored-photo-download-button"]'
            ).all()

            new_links_count = 0

            #download_buttons = download_buttons[-100:]

            for button in download_buttons:
                href = await button.get_attribute("href")
                if href and href not in self.download_links:
                    self.download_links.add(href)
                    new_links_count += 1

            if new_links_count > 0:
                logger.info(f"✓ 提取新链接 {new_links_count} 个，总计 {len(self.download_links)} 个")

            return len(self.download_links)

        except Exception as e:
            logger.error(f"提取下载链接失败: {e}")
            return len(self.download_links)

    def save_links_to_file(self):
        """
        将收集的链接保存到txt文件
        """
        folder_path = "./url"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        try:
            self.total_saved_links += len(self.download_links)
            output_file = f"./url/{self.search_keyword}_{self.total_saved_links}.txt"

            with open(output_file, "a", encoding="utf-8") as f:
                for link in self.download_links:
                    f.write(link + "\n")

            logger.info(f"✓ 已保存 {len(self.download_links)} 个链接到 {output_file}，总计 {self.total_saved_links} 个")
        except Exception as e:
            logger.error(f"保存链接失败: {e}")

    async def run_load_more_flow(self):
        """
        执行完整的加载流程
        添加反爬增强：随机延迟、行为模拟、访问统计
        """
        try:
            logger.info("\n=== 第一步：点击Load more按钮 ===")
            if not await self.click_load_more_button():
                logger.warning("首次点击失败，尝试继续")

            # 随机延迟
            await AntiSpiderHelper.random_delay(2, 4)

            logger.info("\n=== 第二步：开始滚动加载 ===")
            scroll_count = 0
            no_load_count = 0

            while scroll_count < self.MAX_SCROLL_ATTEMPTS:
                scroll_count += 1
                logger.info(f"\n--- 滚动次数: {scroll_count} (请求总数: {self.request_count}) ---")

                is_loaded = await self.scroll_page()

                if is_loaded:
                    no_load_count = 0
                else:
                    no_load_count += 1

                if no_load_count >= 3:
                    logger.info("✓ 连续无新内容加载，已到达页面底部")
                    break

                # 随机延迟替代固定延迟
                await AntiSpiderHelper.random_delay(1, 2)

                current_count = await self.extract_download_links()

                await self.clean_old_images(keep_last=100)

                if current_count >= self.save_threshold:
                    self.save_links_to_file()
                    self.download_links.clear()
                    break

            logger.info(f"\n✓ 加载完成！总计滚动 {scroll_count} 次，发送 {self.request_count} 次请求")

        except Exception as e:
            logger.error(f"加载流程执行失败: {e}")

    async def close(self):
        """关闭浏览器，释放资源"""
        if self.browser:
            await self.browser.close()
            logger.info("✓ 浏览器已关闭")
        if self.playwright:
            await self.playwright.stop()

    async def start(self):
        """启动爬虫的完整流程"""
        try:
            await self.initialize()
            await self.navigate_to_target()
            await self.run_load_more_flow()

            logger.info("\n=== 页面加载完成，可开始数据爬取 ===")

        except Exception as e:
            logger.error(f"爬虫执行出错: {e}")
        finally:
            if self.download_links:
                self.save_links_to_file()
            await self.close()

    async def clean_old_images(self, keep_last: int = 100):
        """
        清理页面中多余的 img 元素，避免浏览器卡顿
        Args:
            keep_last: 保留最近的图片数量
        """
        try:
            await self.page.evaluate(f"""
                const imgs = document.querySelectorAll("img");
                const extra = imgs.length - {keep_last};
                if (extra > 0) {{
                    for (let i = 0; i < extra; i++) {{
                        imgs[i].remove();
                    }}
                }}
                
            const buttons = document.querySelectorAll('[data-testid="non-sponsored-photo-download-button"]');
            const extra_btns = buttons.length - {keep_last};
            if (extra_btns > 0) {{
                for (let i = 0; i < extra_btns; i++) {{
                    buttons[i].remove();
                }}
            }}
            """)
            logger.debug(f"已清理旧图片节点，保留最新 {keep_last} 张")
        except Exception as e:
            logger.warning(f"清理图片节点失败: {e}")

async def main():
    """主程序入口"""
    scraper = UnsplashScraper(search_keyword="dog", save_threshold=100000)
    # search_keyword为搜索词(people)，save_threshold为保存数量(10000)
    # 由于网页一次加载15个图片，最终保存为比save_threshold大的最小一个15的倍数
    await scraper.start()


if __name__ == "__main__":
    asyncio.run(main())
