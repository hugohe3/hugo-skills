#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国坐标系转换库

支持以下坐标系之间的相互转换：
- WGS84: 国际标准坐标系（GPS坐标）
- GCJ02: 火星坐标系（国测局坐标，高德、谷歌中国使用）
- BD09: 百度坐标系（百度地图使用）

依赖：仅标准库（math）。命令行入口见同目录 convert.py。

使用方法：

方式一：使用类方法（推荐）
    from coordinate_converter import CoordinateConverter

    # WGS84 转 GCJ02
    gcj02_lon, gcj02_lat = CoordinateConverter.wgs84_to_gcj02(120.0, 30.0)

    # GCJ02 转 WGS84
    wgs84_lon, wgs84_lat = CoordinateConverter.gcj02_to_wgs84(120.0, 30.0)

    # GCJ02 转 BD09
    bd09_lon, bd09_lat = CoordinateConverter.gcj02_to_bd09(120.0, 30.0)

    # BD09 转 GCJ02
    gcj02_lon, gcj02_lat = CoordinateConverter.bd09_to_gcj02(120.0, 30.0)

    # WGS84 转 BD09
    bd09_lon, bd09_lat = CoordinateConverter.wgs84_to_bd09(120.0, 30.0)

    # BD09 转 WGS84
    wgs84_lon, wgs84_lat = CoordinateConverter.bd09_to_wgs84(120.0, 30.0)

方式二：使用函数式接口（向后兼容）
    from coordinate_converter import wgs84_to_gcj02, gcj02_to_wgs84

    # WGS84 转 GCJ02
    gcj02_lon, gcj02_lat = wgs84_to_gcj02(120.0, 30.0)

    # GCJ02 转 WGS84
    wgs84_lon, wgs84_lat = gcj02_to_wgs84(120.0, 30.0)

