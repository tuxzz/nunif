import os
from os import path
import argparse
from multiprocessing import cpu_count
import torch
import torch.optim as optim
from torch.optim.lr_scheduler import (
    StepLR, MultiStepLR, CosineAnnealingWarmRestarts,
    ConstantLR, ChainedScheduler
)
from ..optim import Lion
from ..models import create_model, save_model, load_model
from ..initializer import set_seed
from .weight_decay_config import configure_adamw
from abc import ABC, abstractmethod


class Trainer(ABC):
    def __init__(self, args):
        self.args = args
        self.initialized = False

    def initialize(self):
        if self.initialized:
            return
        self.initialized = True
        if self.args.gpu[0] >= 0:
            self.device = f"cuda:{self.args.gpu[0]}"
        else:
            self.device = "cpu"
        os.makedirs(self.args.model_dir, exist_ok=True)
        set_seed(self.args.seed)

        self.model = self.create_model()
        self.train_loader = self.create_dataloader(type="train")
        self.eval_loader = self.create_dataloader(type="eval")
        self.optimizer = self.create_optimizer()
        self.scheduler = self.create_scheduler()
        self.grad_scaler = self.create_grad_scaler()
        self.best_model_filename = self.create_best_model_filename()
        self.epoch = 1
        self.start_epoch = 1
        self.best_loss = 1000000000
        if self.args.resume:
            self.resume()
        elif self.args.checkpoint_file is not None:
            self.load_initial_parameters(self.args.checkpoint_file)
        self.env = self.create_env()
        self.env.trainer = self

        if self.amp_is_enabled():
            self.env.enable_amp()
        self.env.set_amp_dtype(torch.bfloat16 if self.args.amp_float == "bfloat16" else torch.float16)
        self.setup()

    def setup(self):
        pass

    def amp_is_enabled(self):
        return not (self.args.disable_amp or self.device == "cpu")

    def resume(self):
        latest_checkpoint_filename = self.create_checkpoint_filename()
        _, meta = load_model(latest_checkpoint_filename, model=self.model)
        if not self.args.reset_state:
            self.optimizer.load_state_dict(meta["optimizer_state_dict"])
            self.scheduler.load_state_dict(meta["scheduler_state_dict"])
            self.grad_scaler.load_state_dict(meta["grad_scaler_state_dict"])
            self.start_epoch = meta["last_epoch"] + 1
            self.best_loss = meta["best_loss"]
        print(f"* load checkpoint from {latest_checkpoint_filename}")

    def load_initial_parameters(self, checkpoint_filename):
        load_model(checkpoint_filename, model=self.model)

    def fit(self):
        self.initialize()
        for self.epoch in range(self.start_epoch, self.args.max_epoch + 1):
            print("-" * 64)
            print(f" epoch: {self.epoch}, lr: {self.scheduler.get_last_lr()}")
            print("--\n train")
            self.env.train(
                loader=self.train_loader,
                optimizer=self.optimizer,
                grad_scaler=self.grad_scaler)
            self.scheduler.step()

            print("--\n eval")
            loss = self.env.eval(self.eval_loader)
            if loss is None:
                self.save_best_model()
            elif loss < self.best_loss:
                print("* best model updated")
                self.best_loss = loss
                self.save_best_model()
            self.save_checkpoint()

    def create_model(self):
        return create_model(self.args.arch, device_ids=self.args.gpu)

    def create_optimizer(self):
        # TODO: support more optimizer if needed
        if self.args.optimizer == "adam":
            return optim.Adam(self.model.parameters(), lr=self.args.learning_rate)
        elif self.args.optimizer == "adamw":
            return configure_adamw(
                self.model,
                lr=self.args.learning_rate,
                weight_decay=self.args.weight_decay)
        elif self.args.optimizer == "sgd":
            return optim.SGD(
                self.model.parameters(),
                lr=self.args.learning_rate,
                momentum=self.args.momentum,
                weight_decay=self.args.weight_decay)
        elif self.args.optimizer == "lion":
            return Lion(self.model.parameters(), lr=self.args.learning_rate, weight_decay=self.args.weight_decay)
        else:
            raise NotImplementedError(f"optimizer = {self.args.optimizer}")

    def create_scheduler(self):
        # TODO: support more schedulers if needed
        if self.args.scheduler == "step":
            if len(self.args.learning_rate_decay_step) == 1:
                scheduler = StepLR(
                    self.optimizer,
                    step_size=self.args.learning_rate_decay_step[0],
                    gamma=self.args.learning_rate_decay)
            else:
                scheduler = MultiStepLR(
                    self.optimizer,
                    milestones=self.args.learning_rate_decay_step,
                    gamma=self.args.learning_rate_decay)
        elif self.args.scheduler == "cosine":
            step = self.args.learning_rate_cycles
            t_0 = self.args.max_epoch // step
            old_max_epoch = self.args.max_epoch
            # Adjust epoch to keep the final epoch to the minimum LR
            self.args.max_epoch -= (self.args.max_epoch % step) + 1
            print(f"scheduler=cosine: max_epoch: {old_max_epoch} -> {self.args.max_epoch}")
            eta_min = self.args.learning_rate * 1e-3
            scheduler = CosineAnnealingWarmRestarts(self.optimizer, T_0=t_0, eta_min=eta_min)
        if self.args.warmup_epoch > 0:
            # TODO: `total_iters=self.args.warmup_epoch` does not work correctly,
            # ConstantLR works fine, but does not work correctly when used with ChainedScheduler.
            warmup_scheduler = ConstantLR(self.optimizer,
                                          factor=self.args.warmup_learning_rate / self.args.learning_rate,
                                          total_iters=self.args.warmup_epoch)
            scheduler = ChainedScheduler([warmup_scheduler, scheduler])

        return scheduler

    def create_grad_scaler(self):
        return torch.cuda.amp.GradScaler(enabled=self.amp_is_enabled())

    def create_best_model_filename(self):
        return path.join(self.args.model_dir, f"{self.model.name}.pth")

    def create_checkpoint_filename(self):
        return path.join(self.args.model_dir, f"{self.model.name}.checkpoint.pth")

    def save_checkpoint(self):
        save_model(
            self.model,
            self.create_checkpoint_filename(),
            train_kwargs=self.args,
            optimizer_state_dict=self.optimizer.state_dict(),
            scheduler_state_dict=self.scheduler.state_dict(),
            grad_scaler_state_dict=self.grad_scaler.state_dict(),
            best_loss=self.best_loss,
            last_epoch=self.epoch)

    def save_best_model(self):
        save_model(self.model, self.best_model_filename, train_kwargs=self.args)

    @abstractmethod
    def create_dataloader(self, type):
        assert (type in {"train", "eval"})

    @abstractmethod
    def create_env(self):
        pass


