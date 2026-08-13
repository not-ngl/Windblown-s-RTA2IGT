#!/bin/bash

file=$(ls -Art /tmp/cached* | tail -n 1)

python3 src/verify_cli.py --file $file --auto-result test/output/auto.json --output test/output/hybrid.json