作者: hugohe3
日期: 2025年10月1日
"""

import math
from typing import Tuple

# 坐标系转换常量
X_PI = math.pi * 3000.0 / 180.0  # 百度坐标系转换常量
PI = math.pi  # 圆周率
A = 6378245.0  # 长半轴（克拉索夫斯基椭球参数）
EE = 0.00669342162296594323  # 偏心率平方

# 中国境内经纬度范围
CHINA_LON_MIN = 73.66
CHINA_LON_MAX = 135.05
CHINA_LAT_MIN = 3.86
CHINA_LAT_MAX = 53.55


class CoordinateConverter:
    """坐标转换器类。

    提供中国常用坐标系之间的相互转换方法，包括 WGS84、GCJ02 和 BD09。
    所有方法均为静态方法或类方法，可直接通过类名调用。

    .. note::
       - WGS84: 国际标准GPS坐标系
       - GCJ02: 中国火星坐标系（国测局标准）
       - BD09: 百度地图坐标系

    :Example:

    >>> # 使用类方法进行转换
    >>> lon, lat = CoordinateConverter.wgs84_to_gcj02(120.0, 30.0)
    >>> print(f"GCJ02: ({lon}, {lat})")
    """

    @staticmethod
    def is_in_china(lon: float, lat: float) -> bool:
        """判断坐标是否在中国境内。

        根据经纬度范围判断坐标点是否位于中国大陆境内，用于决定是否需要进行坐标系偏移转换。

        :param lon: 经度
        :param lat: 纬度
        :return: 如果坐标在中国境内返回 True，否则返回 False

        .. note::
           中国境内经纬度范围：经度 73.66° ~ 135.05°，纬度 3.86° ~ 53.55°
        """
        return (CHINA_LON_MIN <= lon <= CHINA_LON_MAX and
                CHINA_LAT_MIN <= lat <= CHINA_LAT_MAX)

    @staticmethod
    def _transform_lon(lon: float, lat: float) -> float:
        """经度转换的辅助函数。

        用于 WGS84 与 GCJ02 坐标系之间的经度偏移计算，基于国测局的加密算法实现。

        :param lon: 经度
        :param lat: 纬度
        :return: 转换后的经度偏移量

        .. note::
           这是内部辅助方法，不应直接调用。使用公开的转换方法如 wgs84_to_gcj02() 代替。
        """
        ret = (300.0 + lon + 2.0 * lat + 0.1 * lon * lon +
               0.1 * lon * lat + 0.1 * math.sqrt(abs(lon)))
        ret += (20.0 * math.sin(6.0 * lon * PI) +
                20.0 * math.sin(2.0 * lon * PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lon * PI) +
                40.0 * math.sin(lon / 3.0 * PI)) * 2.0 / 3.0
        ret += (150.0 * math.sin(lon / 12.0 * PI) +
                300.0 * math.sin(lon / 30.0 * PI)) * 2.0 / 3.0
        return ret

    @staticmethod
    def _transform_lat(lon: float, lat: float) -> float:
        """纬度转换的辅助函数。

        用于 WGS84 与 GCJ02 坐标系之间的纬度偏移计算，基于国测局的加密算法实现。

        :param lon: 经度
        :param lat: 纬度
        :return: 转换后的纬度偏移量

        .. note::
           这是内部辅助方法，不应直接调用。使用公开的转换方法如 wgs84_to_gcj02() 代替。
        """
        ret = (-100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat +
               0.1 * lon * lat + 0.2 * math.sqrt(abs(lon)))
        ret += (20.0 * math.sin(6.0 * lon * PI) +
                20.0 * math.sin(2.0 * lon * PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lat * PI) +
                40.0 * math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
        ret += (160.0 * math.sin(lat / 12.0 * PI) +
                320.0 * math.sin(lat * PI / 30.0)) * 2.0 / 3.0
        return ret

    @classmethod
    def wgs84_to_gcj02(cls, lon: float, lat: float) -> Tuple[float, float]:
        """WGS84 坐标系转 GCJ02 火星坐标系。

        将国际标准 GPS 坐标转换为中国国测局的火星坐标系。如果坐标不在中国境内，则不进行偏移处理。

        :param lon: WGS84 经度
        :param lat: WGS84 纬度
        :return: (GCJ02经度, GCJ02纬度)

        .. note::
           GCJ02 坐标系用于高德地图、腾讯地图、谷歌中国地图等。
        """
        # 如果不在中国境内，不进行偏移
        if not cls.is_in_china(lon, lat):
            return (lon, lat)

        d_lon = cls._transform_lon(lon - 105.0, lat - 35.0)
        d_lat = cls._transform_lat(lon - 105.0, lat - 35.0)

        rad_lat = lat / 180.0 * PI
        magic = math.sin(rad_lat)
        magic = 1 - EE * magic * magic
        sqrt_magic = math.sqrt(magic)

        d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
        d_lon = (d_lon * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)

        mg_lat = lat + d_lat
        mg_lon = lon + d_lon

        return (mg_lon, mg_lat)

    @classmethod
    def gcj02_to_wgs84(cls, lon: float, lat: float) -> Tuple[float, float]:
        """GCJ02 火星坐标系转 WGS84 坐标系。

        将中国国测局的火星坐标系转换为国际标准 GPS 坐标。采用精确算法进行转换，如果坐标不在中国境内，则不进行偏移处理。

        :param lon: GCJ02 经度
        :param lat: GCJ02 纬度
        :return: (WGS84经度, WGS84纬度)
        """
        # 如果不在中国境内，不进行偏移
        if not cls.is_in_china(lon, lat):
            return (lon, lat)

        d_lon = cls._transform_lon(lon - 105.0, lat - 35.0)
        d_lat = cls._transform_lat(lon - 105.0, lat - 35.0)

        rad_lat = lat / 180.0 * PI
        magic = math.sin(rad_lat)
        magic = 1 - EE * magic * magic
        sqrt_magic = math.sqrt(magic)

        d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
        d_lon = (d_lon * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)

        mg_lat = lat + d_lat
        mg_lon = lon + d_lon

        return (lon * 2 - mg_lon, lat * 2 - mg_lat)

    @staticmethod
    def gcj02_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
        """GCJ02 火星坐标系转 BD09 百度坐标系。

        :param lon: GCJ02 经度
        :param lat: GCJ02 纬度
        :return: (BD09经度, BD09纬度)

        .. note::
           BD09 坐标系专用于百度地图服务。
        """
        z = math.sqrt(lon * lon + lat * lat) + 0.00002 * math.sin(lat * X_PI)
        theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * X_PI)
        bd_lon = z * math.cos(theta) + 0.0065
        bd_lat = z * math.sin(theta) + 0.006
        return (bd_lon, bd_lat)

    @staticmethod
    def bd09_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
        """BD09 百度坐标系转 GCJ02 火星坐标系。

        :param lon: BD09 经度
        :param lat: BD09 纬度
        :return: (GCJ02经度, GCJ02纬度)
        """
        x = lon - 0.0065
        y = lat - 0.006
        z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
        theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
        gcj_lon = z * math.cos(theta)
        gcj_lat = z * math.sin(theta)
        return (gcj_lon, gcj_lat)

    @classmethod
    def wgs84_to_bd09(cls, lon: float, lat: float) -> Tuple[float, float]:
        """WGS84 坐标系转 BD09 百度坐标系。

        将国际标准 GPS 坐标直接转换为百度地图坐标系。内部通过 WGS84 -> GCJ02 -> BD09 两步转换实现。

        :param lon: WGS84 经度
        :param lat: WGS84 纬度
        :return: (BD09经度, BD09纬度)
        """
        gcj_lon, gcj_lat = cls.wgs84_to_gcj02(lon, lat)
        return cls.gcj02_to_bd09(gcj_lon, gcj_lat)

    @classmethod
    def bd09_to_wgs84(cls, lon: float, lat: float) -> Tuple[float, float]:
        """BD09 百度坐标系转 WGS84 坐标系。

        将百度地图坐标系直接转换为国际标准 GPS 坐标。内部通过 BD09 -> GCJ02 -> WGS84 两步转换实现。

        :param lon: BD09 经度
        :param lat: BD09 纬度
        :return: (WGS84经度, WGS84纬度)
        """
        gcj_lon, gcj_lat = cls.bd09_to_gcj02(lon, lat)
        return cls.gcj02_to_wgs84(gcj_lon, gcj_lat)

    @classmethod
    def convert(cls, lon: float, lat: float,
                src: str, dst: str) -> Tuple[float, float]:
        """按源坐标系与目标坐标系动态转换。

        统一入口，依据 ``src`` / ``dst`` 选择对应的转换方法，支持任意两种坐标系互转。
        当源与目标相同时原样返回。

        :param lon: 经度
        :param lat: 纬度
        :param src: 源坐标系标识（wgs84 / gcj02 / bd09，大小写不限）
        :param dst: 目标坐标系标识（wgs84 / gcj02 / bd09，大小写不限）
        :return: (目标经度, 目标纬度)
        :raises ValueError: 当坐标系标识无法识别时抛出
        """
        src_key = normalize_system(src)
        dst_key = normalize_system(dst)
        if src_key == dst_key:
            return (lon, lat)
        method = getattr(cls, f"{src_key}_to_{dst_key}")
        return method(lon, lat)


# 坐标系别名归一化映射
_SYSTEM_ALIASES = {
    "wgs84": "wgs84", "wgs": "wgs84", "gps": "wgs84", "84": "wgs84",
    "gcj02": "gcj02", "gcj": "gcj02", "gaode": "gcj02", "amap": "gcj02",
    "高德": "gcj02", "google": "gcj02", "tencent": "gcj02", "腾讯": "gcj02",
    "火星": "gcj02", "02": "gcj02",
    "bd09": "bd09", "bd": "bd09", "baidu": "bd09", "百度": "bd09", "09": "bd09",
}


def normalize_system(name: str) -> str:
    """将坐标系名称或别名归一化为标准标识。

    支持英文缩写、平台名与中文别名（如 ``高德`` -> ``gcj02``）。

    :param name: 用户输入的坐标系名称
    :return: 标准标识，取值为 ``wgs84`` / ``gcj02`` / ``bd09``
    :raises ValueError: 当名称无法识别时抛出
    """
    key = str(name).strip().lower()
    if key in _SYSTEM_ALIASES:
        return _SYSTEM_ALIASES[key]
    raise ValueError(
        f"无法识别的坐标系: {name!r}（支持 wgs84 / gcj02 / bd09 及其常见别名）")


# 为了向后兼容，提供函数式接口
def wgs84_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
    """WGS84 转 GCJ02（向后兼容接口）。

    .. deprecated:: 推荐使用 CoordinateConverter.wgs84_to_gcj02 类方法
    """
    return CoordinateConverter.wgs84_to_gcj02(lon, lat)


def gcj02_to_wgs84(lon: float, lat: float) -> Tuple[float, float]:
    """GCJ02 转 WGS84（向后兼容接口）。

    .. deprecated:: 推荐使用 CoordinateConverter.gcj02_to_wgs84 类方法
    """
    return CoordinateConverter.gcj02_to_wgs84(lon, lat)


def gcj02_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
    """GCJ02 转 BD09（向后兼容接口）。

    .. deprecated:: 推荐使用 CoordinateConverter.gcj02_to_bd09 类方法
    """
    return CoordinateConverter.gcj02_to_bd09(lon, lat)


def bd09_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
    """BD09 转 GCJ02（向后兼容接口）。

    .. deprecated:: 推荐使用 CoordinateConverter.bd09_to_gcj02 类方法
    """
    return CoordinateConverter.bd09_to_gcj02(lon, lat)


def wgs84_to_bd09(lon: float, lat: float) -> Tuple[float, float]:
    """WGS84 转 BD09（向后兼容接口）。

    .. deprecated:: 推荐使用 CoordinateConverter.wgs84_to_bd09 类方法
    """
    return CoordinateConverter.wgs84_to_bd09(lon, lat)


def bd09_to_wgs84(lon: float, lat: float) -> Tuple[float, float]:
    """BD09 转 WGS84（向后兼容接口）。

    .. deprecated:: 推荐使用 CoordinateConverter.bd09_to_wgs84 类方法
    """
    return CoordinateConverter.bd09_to_wgs84(lon, lat)
