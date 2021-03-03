from typing import Any
import sys

import torch
from torch import nn
import torch.nn.functional as F
from cfmUtils.base import parallelFunction, Module
from pytorch_msssim import ms_ssim

from .encoder import Encoder, MultiScaleEncoder
from .decoder import Decoder, MultiScaleDecoder
from .quantizer import Quantizer, MultiCodebookQuantizer, TransformerQuantizer, VQuantizer, TransformerQuantizerRein
from mcqc.losses.structural import CompressionLoss


class Compressor(nn.Module):
    def __init__(self):
        super().__init__()
        self._encoder = Encoder(512)
        self._quantizer = Quantizer(2048, 512, 0.1)
        self._decoder = Decoder(512)

    def forward(self, x: torch.Tensor, temperature: float, hard: bool):
        latents = self._encoder(x)
        quantized, codes, logits = self._quantizer(latents, temperature, hard)
        restored = self._decoder(quantized)

        # restoredC = self._decoder(quantized.detach())
        # newLatents = self._encoder(restoredC)
        # _, _, newLogits = self._quantizer(newLatents, temperature, hard)

        return restored, codes, latents, logits, None # newLogits


class MultiScaleCompressor(nn.Module):
    def __init__(self, k , channel, nPreLayers):
        super().__init__()
        stage = len(k)
        self._encoder = MultiScaleEncoder(channel, nPreLayers, stage)
        self._quantizer = TransformerQuantizer(k, channel, 0.1)
        self._decoder = MultiScaleDecoder(channel, nPreLayers, stage)

    def forward(self, x: torch.Tensor, temperature: float, hard: bool):
        latents = self._encoder(x)
        quantizeds, codes, logits = self._quantizer(latents, temperature, hard)
        restored = torch.tanh(self._decoder(quantizeds))
        return restored, codes, latents, logits, quantizeds


class MultiScaleCompressorRein(nn.Module):
    def __init__(self, k , channel, nPreLayers):
        super().__init__()
        stage = len(k)
        self._encoder = MultiScaleEncoder(channel, nPreLayers, stage)
        self._quantizer = TransformerQuantizerRein(k, channel, 0.1)
        self._decoder = MultiScaleDecoder(channel, nPreLayers, stage)

    def forward(self, x: torch.Tensor, codes=None):
        latents = self._encoder(x)
        if codes is not None:
            logits, negLogPs = self._quantizer(latents, codes)
            return logits, negLogPs
        quantizeds, codes, logits, negLogPs = self._quantizer(latents, codes)
        restored = torch.tanh(self._decoder(quantizeds))
        return restored, codes, latents, negLogPs, logits, quantizeds


class MultiScaleVQCompressor(nn.Module):
    def __init__(self, k , channel, nPreLayers):
        super().__init__()
        stage = len(k)
        self._encoder = MultiScaleEncoder(channel, nPreLayers, stage)
        self._quantizer = VQuantizer(k, channel, 0.1)
        self._decoder = MultiScaleDecoder(channel, nPreLayers, stage)

    def forward(self, x: torch.Tensor, temperature: float, hard: bool):
        latents = self._encoder(x)
        quantizeds, codes, zszq, codewords = self._quantizer(latents, temperature, hard)
        restored = torch.tanh(self._decoder(quantizeds))
        return restored, codes, latents, zszq, quantizeds, codewords # newLogits