def create_trainer_default_parser():
    parser = argparse.ArgumentParser(
        add_help=False,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    num_workers = min(cpu_count() - 2, 8)
    if not num_workers > 0:
        num_workers = cpu_count()

    parser.add_argument("--data-dir", "-i", type=str, required=True,
                        help="input training data directory that created by `create_training_data` command")
    parser.add_argument("--model-dir", type=str, required=True,
                        help="output directory for trained model/checkpoint")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="minibatch size")
    parser.add_argument("--optimizer", type=str, choices=["adam", "adamw", "sgd", "lion"], default="adam",
                        help="optimizer")
    parser.add_argument("--weight-decay", type=float, default=1e-4,
                        help="weight decay coefficient for adamw, sgd")
    parser.add_argument("--momentum", type=float, default=0.9,
                        help="momentum for sgd")
    parser.add_argument("--num-workers", type=int, default=num_workers,
                        help="number of worker processes for data loader")
    parser.add_argument("--prefetch-factor", type=int, default=4,
                        help="number of batches loaded in advance by each worker")
    parser.add_argument("--max-epoch", type=int, default=200,
                        help="max epoch")
    parser.add_argument("--gpu", type=int, nargs="+", default=[0],
                        help="device ids; if -1 is specified, use CPU")
    parser.add_argument("--learning-rate", type=float, default=0.00025,
                        help="learning rate")
    parser.add_argument("--scheduler", type=str, choices=["step", "cosine"], default="step",
                        help="learning rate scheduler")
    parser.add_argument("--learning-rate-decay", type=float, default=0.995,
                        help="learning rate decay for StepLR")
    parser.add_argument("--learning-rate-decay-step", type=int, nargs="+", default=[1],
                        help="learning rate decay step for StepLR/MultiStepLR")
    parser.add_argument("--learning-rate-cycles", type=int, default=5,
                        help="number of learning rate cycles for CosineAnnealingWarmRestarts")
    parser.add_argument("--warmup-epoch", type=int, default=0,
                        help="warmup epochs with --warmup-learning-rate")
    parser.add_argument("--warmup-learning-rate", type=int, default=1e-6,
                        help="learning rate for warmup")
    parser.add_argument("--disable-amp", action="store_true",
                        help="disable AMP for some special reason")
    parser.add_argument("--amp-float", type=str, default="fp16", choices=["bfloat16", "fp16"],
                        help="dtype for autocast. bfloat16/fp16")
    parser.add_argument("--resume", action="store_true",
                        help="resume training from the latest checkpoint file")
    parser.add_argument("--reset-state", action="store_true",
                        help="do not load best_score, optimizer and scheduler state when --resume")
    parser.add_argument("--seed", type=int, default=71,
                        help="random seed")
    parser.add_argument("--checkpoint-file", type=str,
                        help="checkpoint file for initializing model parameters. ignored when --resume is specified")

    return parser
