from collections.abc import Generator
from contextlib import contextmanager
from typing import cast, override

import httpx
import respx
from respx.models import PassThrough, ResolvedRoute, SideEffectError


class AutoPassThroughRouter(respx.MockRouter):
    """A modified router that automatically passes through requests that are not mocked.

    Basically, all that matters is that if a request is not mocked, we are going to raise the
    PassThrough exception so that it can be handled by another transport (e.g. ASGITransport).
    """

    @classmethod
    def from_mock_router(cls, mock_router: respx.MockRouter) -> "AutoPassThroughRouter":
        """Create a AutoPassThroughRouter from an existing respx.MockRouter instance.

        Just do it by patching the method since that's all that matters.
        """
        mock_router.resolver = cls.resolver.__get__(mock_router, respx.MockRouter)
        new_router = cast("AutoPassThroughRouter", mock_router)
        return new_router

    @contextmanager
    @override
    def resolver(self, request: httpx.Request) -> Generator[ResolvedRoute, None, None]:  # noqa: WPS238 WPS231
        resolved = ResolvedRoute()

        try:  # noqa: WPS229
            yield resolved

            # Note: I have removed the section that auto-mocks a 200 response, instead, we are
            # going to raise PassThrough so that another transport can handle it.
            if resolved.response == request or (resolved.route is None):
                # Pass-through request
                raise PassThrough(  # noqa: TRY301
                    f"Request marked to pass through: {request!r}",
                    request=request,
                    origin=resolved.route,  # pyright: ignore[reportArgumentType]
                )

            else:
                # Mocked response
                assert isinstance(resolved.response, httpx.Response)

        except SideEffectError as error:
            self.record(request, response=None, route=error.route)
            raise error.origin from error
        except PassThrough:
            self.record(request, response=None, route=resolved.route)
            raise
        else:
            self.record(request, response=resolved.response, route=resolved.route)
