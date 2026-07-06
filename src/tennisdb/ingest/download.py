"""HTTP access for ingesters; injectable so tests can substitute a fake."""

from pathlib import Path

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class DownloadError(Exception):
    pass


class HttpDownloader:
    def __init__(self):
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=60.0,
            headers={"User-Agent": USER_AGENT},
            transport=httpx.HTTPTransport(retries=3),
        )

    def get_text(self, url: str) -> str:
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise DownloadError(f"GET {url} failed: {error}") from error
        return response.text

    def download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_suffix(destination.suffix + ".part")
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                with temp_path.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
        except httpx.HTTPError as error:
            temp_path.unlink(missing_ok=True)
            raise DownloadError(f"download of {url} failed: {error}") from error
        temp_path.replace(destination)
