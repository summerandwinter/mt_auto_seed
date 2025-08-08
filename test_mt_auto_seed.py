import os
import sys
import json
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import (
    load_config,
    get_mteam_torrents,
    download_torrent,
    add_to_transmission,
    is_torrent_in_transmission,
    process_single_torrent
)
from exceptions import ConfigError, APIError
from state_manager import StateManager

class TestMTAutoSeed(unittest.TestCase):
    def setUp(self):
        # 创建临时目录作为工作目录
        self.temp_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.temp_dir)

        # 创建测试配置文件
        self.test_config = {
            "MTEAM": {
                "COOKIE": "test_cookie",
                "USER_AGENT": "test_agent",
                "BASE_URL": "https://test.m-team.cc"
            },
            "TRANSMISSION": {
                "HOST": "localhost",
                "PORT": 9091,
                "USERNAME": "test_user",
                "PASSWORD": "test_pass"
            },
            "DOWNLOAD": {
                "DIR": os.path.join(self.temp_dir, "torrents"),
                "MAX_COUNT": 10,
                "FIRST_PAGE": 1,
                "REQUEST_INTERVAL": 1
            },
            "LOGGING": {
                "LEVEL": "INFO",
                "FILE": os.path.join(self.temp_dir, "mt_auto_seed.log")
            }
        }
        # 保存配置文件
        with open("config.yaml", "w") as f:
            import yaml
            yaml.dump(self.test_config, f)

        # 创建下载目录
        os.makedirs(self.test_config["DOWNLOAD"]["DIR"], exist_ok=True)

        # 初始化状态管理器
        self.state_manager = StateManager(os.path.join(self.temp_dir, "state.json"))

    def tearDown(self):
        # 恢复工作目录
        os.chdir(self.original_dir)
        # 删除临时目录
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_config(self):
        # 测试正常加载配置
        config = load_config("config.yaml")
        self.assertEqual(config["MTEAM"]["COOKIE"], "test_cookie")
        self.assertEqual(config["TRANSMISSION"]["PORT"], 9091)

        # 测试配置文件不存在
        with self.assertRaises(ConfigError):
            load_config("non_existent_config.yaml")

    @patch("requests.get")
    def test_get_mteam_torrents(self, mock_get):
        # 模拟成功响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": 1, "title": "Test Torrent 1", "small_descr": "Official"},
                {"id": 2, "title": "Test Torrent 2", "small_descr": "Official"}
            ],
            "total_page": 1
        }
        mock_get.return_value = mock_response

        # 测试正常获取种子列表
        torrents = get_mteam_torrents(1)
        self.assertEqual(len(torrents), 2)
        self.assertEqual(torrents[0]["id"], 1)
        self.assertEqual(torrents[1]["title"], "Test Torrent 2")

        # 模拟API错误
        mock_response.status_code = 403
        with self.assertRaises(APIError):
            get_mteam_torrents(1)

    @patch("requests.get")
    def test_download_torrent(self, mock_get):
        # 模拟成功下载
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"test_torrent_content"
        mock_get.return_value = mock_response

        # 测试下载种子
        torrent_file = download_torrent(1)
        self.assertTrue(os.path.exists(torrent_file))
        with open(torrent_file, "rb") as f:
            self.assertEqual(f.read(), b"test_torrent_content")

        # 模拟下载失败
        mock_response.status_code = 404
        with self.assertRaises(Exception):
            download_torrent(999)

    @patch("transmission_rpc.Client")
    def test_add_to_transmission(self, mock_client):
        # 模拟Transmission客户端
        mock_torrent = MagicMock()
        mock_torrent.id = 1
        mock_client.return_value.add_torrent.return_value = mock_torrent

        # 创建测试torrent文件
        test_torrent_path = os.path.join(self.test_config["DOWNLOAD"]["DIR"], "test.torrent")
        with open(test_torrent_path, "w") as f:
            f.write("test_torrent_content")

        # 测试添加到Transmission
        result = add_to_transmission(test_torrent_path)
        self.assertTrue(result)

        # 模拟添加失败
        mock_client.return_value.add_torrent.side_effect = Exception("Add failed")
        result = add_to_transmission(test_torrent_path)
        self.assertFalse(result)

    @patch("transmission_rpc.Client")
    def test_is_torrent_in_transmission(self, mock_client):
        # 模拟存在种子
        mock_torrent = MagicMock()
        mock_torrent.comment = "mtid=1"
        mock_client.return_value.get_torrents.return_value = [mock_torrent]

        # 测试种子存在
        result = is_torrent_in_transmission(1)
        self.assertTrue(result)

        # 测试种子不存在
        mock_client.return_value.get_torrents.return_value = []
        result = is_torrent_in_transmission(999)
        self.assertFalse(result)

    @patch("main.is_torrent_in_transmission")
    @patch("main.download_torrent")
    @patch("main.add_to_transmission")
    def test_process_single_torrent(self, mock_add, mock_download, mock_is_in):
        # 配置模拟
        mock_is_in.return_value = False
        test_torrent_path = os.path.join(self.test_config["DOWNLOAD"]["DIR"], "test.torrent")
        with open(test_torrent_path, "w") as f:
            f.write("test_torrent_content")
        mock_download.return_value = test_torrent_path
        mock_add.return_value = True

        # 测试处理新种子
        torrent = {"id": 1, "title": "Test Torrent"}
        result = process_single_torrent(torrent, 0, self.state_manager)
        self.assertTrue(result)
        self.assertTrue(self.state_manager.is_torrent_processed(1))

        # 测试处理已存在的种子
        mock_is_in.return_value = True
        torrent = {"id": 2, "title": "Existing Torrent"}
        result = process_single_torrent(torrent, 0, self.state_manager)
        self.assertFalse(result)
        self.assertTrue(self.state_manager.is_torrent_processed(2))

        # 测试处理已处理过的种子
        torrent = {"id": 1, "title": "Already Processed"}
        result = process_single_torrent(torrent, 0, self.state_manager)
        self.assertFalse(result)

    def test_state_manager(self):
        # 测试添加和检查已处理种子
        self.state_manager.add_processed_torrent(1)
        self.assertTrue(self.state_manager.is_torrent_processed(1))
        self.assertFalse(self.state_manager.is_torrent_processed(2))

        # 测试页码更新和获取
        self.state_manager.update_last_page(5)
        self.assertEqual(self.state_manager.get_last_page(), 5)

        # 测试状态保存和加载
        self.state_manager.save_state()
        new_state_manager = StateManager(os.path.join(self.temp_dir, "state.json"))
        self.assertTrue(new_state_manager.is_torrent_processed(1))
        self.assertEqual(new_state_manager.get_last_page(), 5)

if __name__ == "__main__":
    unittest.main()