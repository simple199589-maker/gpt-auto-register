"""浏览器驱动装配能力。AI by zb"""

from ._legacy import SafeChrome, create_driver, get_local_chrome_major_version

__all__ = [
    "SafeChrome",
    "create_driver",
    "get_local_chrome_major_version",
]
