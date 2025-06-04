import logging
from pathlib import Path
from typing import Optional

# 跟踪已创建的logger防止重复初始化
_initialized_loggers = set()

def init_logger(module_name: str, log_dir: Optional[Path] = None) -> logging.Logger:
    """安全初始化模块级日志系统
    
    Args:
        module_name: 模块唯一标识 (如 'build'/'identify')
        log_dir: 日志目录 (默认当前目录)
    """
    # 0. 防止重复初始化
    if module_name in _initialized_loggers:
        return logging.getLogger(f'trcirit.{module_name}')
    
    # 1. 创建唯一命名的logger
    logger = logging.getLogger(f'trcirit.{module_name}')
    
    # 2. 清除可能存在的旧配置
    logger.handlers = []
    logger.propagate = False  # 阻止传播到root logger
    
    # 3. 配置日志路径
    log_dir = log_dir or Path.cwd()
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f'trcirit_{module_name}.log'

    # 4. 创建文件handler（仅在首次运行时创建文件）
    file_handler = logging.FileHandler(
        filename=str(log_file),
        mode='w', 
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
  
    # 5. 应用配置
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    _initialized_loggers.add(module_name)
    return logger

# import logging
# from pathlib import Path

# log init

# def init_logger(log_name: str = 'trcirit'):
#     """Initialize module-specific logger
    
#     Args:
#         log_name: Unique identifier for logger (e.g. 'identify')
    
#     Returns:
#         Configured Logger instance
#     """

#     # 1. 创建唯一命名的logger
#     logger = logging.getLogger(f'trcirit.{log_name}')
    
#     # 2. 完全重置这个logger（关键步骤）
#     logger.handlers = []
#     logger.propagate = False
    
#     # 3. 配置专属文件handler
#     log_file = Path.cwd() / f'trcirit_{log_name}.log'
#     file_handler = logging.FileHandler(
#         filename=str(log_file),
#         mode='w',  # 每次运行覆盖
#         encoding='utf-8'
#     )
#     file_handler.setFormatter(logging.Formatter(
#         '%(asctime)s [%(levelname)s] %(message)s',
#         datefmt='%Y-%m-%d %H:%M:%S'
#     ))
    
#     # 5. 设置日志级别并添加handler
#     logger.setLevel(logging.INFO)
#     logger.addHandler(file_handler)
    
#     return logger


# def init_logger(log_name: str = 'trcirit'):
#     """Initialize global logger
    
#     Args:
#         log_name: Prefix for log filename (e.g. 'trcirit_identify.log')
#     """
#     log_file = Path.cwd() / f'{log_name}.log'
    
#     log_file.parent.mkdir(exist_ok=True)
    
#     logging.basicConfig(
#         filename=str(log_file),
#         filemode='w',
#         level=logging.INFO,
#         format='%(asctime)s [%(levelname)s] %(message)s',
#         datefmt='%Y-%m-%d %H:%M:%S',
#         force=True
#     )

