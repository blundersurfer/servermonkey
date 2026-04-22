#!/bin/bash
# Bootstrap a fresh Ubuntu CT with common utilities
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y
apt-get install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    dnsutils \
    unzip \
    ca-certificates

# Clean up
apt-get autoremove -y
apt-get clean
