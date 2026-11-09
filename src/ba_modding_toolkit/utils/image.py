# utils/image.py
"""图像处理工具（原 ImageUtils 类打散为模块级函数）"""

import math

from PIL import Image, ImageChops, ImageStat

# 贴图一致性宽容阈值（MSE）：bundle 内压缩纹理解码后与源图存在轻微像素差异，
# MSE 低于该阈值视为一致；0 = 逐字节严格比较
DEFAULT_TEXTURE_MSE_THRESHOLD = 20.0


def bleed_image(image: Image.Image, iteration: int = 8) -> Image.Image:
    """
    对图像进行 Bleed 处理。
    """
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    width, height = image.size
    original_alpha = image.getchannel('A')

    # 优化：使用 LUT 代替逐像素操作
    lut = [255] * 256
    lut[0] = 0
    mask = original_alpha.point(lut)

    # 优化：如果没有完全透明像素，直接返回
    if original_alpha.getextrema()[0] > 0:
        return image

    current_canvas = image.copy()

    for _ in range(iteration):
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]

        for dx, dy in offsets:
            shifted = current_canvas.transform(
                (width, height),
                Image.Transform.AFFINE,
                (1, 0, -dx, 0, 1, -dy)
            )
            layer.alpha_composite(shifted)

        layer.alpha_composite(current_canvas)
        current_canvas = layer

    result = Image.composite(image, current_canvas, mask)
    r, g, b, _ = result.split()
    final = Image.merge("RGBA", (r, g, b, original_alpha))

    return final


def texture_mse(img1: Image.Image, img2: Image.Image, alpha_epsilon: int = 8) -> float:
    """计算两图的均方误差（MSE），用于带容差的贴图一致性判定

    bundle 内压缩纹理解码后与源图存在像素级差异，逐字节比较会误判为不同；
    调用方以 MSE ≤ 阈值判定"视为一致"（见 asset.is_same_texture）。
    透明像素（两侧 alpha 均 ≤ alpha_epsilon）的 RGB 压缩后不确定，不计入统计；
    alpha 通道差异始终计入。

    Returns:
        MSE 值；完全一致返回 0.0，尺寸不同返回 math.inf（视为完全不同）
    """
    if img1.size != img2.size:
        return math.inf
    if img1.mode == img2.mode and img1.tobytes() == img2.tobytes():
        return 0.0  # 完全一致快路径，零成本

    a1, a2 = img1.convert("RGBA"), img2.convert("RGBA")
    r, g, b, a = ImageChops.difference(a1, a2).split()
    # 双侧 alpha 的最大值做掩码：仅 RGB 被掩（透明区域 RGB 无意义），alpha 差异保留
    mask = ImageChops.lighter(a1.getchannel("A"), a2.getchannel("A")).point(
        lambda v: 255 if v > alpha_epsilon else 0
    )
    rgb = Image.merge("RGBA", (
        ImageChops.multiply(r, mask),
        ImageChops.multiply(g, mask),
        ImageChops.multiply(b, mask),
        a,
    ))
    stat = ImageStat.Stat(rgb)
    return sum(stat.sum2) / (a1.width * a1.height * 4)


def is_same_texture(img1: Image.Image, img2: Image.Image) -> bool:
    """带容差的贴图一致性判定：MSE 不超过默认阈值即视为一致"""
    return texture_mse(img1, img2) <= DEFAULT_TEXTURE_MSE_THRESHOLD
