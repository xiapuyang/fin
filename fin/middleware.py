import time
import uuid

from fin.context import request_id_ctx
from fin.logger import get_access_logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

access_logger = get_access_logger()

_SKIP_PREFIXES = ("/api/health", "/favicon", "/vendor/", "/src/", "/config/i18n/")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        return await _log_request(request, call_next)


async def _log_request(request: Request, call_next):
    """Inject request_id, log access, measure duration."""
    if any(request.url.path.startswith(p) for p in _SKIP_PREFIXES):
        return await call_next(request)

    rid = uuid.uuid4().hex[:8]
    token = request_id_ctx.set(rid)
    start = time.time()
    req_desc = ""

    try:
        if request.method in ("POST", "PUT", "PATCH"):
            if "application/json" in request.headers.get("content-type", ""):
                try:
                    body_bytes = await request.body()
                    req_desc = body_bytes.decode("utf-8")[:500]

                    async def receive():
                        return {"type": "http.request", "body": body_bytes}

                    request._receive = receive
                except Exception:
                    req_desc = "<unparseable>"

        access_logger.info(
            f"START - {request.method} {request.url.path}"
            + (f" - REQ: {req_desc}" if req_desc else "")
        )

        response = await call_next(request)
        duration = time.time() - start

        resp_body = b""
        if "application/json" in response.headers.get("content-type", ""):
            try:
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                resp_body = b"".join(chunks)

                new_headers = dict(response.headers)
                new_headers.pop("content-length", None)
                response = Response(
                    content=resp_body,
                    status_code=response.status_code,
                    headers=new_headers,
                    media_type=response.media_type,
                )
            except Exception:
                pass

        response.headers["X-Request-ID"] = rid
        log_resp = resp_body.decode("utf-8", errors="ignore")[:300] if resp_body else ""
        access_logger.info(
            f"EXIT - {request.method} {request.url.path} - "
            f"STATUS: {response.status_code} - DURATION: {duration:.4f}s - RESP: {log_resp}"
        )
        return response

    except Exception as e:
        access_logger.error(f"ERROR - {request.method} {request.url.path} - {e}")
        raise
    finally:
        request_id_ctx.reset(token)
