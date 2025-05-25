### Archived and moved for easier development
Raspi : [Github Link](https://github.com/FreeMission-2025/FM-Raspi)

AWS: [Github Link](https://github.com/FreeMission-2025/FM-Raspi)

# freemission-AWS

# Setup

## AWS EC2 Instance

AWS EC2 instace is used to receive, process and transmit data from client-server-client.

1.  Create EC2 instance with amazoin linux 2 AMI.
2.  Connect via putty or web
3.  Install Depedenices

    ```bash
    sudo yum update && sudo yum upgrade -y
    sudo yum install git python3 python3-pip -y
    sudo yum install python3-opencv -y
    ```

    Note: to connect via putty, you need private key file (.ppk) and public IP address of the instance that can be seen on connect tab. Dont forget to change username in data to ec2-user.

## Raspberry Pi

Raspberry Pi is used to capture images and send to AWS EC2 instance.

1.  Install Raspbian OS Lite (for more efficient use of resources)
2.  Install dependencies

    ```bash
    sudo apt-get update && sudo apt-get upgrade -y
    sudo apt-get install python3 python3-pip git -y
    sudo apt-get install python3-opencv -y
    ```
