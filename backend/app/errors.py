"""Consistent error responses (RFC 9457 problem+json)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str, **extra) -> None:
        super().__init__(detail)
        self.status, self.code, self.detail, self.extra = status, code, detail, extra


def not_found(what: str = "resource") -> ApiError:
    # Used for missing objects AND objects in another organization, so ids cannot be probed.
    return ApiError(404, "not_found", f"{what} not found")


def forbidden(detail: str = "You do not have permission to do this") -> ApiError:
    return ApiError(403, "forbidden", detail)


def _problem(status: int, code: str, detail: str, request: Request, **extra) -> JSONResponse:
    body = {"type": f"https://webdata.local/errors/{code}", "title": code.replace("_", " "), "status": status,
            "detail": detail, "code": code, "instance": str(request.url.path),
            "request_id": getattr(request.state, "request_id", None), **extra}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError):
        return _problem(exc.status, exc.code, exc.detail, request, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return _problem(exc.status_code, "http_error", str(exc.detail), request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()][:20]
        return _problem(422, "validation_error", "The request is not valid", request, errors=errors)
