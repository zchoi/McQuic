#!/bin/sh
docker run -u $(id -u):$(id -g) --gpus all --rm -i --ipc=host -v $PWD/assets:/workspace/mcquic/data mcquic/main:latest -q 1 -i /workspace/mcquic/data/example.png -o /workspace/mcquic/data/compressed.bin

docker run -u $(id -u):$(id -g) --gpus all --rm -i --ipc=host -v $PWD/assets:/workspace/mcquic/data mcquic/main:latest -q 1 -i /workspace/mcquic/data/compressed.bin -o /workspace/mcquic/data/restore.png
