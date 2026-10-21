# utils/image.py
"""图像处理工具（原 ImageUtils 类打散为模块级函数）"""

from PIL import Image


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
