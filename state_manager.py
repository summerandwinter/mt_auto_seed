import json
import os
import logging

logger = logging.getLogger("MT_Auto_Seed")

class StateManager:
    """状态管理器，用于持久化程序运行状态"""
    def __init__(self, state_file="state.json"):
        self.state_file = state_file
        self.state = {
            "processed_torrent_ids": set(),
            "last_page_number": 1
        }
        self.load_state()

    def load_state(self):
        """加载之前保存的状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    self.state["processed_torrent_ids"] = set(saved_state.get("processed_torrent_ids", []))
                    self.state["last_page_number"] = saved_state.get("last_page_number", 1)
                logger.info(f"成功加载状态: 已处理 {len(self.state['processed_torrent_ids'])} 个种子，最后处理到第 {self.state['last_page_number']} 页")
            else:
                logger.info("状态文件不存在，使用默认状态")
        except Exception as e:
            logger.error(f"加载状态失败: {str(e)}")
            # 保持默认状态

    def save_state(self):
        """保存当前状态"""
        try:
            saved_state = {
                "processed_torrent_ids": list(self.state["processed_torrent_ids"]),
                "last_page_number": self.state["last_page_number"]
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(saved_state, f, ensure_ascii=False, indent=2)
            logger.info(f"成功保存状态: 已处理 {len(self.state['processed_torrent_ids'])} 个种子，最后处理到第 {self.state['last_page_number']} 页")
        except Exception as e:
            logger.error(f"保存状态失败: {str(e)}")

    def add_processed_torrent(self, torrent_id):
        """添加已处理的种子ID"""
        self.state["processed_torrent_ids"].add(str(torrent_id))

    def is_torrent_processed(self, torrent_id):
        """检查种子是否已处理"""
        return str(torrent_id) in self.state["processed_torrent_ids"]

    def update_last_page(self, page_number):
        """更新最后处理的页码"""
        self.state["last_page_number"] = page_number

    def get_last_page(self):
        """获取最后处理的页码"""
        return self.state["last_page_number"]