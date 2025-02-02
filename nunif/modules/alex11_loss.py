import torch
from torch import nn
from torch.nn import functional as F
from .charbonnier_loss import CharbonnierLoss
from os import path


class Alex11Loss(nn.Module):
    # AlexNet's first 11x11 linear filter
    def __init__(self, in_channels, loss=None, cosine_weight=0.0):
        assert in_channels in {1, 3}
        super().__init__()
        self.in_channels = in_channels
        self.cosine_weight = cosine_weight
        self.conv = self.create_filter(in_channels)
        if loss is None:
            self.loss = CharbonnierLoss()
        else:
            self.loss = loss

    @staticmethod
    def create_filter(in_channels):
        weight_path = path.join(path.dirname(__file__), "alex11.pth")
        if path.exists(weight_path):
            # Load calculated weights
            # NOTE: If not loaded, need to make sure torchvision's alex weights are still the same
            f = torch.load(weight_path)
        else:
            from torchvision.models import alexnet, AlexNet_Weights

            net = alexnet(weights=AlexNet_Weights.DEFAULT)
            f = net.features[0].weight.data.detach().clone()
            # rgb to grayscale
            f = f[:, 0:1, :, :] * 0.29891 + f[:, 1:2, :, :] * 0.58661 + f[:, 2:3, :, :] * 0.11448
            # normalize [-1, 1]
            for i in range(f.shape[0]):
                f[i] *= 1. / torch.abs(f[i]).max()
            # index 31 is most similar to the identity filter,
            # so override it with the true identity filter
            f[31, :, :, :].zero_()
            f[31, :, 11 // 2, 11 // 2] = 1.  # 1., 4., 8.
            torch.save(f, weight_path)
        # conv2d
        conv = nn.Conv2d(in_channels, 64 * in_channels, kernel_size=11, stride=1, padding=0, groups=in_channels, bias=False)
        f = torch.cat([f for _ in range(in_channels)], dim=0)
        print(f.shape)
        conv.weight.data.copy_(f)
        for m in conv.parameters():
            m.requires_grad_(False)
        return conv

    def forward(self, input, target):
        y = self.conv(input)
        t = self.conv(target)
        loss_filter = self.loss(y, t)
        if self.cosine_weight > 0:
            loss_cosine = -F.cosine_similarity(y, t).mean()
            loss = loss_filter * (1. - self.cosine_weight) + loss_cosine * self.cosine_weight
        else:
            loss = loss_filter

        return loss


def _visualize(loss):
    from torchvision.utils import make_grid
    from torchvision.transforms import functional as TF
    from torchvision.transforms import InterpolationMode
    f = torch.clamp(loss.conv.weight.data, -1, 1)
    c = torch.cat([torch.clamp(f, 0, 1),
                   -torch.clamp(f, -1, 0),
                   torch.zeros(f.shape)], dim=1)
    grid = make_grid(c, nrow=8, padding=2)
    grid = TF.to_pil_image(grid)
    im = TF.resize(grid, (grid.size[1] * 4, grid.size[0] * 4), interpolation=InterpolationMode.NEAREST)
    im.show()


def _visualize_result(loss):
    from torchvision.utils import make_grid
    from torchvision.transforms import functional as TF
    from ..utils import pil_io
    from os import path
    im, _ = pil_io.load_image_simple(path.join("waifu2x", "docs", "images", "miku_128.png"))
    im = TF.to_grayscale(im)
    im = TF.to_tensor(im)
    ret = loss.conv(im.unsqueeze(0)).squeeze(0)
    ret = ret.unsqueeze(1)
    grid = make_grid(ret, nrow=8, padding=2, normalize=True, scale_each=True)
    grid = TF.to_pil_image(grid)
    grid.show()


if __name__ == "__main__":
    loss = Alex11Loss(1)
    input = torch.rand((4, 1, 16, 16))
    target = torch.rand((4, 1, 16, 16))
    z = loss(input, target)

    print(z)
    _visualize(loss)
    _visualize_result(loss)
