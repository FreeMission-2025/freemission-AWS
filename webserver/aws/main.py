def main():
    import platform
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

    from constants import HTTP_PORT, HTTPS_PORT, QUIC_PORT, PUBLIC_IP
    from utils.logger import Log

    from app import app
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    import os   

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

    if PUBLIC_IP == '127.0.0.1':
        Log.warning('Using 127.0.0.1 instead of public IP. Use this if not running webserver on same machine (on aws)')
    else:
        Log.warning('Using public IP instead of 127.0.0.1. Use this if running webserver on the same machine')

    try:
        asyncio.run(serve(app, config, mode='asgi'))
    except KeyboardInterrupt:
        print("Shutting down gracefully !")
    except Exception as e:
        print(f"Shutting down. {e}")
        from handler import ctx
        asyncio.run(ctx.cleanup())

if __name__ == "__main__":
    # Explicitly set spawn method beause linux by default use fork 
    # Fork makes socket, file descriptors, & other resources shared with child process which is so bad
    try:
        import multiprocessing
        multiprocessing.set_start_method('spawn')
        main()
    except Exception as e:
        print(f"Error when starting main process: {e}")

#openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -config ssl.conf -extensions req_ext