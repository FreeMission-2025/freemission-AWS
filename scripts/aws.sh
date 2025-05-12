# Benchmark Sender and Receiver
iperf3 -s -p 8001
iperf3 -c 43.218.134.25 -p 5201     # Laptop → EC2 (Laptop uploads, EC2 downloads)
iperf3 -c 43.218.134.25 -p 5201 -R  # EC2 → Laptop (Laptop downloads, EC2 uploads)

# Add python access to unprivileged port (80,443,etc)
sudo setcap cap_net_bind_service=+ep /usr/bin/python3.12

# Add trusted CA
sudo cp /home/crystal/Desktop/teknofest/webserver/certificate/cert.pem /usr/local/share/ca-certificates/mycert.crt
sudo update-ca-certificates

# Check used ports
sudo lsof -i :8086
sudo netstat -tuln
sudo kill 1981 
sudo kill -9 1981 

# Check sock buffer max limit:
cat /proc/sys/net/core/rmem_max

# Temporarily increase max (until reboot):
sudo sysctl -w net.core.rmem_max=67108864  # 64 MB

# Permanently set (e.g., in /etc/sysctl.conf):
net.core.rmem_max = 67108864

# update shared library
sudo ldconfig
