#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
sudo apt update
sudo apt upgrade -y
sudo apt autoremove -y

sudo apt install -y build-essential dkms linux-headers-aws linux-modules-extra-aws unzip gcc make libglvnd-dev pkg-config

# Add NVIDIA repository
DISTRO=$(. /etc/os-release;echo $ID$VERSION_ID | sed -e 's/\.//g')
if (arch | grep -q x86); then
  ARCH=x86_64
else
  ARCH=sbsa
fi
cd /tmp
curl -L -O https://developer.download.nvidia.com/compute/cuda/repos/$DISTRO/$ARCH/cuda-keyring_1.1-1_all.deb
sudo apt install -y ./cuda-keyring_1.1-1_all.deb
sudo apt update

# Install nvidia driver
sudo apt install -y cuda-drivers

# Install CUDA
sudo apt install -y cuda-toolkit
echo 'export PATH=/usr/local/cuda/bin:$PATH' | sudo tee -a /etc/profile.d/cuda.sh
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' | sudo tee -a /etc/profile.d/cuda.sh
sudo chmod +x /etc/profile.d/cuda.sh
sudo ldconfig

# Install CUDNN
sudo apt install -y zlib1g cudnn
sudo ldconfig

# Install libgl
sudo apt install libgl1 libgl1-mesa-dev mesa-utils mesa-common-dev

# Install pip and venv
sudo apt install python3-pip python3-venv

# Install netstat
sudo apt install net-tools

sudo reboot