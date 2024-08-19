from uvicorn.workers import UvicornWorker


class ProxyUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {
        "loop": "auto",  # Use 'auto' to automatically choose the best loop, 'uvloop' can be specified for performance.
        "http": "auto",  # Use 'auto' to automatically choose the best HTTP protocol support, 'httptools' can be specified.
        "lifespan": "on",  # 'on' to enable lifespan support.
        "proxy_headers": True,  # Corresponding to `--proxy-headers`
        "forwarded_allow_ips": "*",  # Corresponding to `--forwarded-allow-ips=*`
    }
