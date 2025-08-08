class MTAutoSeedException(Exception):
    """M-Team自动种子工具基础异常类"""
    pass


class ConfigError(MTAutoSeedException):
    """配置相关错误"""
    pass


class APIError(MTAutoSeedException):
    """API请求相关错误"""
    pass


class DownloadError(MTAutoSeedException):
    """种子下载相关错误"""
    pass


class TransmissionError(MTAutoSeedException):
    """Transmission相关错误"""
    pass


class HashError(MTAutoSeedException):
    """哈希计算相关错误"""
    pass