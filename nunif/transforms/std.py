from PIL import Image
from torchvision import transforms as T
from torchvision.transforms import (
    functional as TF,
    InterpolationMode
)
import random
from io import BytesIO


class Identity():
    def __init__(self):
        pass

    def __call__(self, x):
        return x


class RandomSRHardExampleCrop():
    def __init__(self, size, samples=4):
        self.size = (size, size)
        self.samples = samples

    def __call__(self, x):
        rects = []
        xt = TF.to_tensor(x)
        for _ in range(self.samples):
            i, j, h, w = T.RandomCrop.get_params(x, self.size)
            rect = TF.crop(xt, i, j, h, w)
            color_stdv = rect.std(dim=[1, 2]).sum().item()
            rects.append(((i, j, h, w), color_stdv))

        i, j, h, w = max(rects, key=lambda v: v[1])[0]
        x = TF.crop(x, i, j, h, w)
        return x


class RandomFlip():
    def __call__(self, x):
        if random.uniform(0, 1) > 0.5:
            x = TF.rotate(x, 90, interpolation=InterpolationMode.NEAREST)
        steps = random.choice([[], [TF.hflip], [TF.vflip], [TF.vflip, TF.hflip]])
        for f in steps:
            x = f(x)
        return x


class RandomJPEG():
    def __init__(self, min_quality=85, max_quality=99, sampling=["4:4:4", "4:2:0"]):
        self.min_quality = min_quality
        self.max_quality = max_quality
        self.sampling = sampling

    def __call__(self, x):
        quality = random.randint(self.min_quality, self.max_quality)
        sampling = random.choice(self.sampling)
        with BytesIO() as f:
            mode = x.mode
            rgb = x.convert("RGB")
            rgb.save(f, format="jpeg", quality=quality, sampling=sampling)
            f.seek(0)
            x = Image.open(f)
            x.load()
            if mode == "L":
                x = x.convert("L")
            return x


class RandomDownscale():
    def __init__(self, min_size, min_scale=0.5, interpolations=None):
        self.min_size = min_size
        self.min_scale = min_scale
        if interpolations is None:
            self.interpolations = [TF.InterpolationMode.BICUBIC,
                                   TF.InterpolationMode.LANCZOS]
        else:
            self.interpolations = interpolations

    def __call__(self, x):
        interpolation = random.choice(self.interpolations)
        w, h = x.size
        min_scale = (self.min_size + 1) / min(w, h)
        if min_scale > 1:
            return x
        if min_scale < self.min_scale:
            min_scale = self.min_scale
        scale = random.uniform(min_scale, 1.0)
        x = TF.resize(x, (int(h * scale), int(w * scale)),
                      interpolation=interpolation, antialias=True)

        return x


class RandomChannelShuffle():
    def __init__(self):
        pass

    def __call__(self, x):
        if x.mode != "RGB":
            return x
        channels = list(x.split())
        random.shuffle(channels)
        return Image.merge("RGB", channels)


class ReflectionResize():
    def __init__(self, size):
        if isinstance(size, int):
            self.size = (size, size)
        else:
            self.size = size

    def __call__(self, x):
        w, h = x.size
        pad_l = pad_t = pad_r = pad_b = 0
        if self.size[0] > w:
            border = (self.size[0] - w)
            pad_l = border // 2
            pad_r = border // 2 + (border % 2)
        if self.size[1] > h:
            border = (self.size[1] - h)
            pad_t = border // 2
            pad_b = border // 2 + (border % 2)
        if pad_l + pad_t + pad_r + pad_b != 0:
            x = TF.pad(x, (pad_l, pad_t, pad_r, pad_b), padding_mode="reflect")
        if w > self.size[0] or h > self.size[1]:
            i, j, h, w = T.RandomCrop.get_params(x, self.size)
            x = TF.crop(x, i, j, h, w)
        return x


class RandomPILFilter():
    def __init__(self, filters):
        self.filters = filters

    def __call__(self, x):
        kernel = random.choice(self.filters)
        return x.filter(kernel)
