#!/usr/bin/env bash

source $(conda info --base)/etc/profile.d/conda.sh
conda create -y -n music_bot python=3.8
conda activate music_bot
pip install -r requirements.txt
