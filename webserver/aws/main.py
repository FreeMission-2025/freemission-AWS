from multiprocessing import shared_memory
import platform
import signal
from typing import Any
from constants import HTTP_PORT, HTTPS_PORT, QUIC_PORT

system = platform.system()
try:
    if system == 'Linux':
        import uvloop
        uvloop.install()
    elif system == 'Windows':
        import winloop
        winloop.install()
except ModuleNotFoundError:
    pass
except Exception as e:
    print(f"Error when installing loop: {e}")

from app import app
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
import os   


def main():
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    cert_path = os.path.join(current_dir, "../",  "certificate", "cert.pem")
    key_path = os.path.join(current_dir,  "../", "certificate", "key.pem")

    config = Config()

    # linux automaticly bind both ipv4 and ipv6
    if system == 'Linux':
        config.quic_bind = [f"[::]:{QUIC_PORT}"]
        config.insecure_bind=[f"[::]:{HTTP_PORT}"]
        config.bind=[f"[::]:{HTTPS_PORT}"]
    else:
        config.quic_bind = [f"0.0.0.0:{QUIC_PORT}", f"[::]:{QUIC_PORT}"]
        config.insecure_bind=[f"0.0.0.0:{HTTP_PORT}", f"[::]:{HTTP_PORT}"]
        config.bind=[f"0.0.0.0:{HTTPS_PORT}", f"[::]:{HTTPS_PORT}"]

    config.certfile = cert_path
    config.keyfile = key_path
    config.alpn_protocols = ["h3", "h2", "http/1.1"] 
    config.accesslog = "-"  
    config.access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'

    try:
        asyncio.run(serve(app, config, mode='asgi'))
    except KeyboardInterrupt:
        print("Shutting down gracefully !")
    except Exception as e:
        print(f"Shutting down. {e}")
        from handler import ctx
        asyncio.run(ctx.cleanup())

if __name__ == "__main__":
    main()


#openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -config ssl.conf -extensions req_ext