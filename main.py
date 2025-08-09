import os
import sys
import time
import yaml
import logging
import requests
import transmission_rpc
import concurrent.futures
from torrentool.api import Torrent
from exceptions import ConfigError, APIError, DownloadError, TransmissionError, HashError
from state_manager import StateManager

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mt_auto_seed.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("MT_Auto_Seed")

# 读取配置文件
def load_config(config_path="config.yaml"):
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"配置文件不存在: {config_path}")
    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件格式错误: {str(e)}")

# 加载配置
CONFIG = load_config()

# 全局Transmission客户端实例
TR_CLIENT = None

# 从配置中提取参数
MT_USER_AGENT = CONFIG['mt']['user_agent']
MT_API_KEY = CONFIG['mt']['api_key']
TEAMS = CONFIG['mt']['teams']

TR_HOST = CONFIG['transmission']['host']
TR_PORT = CONFIG['transmission']['port']
TR_USER = CONFIG['transmission']['username']
TR_PASSWORD = CONFIG['transmission']['password']
SAVE_PATH = CONFIG['transmission']['save_path']
LABELS = CONFIG['transmission']['labels']

DOWNLOAD_DIR = CONFIG['download']['dir']
REQUEST_INTERVAL = CONFIG['download']['request_interval']
MAX_DOWNLOAD_COUNT = CONFIG['download']['max_download_count']
PAGE_SIZE = CONFIG['download']['page_size']
MAX_RETRIES = CONFIG['download']['max_retries']
INITIAL_RETRY_DELAY = CONFIG['download']['initial_retry_delay']
MAX_WORKERS = CONFIG['download']['max_workers']

def get_mteam_torrents(page_number=1):
    """获取馒头官种列表（通过API接口）"""
    url = "https://api2.m-team.cc/api/torrent/search"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": MT_API_KEY,
        "User-Agent": MT_USER_AGENT
    }
    
    # 请求体
    payload = {
        "mode": "normal",
        "visible": 1,
        "categories": [],
        "teams": TEAMS,
        "sortDirection": "ASC",
        "sortField": "SIZE",
        "pageNumber": page_number,
        "pageSize": PAGE_SIZE
    }
    
    try:
        logger.info(f"正在请求第 {page_number} 页种子列表")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # 检查响应是否成功
        if data.get("code") != "0":
            error_msg = f"API请求失败: {data.get('message', '未知错误')}"
            logger.error(error_msg)
            raise APIError(error_msg)
        
        torrents = []
        # 提取种子信息
        for item in data.get("data", {}).get("data", []):
            torrents.append({
                "id": item.get("id"),
                "title": item.get("name")
            })
        
        logger.info(f"通过API获取到 {len(torrents)} 个种子")
        return torrents
    
    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求错误: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)
    except ValueError as e:
        error_msg = f"响应解析错误: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)
    except Exception as e:
        error_msg = f"获取种子列表失败: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)

def download_torrent(torrent_id, state_manager):
    """下载种子文件（通过API接口）"""
    # 生成固定格式的文件名
    filename = f"mteam.{torrent_id}.torrent"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    # 检查文件是否已存在
    if os.path.exists(filepath):
        logger.info(f"种子文件已存在，跳过下载: {filename}")
        return filepath
    
    # 生成下载token的API
    token_url = f"https://api2.m-team.cc/api/torrent/genDlToken?id={torrent_id}"
    headers = {
        "x-api-key": MT_API_KEY,
        "User-Agent": MT_USER_AGENT
    }
    
    try:
        # 请求下载token
        logger.info(f"正在请求种子 {torrent_id} 的下载token")
        token_response = requests.post(token_url, headers=headers, timeout=30)
        token_response.raise_for_status()
        
        token_data = token_response.json()
        
        # 检查响应是否成功
        if token_data.get("code") != "0":
            error_msg = f"获取下载token失败: {token_data.get('message', '未知错误')}"
            logger.error(error_msg)
            raise APIError(error_msg)
        
        # 获取下载链接
        download_url = token_data.get("data")
        if not download_url:
            error_msg = "未获取到有效的下载链接"
            logger.error(error_msg)
            raise APIError(error_msg)
        
        # 下载种子文件，处理请求过于频繁的情况
        logger.info(f"正在下载种子文件: {filename}")
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                response = requests.get(download_url, headers={"User-Agent": MT_USER_AGENT}, timeout=30)
                response.raise_for_status()
                
                # 检查是否是请求过于频繁的错误
                try:
                    json_response = response.json()
                    if json_response.get("code") == 1:
                        message = json_response.get("message", "")
                        if "今日下載配額用盡" in message:
                            logger.error(f"下载配额已用尽: {message}")
                            state_manager.save_state()
                            logger.info("程序结束")
                            # 使用os._exit()强制终止进程，确保在多线程环境中能够退出
                            os._exit(1)
                        elif "請求過於頻繁" in message:
                            delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                            logger.warning(f"请求过于频繁，{delay}秒后重试... (重试次数: {retry_count+1}/{MAX_RETRIES})\n")
                            time.sleep(delay)
                            retry_count += 1
                            continue
                except ValueError:
                    # 不是JSON响应，说明下载成功
                    pass
                
                # 下载成功，跳出循环
                break
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP错误: {str(e)}")
                # 检查响应内容是否包含下载配额用尽或请求过于频繁的信息
                response_text = response.text
                if "今日下載配額用盡" in response_text:
                    logger.error(f"下载配额已用尽: {response_text}")
                    logger.info("保存最终状态...")
                    state_manager.save_state()
                    logger.info("程序结束")
                    # 使用os._exit()强制终止进程，确保在多线程环境中能够退出
                    os._exit(1)
                elif "請求過於頻繁" in response_text:
                    delay = INITIAL_RETRY_DELAY * (2 ** retry_count)
                    logger.warning(f"请求过于频繁，{delay}秒后重试... (重试次数: {retry_count+1}/{MAX_RETRIES})\n")
                    time.sleep(delay)
                    retry_count += 1
                else:
                    # 其他HTTP错误，直接抛出
                    raise DownloadError(f"HTTP错误: {str(e)}")
            except Exception as e:
                logger.error(f"下载错误: {str(e)}")
                raise DownloadError(f"下载错误: {str(e)}")
        else:
            # 达到最大重试次数仍然失败
            error_msg = f"达到最大重试次数({MAX_RETRIES})，下载失败"
            logger.error(error_msg)
            raise DownloadError(error_msg)
        
        # 保存种子文件
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"已下载: {filename}")
        return filepath
    
    except Exception as e:
        logger.error(f"下载种子失败(ID: {torrent_id}): {str(e)}")
        return None

