#!/bin/sh
set -eu

guix time-machine -C channels-lock.scm -- build -L . -L ./patches -f guix.scm

guix time-machine -C channels-lock.scm -- system docker-image -L . -L ./patches --root=docker-image.tar.gz docker/image.scm
