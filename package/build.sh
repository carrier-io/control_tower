#!/bin/bash

mkdir package/lambda
docker run --rm -v "$PWD/package":/var/task lambci/lambda:build-python3.7 pip install -r requirements.txt -t /var/task/lambda
cp package/lambda.py package/lambda
cd package/lambda
zip control-tower.zip -r .
cp control-tower.zip ../
cd ..
rm -rf lambda
cd ..

