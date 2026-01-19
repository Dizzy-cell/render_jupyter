
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models

class VGGFeatureExtractor(nn.Module):
    def __init__(self, layers=(3, 8, 15, 22)):
        """
        layers: VGG19 relu layer indices
        relu1_2=3, relu2_2=8, relu3_3=15, relu4_3=22
        """
        super().__init__()
        vgg = models.vgg19(weights=models.VGG19_Weights.IMAGENET1K_V1)
        self.features = vgg.features[:max(layers)+1]
        self.layers = layers
        for p in self.parameters():
            p.requires_grad = False

    def forward(self, x):
        feats = []
        for i, layer in enumerate(self.features):
            x = layer(x)
            if i in self.layers:
                feats.append(x)
        return feats

def gram_matrix(feat):
    """
    feat: (B, C, H, W)
    """
    B, C, H, W = feat.shape
    feat = feat.view(B, C, H * W)
    gram = torch.bmm(feat, feat.transpose(1, 2))
    gram = gram / (C * H * W)
    return gram


class PerceptualLoss(nn.Module):
    def __init__(
        self,
        lambda_feat=(1.0, 1.0, 1.0, 1.0),
        lambda_gram=(0.1, 0.1, 0.1, 0.1),
    ):
        super().__init__()
        self.vgg = VGGFeatureExtractor()
        self.lambda_feat = lambda_feat
        self.lambda_gram = lambda_gram
    def normalize_vgg(self, x):
      mean = torch.tensor([0.485, 0.456, 0.406], device=x.device)[None,:,None,None]
      std  = torch.tensor([0.229, 0.224, 0.225], device=x.device)[None,:,None,None]
      return (x - mean) / std


    def forward(self, pred, gt):
        """
        pred: ˆI_novel  (B,3,H,W), range [0,1]
        gt:   I_novel   (B,3,H,W), range [0,1]
        """

        pred = self.normalize_vgg(pred)
        gt = self.normalize_vgg(gt)

        feats_pred = self.vgg(pred)
        feats_gt   = self.vgg(gt)

        loss = 0.0
        for l, (fp, fg) in enumerate(zip(feats_pred, feats_gt)):
            # feature loss
            loss_feat = F.mse_loss(fp, fg)

            # gram loss
            gram_p = gram_matrix(fp)
            gram_g = gram_matrix(fg)
            loss_gram = F.mse_loss(gram_p, gram_g)

            loss += (
                self.lambda_feat[l] * loss_feat
                + self.lambda_gram[l] * loss_gram
            )

        return loss
