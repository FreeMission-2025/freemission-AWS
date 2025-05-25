## Webserver Parts has been archived and moved for easier development
Raspi : [Github Link](https://github.com/FreeMission-2025/FM-Raspi)

AWS: [Github Link](https://github.com/FreeMission-2025/FM-Raspi)

## Description
Free Mission Software for AWS and Raspi. 

### Folder Structure
- `/aws`                  : Various protocol (UDP and TCP) and Image / Video format (H264, MJPEG) for AWS server
- `/raspi`                : Various protocol (UDP and TCP) and Image / Video format (H264, MJPEG) for Raspi client

### Folder Structure
Running : 
```bash
# Use python version 3.11+ and use virtual environment
python3 -m venv venv

# Linux : 
source ./venv/bin/activate

# Windows :
./venv/Scripts/activate

# Install package
pip install -r requirements.txt

# run as sudo and activate venv again
sudo -s
ulimit -n 120000
setcap cap_net_bind_service=+ep /usr/bin/python3.12 # change to ur python version

# Running AWS Server . Modify constants.py to modify codec, port, ip, protocol, etc
python aws/main.py

# Running Raspi Client
# Choose between TCP and UDP (buggy on linux) folder and run according to file name.
# ex: udp/v380/socket_h264.py means using UDP on V380 camera using H264 Encoder
python raspi/udp/v380/socket_h264.py
```