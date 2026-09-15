import io
import posixpath
import zipfile

from .ocr import PageResult


# Image keys coming back from PaddleOCR are derived from the crop's bounding box, so two
# pages can produce the same key. Prefixing with the page number keeps every image of the
# document distinct; the same rename is applied inside prunedResult so restructure-pages
# regenerates markdown that still points at the stored files.
def namespace_images(page_number: int, page: PageResult) -> PageResult:
    renames = {key: f"imgs/p{page_number:05d}_{posixpath.basename(key)}" for key in page.images}
    return PageResult(
        pruned_result=rename_strings(page.pruned_result, renames),
        markdown=rename_strings(page.markdown, renames),
        images={renames[key]: data for key, data in page.images.items()},
    )


def rename_strings(value, renames: dict[str, str]):
    if isinstance(value, str):
        for old, new in renames.items():
            if old in value:
                value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [rename_strings(item, renames) for item in value]
    if isinstance(value, dict):
        return {key: rename_strings(item, renames) for key, item in value.items()}
    return value


def concatenate(page_markdowns: list[str]) -> str:
    return "\n\n".join(text.strip() for text in page_markdowns if text.strip()) + "\n"


def build_zip(markdown: str, images: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result.md", markdown)
        for key, data in images.items():
            archive.writestr(key, data)
    return out.getvalue()
