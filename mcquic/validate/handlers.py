from typing import List, Tuple, Any, Union

import torch
from torch import nn
from vlutils.metrics.meter import Handler

from .metrics import MsSSIM as M, PSNR as P
from .utils import Decibel


class MsSSIM(Handler):
    def __init__(self, format: str = r"%.2f dB"):
        super().__init__(format=format)
        self._msSSIM = M(sizeAverage=False)
        self._formatter = Decibel(1.0)

    def to(self, device):
        self._msSSIM.to(device)
        return super().to(device)

    def handle(self, *, images: torch.ByteTensor, restored: torch.ByteTensor, **_) -> List[float]:
        # [N]
        results: torch.Tensor = self._formatter(self._msSSIM(images.float(), restored.float()))
        return results.tolist()


class PSNR(Handler):
    def __init__(self, format: str = r"%.2f dB"):
        super().__init__(format=format)
        self._psnr = P(sizeAverage=False)

    def to(self, device):
        self._psnr.to(device)
        return super().to(device)

    def handle(self, *, images: torch.ByteTensor, restored: torch.ByteTensor, **_) -> List[float]:
        # [N]
        results: torch.Tensor = self._psnr(images.float(), restored.float())
        return results.tolist()


class BPP(Handler):
    def __init__(self, format: str = r"%.4f"):
        super().__init__(format=format)

    @staticmethod
    def bitLength(byteArray: List[bytes]):
        return sum(len(bi) * 8 for bi in byteArray)

    def handle(self, *, images: torch.ByteTensor, binaries: List[List[bytes]], **_) -> List[float]:
        # binaries: List of binary, len = n, len(binaries[0]) = level
        bits = [self.bitLength(bis) for bis in binaries]
        pixels = images.shape[-2] * images.shape[-1]
        bpps = [bit / pixels for bit in bits]
        return bpps


class Visualization(Handler):
    def __init__(self):
        super().__init__()
        self._temp = None

    def reset(self):
        self._temp = None

    def __call__(self, *args: Any, **kwds: Any):
        self._temp = self.handle(*args, **kwds)

    def handle(self, *, restored: torch.ByteTensor, **_) -> torch.Tensor:
        # binaries: List of binary, len = n, len(binaries[0]) = level
        return restored.detach()

    @property
    def ShowInSummary(self) -> bool:
        return False

    @property
    def Result(self):
        # percentage of usage of all codes
        return self._temp

    def __str__(self) -> str:
        return "In Tensorboard."


class IdealBPP(Handler):
    def __init__(self, m: int, k: List[int], format: str = r"%.4f"):
        super().__init__(format)

        self._k = k
        self._m = m
        self.accumulated: List[torch.Tensor] = list(torch.zeros((m, k)) for k in self._k)
        self.totalPixels = torch.zeros(())
        self.totalCodes: List[torch.Tensor] = list(torch.zeros((self._m)) for _ in self._k)

    def reset(self):
        self.length = 0
        self.accumulated = list(torch.zeros((self._m, k)) for k in self._k)
        self.totalPixels = torch.zeros(())
        self.totalCodes = list(torch.zeros((self._m)) for _ in self._k)

    def __call__(self, *args: Any, **kwds: Any):
        results, pixels, codes = self.handle(*args, **kwds)

        # Only give stats of whole dataset
        self.length += 1

        for lv, unqiueCounts in enumerate(results):
            self.accumulated[lv] += unqiueCounts
        self.totalPixels += pixels
        for lv, codeCount in enumerate(codes):
            self.totalCodes[lv] += codeCount

    def handle(self, *, codes: List[torch.Tensor], images: torch.ByteTensor, **_) -> Tuple[List[torch.Tensor], int, List[torch.Tensor]]:
        """[summary]

        Args:
            codes (List[torch.Tensor]): len = level, each code has shape [n, m, h, w]
            images (torch.ByteTensor): [n, c, h, w]

        Returns:
            List[torch.Tensor]: Bincount of codes, len = level, each item has shape [m, k]
            int: Total pixels (n * h * w) of images.
            List[torch.Tensor]]: Total code amount, len = level, each item has shape [m].
        """
        allCounts: List[torch.Tensor] = list()
        codesNum: List[torch.Tensor] = list()
        # [n, m, h, w]
        for code, k in zip(codes, self._k):
            groupCounts = list()
            groupCodeNum = list()
            for m in range(self._m):
                # [n, h, w] -> [k]
                count = torch.bincount(code[:, m].flatten(), minlength=k).cpu()
                groupCounts.append(count)
                groupCodeNum.append(code[:, m].numel())
            # [m, k]
            groupCounts = torch.stack(groupCounts, 0)
            allCounts.append(groupCounts)

            # [m]
            groupCodeNum = torch.tensor(groupCodeNum)
            codesNum.append(groupCodeNum)

        n, _, h, w = images.shape

        # lv * [each image's unique counts, only first group]
        return allCounts, n * h * w, codesNum

    @property
    def Result(self) -> float:
        totalBits = 0.
        for codeUsage, codeCount in zip(self.accumulated, self.totalCodes):
            # [m, k]
            prob = codeUsage / codeUsage.sum(-1, keepdim=True)
            estimateEntropy = prob.log2()
            estimateEntropy[estimateEntropy == float("-inf")] = 0
            # [m]
            estimateEntropy = -(prob * estimateEntropy).sum(-1)
            # [m] * [m] then sum
            totalBits += float((estimateEntropy * codeCount).sum())
        # percentage of usage of all codes
        return totalBits / float(self.totalPixels)

    def __str__(self) -> str:
        return self._format % self.Result
