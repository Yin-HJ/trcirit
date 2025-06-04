import subprocess
import logging
from typing import Tuple
import shutil
from typing import Tuple, Optional 

def check_java_environment(java_path: Optional[str] = None) -> Tuple[int, int]:
    """Verify Java environment meets requirements (Recommended >1.7)
    Args:
        java_path: Java path specified by user

    Returns:
        Tuple[int, int]: Detected Java version as (major, minor)
        
    Raises:
        RuntimeError: If Java is not available or version too old
    """
    try:
        # 获取Java可执行文件完整路径
        resolved_java_path = _resolve_java_path(java_path)            

        # 检查版本
        result = subprocess.run(
            [resolved_java_path, "-version"],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            check=True
        )
        
        version_line = result.stderr.split('\n')[0]
        version_str = _parse_java_version(version_line)
        major, minor = int(version_str[0]), int(version_str[1]) if len(version_str) > 1 else 0
        
        if major == 1 and minor <= 7:
            logging.warning(f"JRE version > 1.7 is recommended (found {major}.{minor})")
        elif major < 1:
            raise RuntimeError(f"Unsupported Java version: {major}.{minor}")
                
        logging.info(f"Java version: {major}.{minor} (Recommended >1.7)")
        return (major, minor)
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Java runtime not found or not executable")
    except Exception as e:
        raise RuntimeError(f"Java version check failed: {str(e)}")

def _resolve_java_path(user_path: Optional[str]) -> str:
    """parse java path"""
    if user_path:
        return user_path  
    
    java_path = shutil.which("java")
    if not java_path:
        raise RuntimeError("Java not found in system PATH. Specify with --java-path")
    return java_path

def _parse_java_version(version_line: str) -> list:
    """Parse version string from java -version output"""
    if '"' in version_line:
        return version_line.split('"')[1].split('.')[:2]
    elif 'openjdk' in version_line.lower():
        return version_line.split(' ')[2].split('.')[:2]
    return []