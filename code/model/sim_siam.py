import torch
import torch.nn as nn
import math
from .modules import *
from torchvision.models import resnet50

class MLP(nn.Module):
    def __init__(self, in_dim, out_dim, hsz, n_layers):
        super(MLP, self).__init__()

        layers = []
        prev_dim = in_dim
        for i in range(n_layers):
            if i == n_layers - 1:
                layers.append(nn.Linear(prev_dim, out_dim))
            else:
                layers.extend([
                    nn.Linear(prev_dim, hsz),
                    nn.ReLU(True),
                    nn.Dropout(0.5)
                ])
                prev_dim = hsz

        self.main = nn.Sequential(*layers)

    def forward(self, x):
        return self.main(x)

class Projection(nn.Module):
    def __init__(self, in_dim, out_dim=2048, hsz=2048, n_layers=3):
        super().__init__()

        layers = []
        prev_dim = in_dim
        for i in range(n_layers):
            if i == n_layers - 1:
                layers.extend([
                    nn.Linear(prev_dim, out_dim),
                    nn.BatchNorm1d(out_dim)
                ])
            else:
                layers.extend([
                    nn.Linear(prev_diim, hsz),
                    nn.BatchNorm1d(hsz),
                    nn.ReLU(inplace=True)
                ])
                prev_dim = hsz
        self.main = nn.Sequential(*layers)

    def forward(self, x):
        return self.main(x)

class Prediction(nn.Module):
    def __init__(self, in_dim=2048, out_dim=2048, hsz=512, n_layers=2):
        super().__init__()

        layers = []
        prev_dim = in_dim
        for i in range(n_layers):
            if i == n_layers - 1:
                layers.append(nn.Linear(prev_dim, out_dim))
            else:
                layers.extend([
                    nn.Linear(prev_dim, hsz),
                    nn.BatchNorm1d(hsz),
                    nn.ReLU(inplace=True)
                ])
                prev_dim = hsz

            self.main = nn.Sequential(*layers)

        def forward(self, x):
            return self.main(x)


class SimSiam(nn.Module):
    def __init__(self, use_outputs):
        super(SimSiam, self).__init__()

        self.backbone = resnet50()
        self.projector = Projection(resnet50().output_dim)

        self.encoder = nn.Sequential( # f encoder
                self.backbone,
                self.projector
        )
        self.predictor = Prediction()

        self.net_output_key = use_outputs
    
    @classmethod
    def resolve_args(cls, args):
        return cls(args, args.use_outputs)

    def forward(self, x_1, x_2):
        f, h = self.encoder, self.predictor
        z_i, z_j = f(x_1), f(x_2)
        p_i, p_j = h(z_1), h(z_2)
        {key: eval(key) for key in self.net_output_key}
        return y_pred
