'''
freeze the encoder and train the supervised classification head with a cross entropy loss
'''

import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision 
from tqdm import tqdm
import shutil
import copy

from ignite.engine.engine import Engine, State, Events

from dataloader import get_aug
from dataloader.load_dataset import get_dataset
from ckpt import get_model_ckpt, save_ckpt
from model import get_model
from loss import get_loss
from optimizer import get_optimizer, get_sub_optimizer, get_scheduler
from logger import get_logger, log_results, log_results_cmd

from utils import prepare_batch
from metric import get_metrics
from metric.stat_metric import StatMetric, KNNMonitor
from ignite.metrics import Accuracy, TopKCategoricalAccuracy, Loss
import numpy as np


''' 
transfer learning where we allow all weights to vary during training
'''

'''
ignite.metrics.TopKCategoricalAccuracy(k=5, output_transfrom, device)
 calculates the top-k categorical accuarcy
 `update` must reive output `(y_pred, y)` or dict
'''
def get_trainer(args, model, loss_fn, optimizer, scheduler):
    def update_model(trainer, batch):
        model.encoder.eval()
        model.mlp.train()
        optimizer.zero_grad()

        # to gpu
        net_inputs, target = prepare_batch(args, batch)
        # **: dictionary input each argument
        # y_pred: dict {z_i, z_j, p_i, p_j}
        y_pred = model(**net_inputs)
        batch_size = target.shape[0] # N
        loss = loss_fn(y_pred, target)
        
        loss.backward()
        optimizer.step()
        scheduler.step()
        
        return loss.item(), batch_size, y_pred.detach(), target.detach()

    trainer = Engine(update_model)

    metrics = {
            'loss': StatMetric(output_transform=lambda x: (x[0], x[1])),
            'top1_acc': Accuracy(output_transform=lambda x: (x[2], x[3])),
            }

    for name, metric in metrics.items():
        metric.attach(trainer, name)

    return trainer
def get_evaluator(args, model, loss_fn, metrics={}):
    sample_count = 0
    def _inference(evaluator, batch):
        nonlocal sample_count
        
        model.encoder.eval()
        model.mlp.eval()
        model.encoder.zero_grad()

        with torch.no_grad():
            net_inputs, target = prepare_batch(args, batch)
            y_pred = model(**net_inputs)
            batch_size = y_pred.shape[0]
            loss = loss_fn(y_pred, target)

            return loss.item(), batch_size, y_pred, target

        engine= Engine(_inference)
'''
ignite.metrics.loss(loss_fn, output_transform, batch_size, device)
 loss_fn : taking a prediction tensor, a target tensor and returns the average loss over all observations in the batch
 output_transform: is expected to be a tuple (prediction, target)
'''

        metrics = {**metrics, **{
            'loss': Loss(loss_fn, ouput_transform=lambda x: (x[2], x[3])),
            'top1_acc': Accuracy(output_transform=lambda x: (x[2], x[3])),
            'top5_acc': TopKCategoricalAccuracy(k=5, output_transform=lambda x:(x[2], x[3])),
            # target.view(-1,1).expand_as(k).sum().item() / batch_size 
            # num_corrects
        }}

        for name, metric in metrics.items():
            metric.attach(engine, name)

        return engine

def evaluate_once(evaluator, iterator):
    evaluator.run(iterator)
    return evaluator.state

def linear_evaluation(pretrain, args):
    # get pretrained models
    args, pt_model, ckpt_available = get_model_ckpt(pretrain)

    taug = get_aug(args=args, train=True, double=False)
    vaug = get_aug(args=args, train=False, double=False)
    linear_iters = get_dataset(args, taug, vaug)
    
    if ckpt_available:
        print("loaded checkpoint {}".format(args.ckpt_name))
    
    model = get_model(args, pt_model, args.num_classes)
    loss_fn = get_loss(args)
    optimizer = get_sub_optimizer(args, model)
    scheduler = get_scheduler(args, optimizer)

    trainer = get_trainer(args, model, loss_fn, optimizer, scheduler)
    evaluator = get_evaluator(args, model, loss_fn)

    metrics = get_metrics(args)

    logger = get_logger(args)

    @trainer.on(Events.STARTED)
    def on_training_started(engine):
        print("Begin Logistic Regression")

    # batch-wise
    @trainer.on(Events.ITERATION_COMPLETED)
    def log_iter_results(engine):
        log_results(logger, 'logistic_regression/iter', engine.state, engine.state.iteration)

    # epoch-wise (ckpt)
    @trainer.on(Events.EPOCH_COMPLETED)
    def save_epoch(engine):
        log_results(logger, 'logistic_regression/epoch', engine.state, engine.state.epoch)
        log_results_cmd(logger, 'logistic_regression/epoch', engine.state, engine.state.epoch)
        state = evaluate_once(evaluator, iterator=log_iters['val'])
        save_ckpt(args, engine.state.epoch, engine.state.metrics['loss'], model)

    trainer.run(log_iters['train']), max_epochs=args.max_epochs)
