"""No-proxy local MT transport, with redirects checked before any request.

The dispatcher enables FREETRANSLATE_LOCAL_ONLY. This is an HTTP-client guard,
not an OS network sandbox (extractors may need previously downloaded weights).
"""
import ipaddress
import os
import urllib.request
from urllib.parse import urlsplit


def local_endpoint(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
        return False
    if p.hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(p.hostname).is_loopback
    except ValueError:
        return False


def validate_endpoint(url, allow_remote=False):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("endpoint must be http(s), without credentials/query/fragment; use LLM_API_KEY")
    if not allow_remote and not local_endpoint(url):
        raise ValueError("remote MT disabled; explicitly approve allow_remote for this job")
    return url


class Guard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if os.environ.get("FREETRANSLATE_LOCAL_ONLY") == "1":
            validate_endpoint(newurl)
        # Never forward an API key to another origin, even in remote mode.
        if urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            raise ValueError("cross-origin model redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class EndpointGuard(urllib.request.BaseHandler):
    def http_request(self, req):
        if os.environ.get("FREETRANSLATE_LOCAL_ONLY") == "1":
            validate_endpoint(req.full_url)
        return req

    https_request = http_request


def model_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), EndpointGuard(), Guard())