def get_torrent_hash(torrent_file):
    """计算种子文件的info hash"""
    try:
        # 使用torrentool获取种子hash
        torrent = Torrent.from_file(torrent_file)
        return torrent.info_hash
    except Exception as e:
        logger.error(f"计算种子哈希失败: {str(e)}")
        raise HashError(f"计算种子哈希失败: {str(e)}")

def init_transmission_client():
    """初始化Transmission客户端连接"""
    global TR_CLIENT, TRANSMISSION_HASH_CACHE, LAST_CACHE_UPDATE
    if TR_CLIENT is None:
        try:
            logger.info(f"尝试连接到Transmission: {TR_HOST}:{TR_PORT}")
            TR_CLIENT = transmission_rpc.Client(
                host=TR_HOST,
                port=TR_PORT,
                username=TR_USER,
                password=TR_PASSWORD
            )
            logger.info("成功连接到Transmission")
            return True
        except Exception as e:
            logger.error(f"连接Transmission失败: {str(e)}")
            raise TransmissionError(f"连接Transmission失败: {str(e)}")
    return True

# 添加全局变量用于缓存种子哈希值
TRANSMISSION_HASH_CACHE = set()
CACHE_EXPIRY_TIME = 300  # 缓存过期时间（秒）
LAST_CACHE_UPDATE = 0


def update_transmission_cache():
    """更新Transmission种子哈希缓存"""
    global TR_CLIENT, TRANSMISSION_HASH_CACHE, LAST_CACHE_UPDATE
    try:
        # 确保客户端已初始化
        if not TR_CLIENT:
            init_transmission_client()

        logger.info("更新Transmission种子哈希缓存...")
        # 获取所有种子，然后提取哈希值
        torrent_hashes = {torrent.hashString.lower() for torrent in TR_CLIENT.get_torrents()} 
        TRANSMISSION_HASH_CACHE = torrent_hashes
        LAST_CACHE_UPDATE = time.time()
        logger.info(f"缓存更新完成，当前种子数量: {len(TRANSMISSION_HASH_CACHE)}")
    except Exception as e:
        logger.error(f"更新缓存失败: {str(e)}")


def is_torrent_in_transmission(torrent_id):
    """检查种子是否已在Transmission中（通过哈希对比）"""
    global TR_CLIENT
    try:
        # 确保客户端已初始化
        if not TR_CLIENT:
            init_transmission_client()

        # 检查缓存是否过期，过期则更新
        current_time = time.time()
        if current_time - LAST_CACHE_UPDATE > CACHE_EXPIRY_TIME:
            update_transmission_cache()
        torrent_hashes = TRANSMISSION_HASH_CACHE

        # 构建本地种子文件路径
        torrent_file = os.path.join(DOWNLOAD_DIR, f"mteam.{torrent_id}.torrent")

        # 如果本地文件存在，计算哈希值并检查
        if os.path.exists(torrent_file):
            try:
                local_hash = get_torrent_hash(torrent_file)
                if local_hash and local_hash.lower() in torrent_hashes:
                    logger.info(f"种子已在Transmission中（哈希匹配）: {torrent_file}")
                    return True
            except HashError as e:
                logger.warning(f"计算哈希失败，跳过检查: {str(e)}")

        # 本地文件不存在或哈希不匹配
        return False
    except Exception as e:
        logger.error(f"检查Transmission种子失败: {str(e)}")
        # 连接可能已断开，尝试重新初始化
        TR_CLIENT = None
        return False

