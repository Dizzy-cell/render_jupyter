#!/bin/bash

playwright install

jupyter lab --ip=0.0.0.0 --port=10000 --no-browser --NotebookApp.token='' --NotebookApp.password=''

# git push -u origin-v2 main