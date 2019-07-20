#!/usr/bin/env python3

import os
import yaml
import tarfile
import hashlib

from functools import reduce
from shutil import copy2, copytree, rmtree


def sha256(file_path):
    h = hashlib.sha256()

    with open(file_path, 'rb') as file:
        while True:
            chunk = file.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


def mkdir(path):
    directory = os.path.dirname(path)
    if directory != '' and os.path.exists(directory) is False:
        os.makedirs(directory)
    return path


class File:
    def __init__(self, path, body=None):
        self.path = mkdir(path)
        self.body = body

    def read(self, path=None):
        if not path: path = self.path
        with open(path, 'r') as fd:
            return fd.read()

    def write(self, data=None, path=None):
        if not data: data = self.body
        if not path: path = self.path
        with open(path, 'w') as fd:
            fd.write(data)

    def read_yaml(self, path=None):
        return yaml.load(self.read(path), Loader=yaml.FullLoader)

    def firstline(self, path=None):
        if not path: path = self.path
        with open (path, 'r') as f:
            return f.readline()


DOCKERFILE = 'Dockerfile'
IMAGES = File('images.yml').read_yaml()['images']


matrix = reduce(
    lambda x,y: x + y,
    [
        [(
            i,
            f'.build/{i}/Dockerfile',
            f'.build/{i}.tar.gz',
            v.get('source')
        ) for i in v['tags']]
        for k,v in IMAGES.items()
    ]
)


travis_template = lambda matrix, repo='kudato/baseimage': \
f'''sudo: required
language: python
python: 3.7

services:
  - docker

before_install:
  - pip install pyyaml
  - python -m unittest discover tests
  - python make.py

env:
  global:
    - COMMIT_SHA=$TRAVIS_COMMIT
  matrix:
{matrix}

before_script:
  - docker build -t {repo}:$TAG $CONTEXT
  - echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin &>/dev/null

script:
  - docker push {repo}:$TAG
  - docker tag {repo}:$TAG-$COMMIT_SHA
  - docker push {repo}:$TAG-$COMMIT_SHA
'''


class Travis(File):
    def __init__(self):
        super().__init__('.travis.yml')
        body = '\n'.join(
            [f'    - CONTEXT={i[2]} TAG={i[0]}' for i in matrix]
        )
        self.body = travis_template(body)


class Dockerfile(File):
    contexts = []

    def __init__(self, path, tag, source):
        super().__init__(path)
        curr = self.firstline('Dockerfile')[5:15]
        self.write(self.read('Dockerfile') \
            .replace(f'FROM {curr}', f'FROM {source}'))

        context = f'.build/{tag}.tar.gz'
        with tarfile.open(context, "w:gz") as t:
            t.add(f'.build/{tag}/Dockerfile', arcname='Dockerfile')
            t.add('scripts', arcname='scripts')
        rmtree(f'.build/{tag}')
        self.contexts.append((sha256(context),context,tag,source))


Travis().write()
for item in matrix:
    Dockerfile(item[1], item[0], item[3])