def add_to_transmission(torrent_file):
    """添加种子到Transmission"""
    global TR_CLIENT, TRANSMISSION_HASH_CACHE, LAST_CACHE_UPDATE
    try:
        # 确保客户端已初始化
        if not TR_CLIENT:
            init_transmission_client()

        # 检查种子文件是否存在
        if not os.path.exists(torrent_file):
            error_msg = f"种子文件不存在: {torrent_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        # 检查文件大小
        file_size = os.path.getsize(torrent_file)
        if file_size == 0:
            error_msg = "种子文件为空"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 尝试以二进制方式读取种子文件内容
        with open(torrent_file, 'rb') as f:
            torrent_content = f.read()

        # 添加种子
        try:
            torrent = TR_CLIENT.add_torrent(
                torrent=torrent_content,
                download_dir=SAVE_PATH,
                labels=LABELS,
                paused=False
            )
            logger.info(f"已添加到Transmission: {torrent.name}")
            
            # 添加种子哈希到缓存
            torrent_hash = torrent.hashString.lower()
            if torrent_hash not in TRANSMISSION_HASH_CACHE:
                TRANSMISSION_HASH_CACHE.add(torrent_hash)
                LAST_CACHE_UPDATE = time.time()
                logger.info(f"已将种子哈希 {torrent_hash} 添加到缓存")
            
            return True
        except Exception as e1:
            logger.error(f"添加种子到Transmission失败: {str(e1)}")
            raise TransmissionError(f"添加种子到Transmission失败: {str(e1)}")

    except Exception as e:
        logger.error(f"操作Transmission失败: {str(e)}")
        # 连接可能已断开，尝试重新初始化
        TR_CLIENT = None
        return False

def process_single_torrent(torrent, total_downloaded, state_manager):
    """处理单个种子"""
    logger.info(f"处理中 [{total_downloaded+1}/{MAX_DOWNLOAD_COUNT}]: {torrent['title']}")

    # 检查种子是否已处理过
    if state_manager.is_torrent_processed(torrent['id']):
        logger.info(f"种子 {torrent['id']} 已处理过，跳过")
        return False

    # 检查种子是否已在Transmission中
    if is_torrent_in_transmission(torrent['id']):
        logger.info("种子已在Transmission中，跳过处理")
        # 标记为已处理
        state_manager.add_processed_torrent(torrent['id'])
        return False

    # 下载种子文件
    torrent_file = download_torrent(torrent['id'], state_manager)

    if torrent_file:
        # 添加到Transmission
        if add_to_transmission(torrent_file):
            logger.info("添加成功")
            # 遵守请求间隔
            time.sleep(REQUEST_INTERVAL)
        else:
            logger.error("添加失败")
        # 标记为已处理
        state_manager.add_processed_torrent(torrent['id'])
        return True
    return False

def main():
    # 确保下载目录存在
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # 初始化状态管理器
    state_manager = StateManager()

    # 初始化Transmission客户端
    try:
        init_transmission_client()
        # 初始化种子哈希缓存
        update_transmission_cache()
    except TransmissionError as e:
        logger.error(f"无法连接到Transmission，程序退出: {str(e)}")
        return

    total_downloaded = 0
    # 从上次停止的页码开始
    page_number = state_manager.get_last_page()

    try:
        while total_downloaded < MAX_DOWNLOAD_COUNT:
            logger.info(f"正在获取第 {page_number} 页馒头官种列表...")
            
            # 获取官种列表（指定页码）
            try:
                torrents = get_mteam_torrents(page_number)
            except APIError as e:
                logger.error(f"获取种子列表失败: {str(e)}")
                # 等待一段时间后重试
                time.sleep(REQUEST_INTERVAL)
                continue
            
            if not torrents:
                logger.info("未找到官方种子或已到达最后一页")
                break
            
            logger.info(f"第 {page_number} 页找到 {len(torrents)} 个官方种子")
            
            # 批量处理种子 - 使用线程池并行处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for torrent in torrents:
                    if total_downloaded >= MAX_DOWNLOAD_COUNT:
                        break
                    # 跳过已处理的种子
                    if state_manager.is_torrent_processed(torrent['id']):
                        logger.info(f"种子 {torrent['id']} 已处理过，跳过")
                        continue
                    future = executor.submit(process_single_torrent, torrent, total_downloaded, state_manager)
                    futures.append(future)
                    total_downloaded += 1
                
                # 等待所有任务完成
                concurrent.futures.wait(futures)
                
            
            # 更新最后处理的页码
            state_manager.update_last_page(page_number)
            # 保存状态
            state_manager.save_state()
            
            # 进入下一页
            page_number += 1
    
    except KeyboardInterrupt:
        logger.info("程序已被用户中断")
    finally:
        # 保存最终状态
        state_manager.save_state()
    
    logger.info(f"共下载 {total_downloaded} 个种子")

if __name__ == "__main__":
    main()