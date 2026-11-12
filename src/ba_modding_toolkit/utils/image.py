# utils/image.py
"""图像处理工具（原 ImageUtils 类打散为模块级函数）"""

import math

from PIL import Image, ImageChops, ImageStat

# 贴图一致性宽容阈值（MSE）：bundle 内压缩纹理解码后与源图存在轻微像素差异，
# MSE 低于该阈值视为一致；0 = 逐字节严格比较
DEFAULT_TEXTURE_MSE_THRESHOLD = 20.0

# 尺寸轻微不同（如 Spine 渲染 trim）时允许比较的宽高比相对差异：
# 超过该比例说明两张图构图已不同，缩放后再比较没有意义
DEFAULT_COMPARE_ASPECT_TOLERANCE = 0.02

# Bleed 的 alpha 阈值：alpha 不超过该值的像素视觉上等同于透明，
# 但其 RGB 往往不可靠（导出/压缩残留），会被线性过滤与 mipmap 带进可见区域
DEFAULT_BLEED_ALPHA_THRESHOLD = 5


def bleed_image(
    image: Image.Image,
    iteration: int = 8,
    threshold: int = DEFAULT_BLEED_ALPHA_THRESHOLD,
) -> Image.Image:
    """
    对图像进行 Bleed 处理。

    将 alpha 不超过 alpha_threshold 的像素视为不可见，用周边颜色扩散覆盖其 RGB，
    alpha 通道保持原样。alpha_threshold=0 时只处理完全透明像素。
    """
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    width, height = image.size
    original_alpha = image.getchannel('A')

    # 优化：使用 LUT 代替逐像素操作
    lut = [0 if v <= threshold else 255 for v in range(256)]
    mask = original_alpha.point(lut)

    # 优化：如果没有不超过阈值的像素，直接返回
    if original_alpha.getextrema()[0] > threshold:
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


def compare_texture(img1: Image.Image, img2: Image.Image) -> tuple[bool, float]:
    """带容差比较：返回 (是否视为一致, MSE)，尺寸不同时 MSE 为 inf"""
    mse = texture_mse(img1, img2)
    return mse <= DEFAULT_TEXTURE_MSE_THRESHOLD, mse


def _crop_transparent(image: Image.Image) -> Image.Image:
    """裁掉 alpha 全透明的边（无 alpha 通道或全透明时原样返回）"""
    if "A" not in image.getbands():
        return image
    bbox = image.getchannel("A").getbbox()
    return image.crop(bbox) if bbox else image


def compare_texture_scaled(
    img1: Image.Image,
    img2: Image.Image,
    aspect_tolerance: float = DEFAULT_COMPARE_ASPECT_TOLERANCE,
) -> tuple[bool, float] | None:
    """尺寸不同但宽高比接近时，裁透明边并缩放到同尺寸后比较

    先按 alpha 非零区域裁掉透明边（消除 trim 造成的边距/位置偏差），
    再统一缩放到较小一侧尺寸，最后复用 texture_mse 的透明像素掩码规则。

    Returns:
        (是否视为一致, MSE)；宽高比相对差异超过 aspect_tolerance 时返回 None
    """
    ratio1 = img1.width / img1.height
    ratio2 = img2.width / img2.height
    if abs(ratio1 - ratio2) > aspect_tolerance * min(ratio1, ratio2):
        return None
    ia, ib = _crop_transparent(img1), _crop_transparent(img2)
    target = ia.size if ia.width * ia.height <= ib.width * ib.height else ib.size
    if ia.size != target:
        ia = ia.resize(target, Image.BILINEAR)
    if ib.size != target:
        ib = ib.resize(target, Image.BILINEAR)
    return compare_texture(ia, ib)


def mse_to_similarity(mse: float) -> float:
    """MSE → 相似度百分比（100 − 归一化 RMSE），inf 返回 0"""
    if not math.isfinite(mse):
        return 0.0
    return 100 - math.sqrt(mse) / 255 * 100


def is_same_texture(img1: Image.Image, img2: Image.Image) -> bool:
    """带容差的贴图一致性判定：MSE 不超过默认阈值即视为一致"""
    return compare_texture(img1, img2)[0]
