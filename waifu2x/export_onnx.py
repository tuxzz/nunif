# convert pytorch models to onnx
# DEBUG=1 python3 -m waifu2x.export_onnx -i ./waifu2x/pretrained_models -o ./waifu2x/onnx_models
# TODO: torchvision's SwinTransformer has bug in Dropout's training flag. Currently I fixed it locally. https://github.com/pytorch/vision/issues/7103

import os
from os import path
import argparse
from nunif.models import load_model
from nunif.models.onnx_helper_models import (
    ONNXReflectionPadding,
    ONNXTTASplit,
    ONNXTTAMerge,
    ONNXCreateSeamBlendingFilter,
    ONNXAlphaBorderPadding,
    ONNXScale1x,  # identity with offset
)
from nunif.logger import logger


def export_onnx(load_path, save_path):
    model, *_ = load_model(load_path)
    model.export_onnx(save_path)


def convert_cunet(model_dir, output_dir):
    for domain in ("art",):
        in_dir = path.join(model_dir, "cunet", domain)
        out_dir = path.join(output_dir, "cunet", domain)
        os.makedirs(out_dir, exist_ok=True)
        for noise_level in (0, 1, 2, 3):
            export_onnx(path.join(in_dir, f"noise{noise_level}.pth"),
                        path.join(out_dir, f"noise{noise_level}.onnx"))

        scale1x = ONNXScale1x(offset=28)
        scale1x.export_onnx(path.join(out_dir, "scale1x.onnx"))


def convert_upcunet(model_dir, output_dir):
    for domain in ("art",):
        in_dir = path.join(model_dir, "cunet", domain)
        out_dir = path.join(output_dir, "cunet", domain)
        os.makedirs(out_dir, exist_ok=True)
        for noise_level in (0, 1, 2, 3):
            export_onnx(path.join(in_dir, f"noise{noise_level}_scale2x.pth"),
                        path.join(out_dir, f"noise{noise_level}_scale2x.onnx"))

        export_onnx(path.join(in_dir, "scale2x.pth"),
                    path.join(out_dir, "scale2x.onnx"))


def convert_swin_unet(model_dir, output_dir):
    for domain in ("art",):
        in_dir = path.join(model_dir, "swin_unet", domain)
        out_dir = path.join(output_dir, "swin_unet", domain)
        os.makedirs(out_dir, exist_ok=True)
        for noise_level in (0, 1, 2, 3):
            export_onnx(path.join(in_dir, f"noise{noise_level}.pth"),
                        path.join(out_dir, f"noise{noise_level}.onnx"))
            export_onnx(path.join(in_dir, f"noise{noise_level}_scale2x.pth"),
                        path.join(out_dir, f"noise{noise_level}_scale2x.onnx"))
            export_onnx(path.join(in_dir, f"noise{noise_level}_scale4x.pth"),
                        path.join(out_dir, f"noise{noise_level}_scale4x.onnx"))

        export_onnx(path.join(in_dir, "scale4x.pth"),
                    path.join(out_dir, "scale4x.onnx"))

        export_onnx(path.join(in_dir, "scale2x.pth"),
                    path.join(out_dir, "scale2x.onnx"))

        scale1x = ONNXScale1x(offset=8)
        scale1x.export_onnx(path.join(out_dir, "scale1x.onnx"))


def convert_utils(output_dir):
    utils_dir = path.join(output_dir, "utils")
    os.makedirs(utils_dir, exist_ok=True)

    pad = ONNXReflectionPadding()
    pad.export_onnx(path.join(utils_dir, "pad.onnx"))

    tta_split = ONNXTTASplit()
    tta_split.export_onnx(path.join(utils_dir, "tta_split.onnx"))

    tta_merge = ONNXTTAMerge()
    tta_merge.export_onnx(path.join(utils_dir, "tta_merge.onnx"))

    seam_filter = ONNXCreateSeamBlendingFilter()
    seam_filter.export_onnx(path.join(utils_dir, "create_seam_blending_filter.onnx"))

    alpha_border_padding = ONNXAlphaBorderPadding()
    alpha_border_padding.export_onnx(path.join(utils_dir, "alpha_border_padding.onnx"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", "-i", type=str, required=True, help="input model dir")
    parser.add_argument("--output-dir", "-o", type=str, required=True, help="output onnx model dir")
    args = parser.parse_args()

    logger.info("cunet")
    convert_cunet(args.input_dir, args.output_dir)

    logger.info("upcunet")
    convert_upcunet(args.input_dir, args.output_dir)

    logger.info("swin_unet")
    convert_swin_unet(args.input_dir, args.output_dir)

    logger.info("utils")
    convert_utils(args.output_dir)
