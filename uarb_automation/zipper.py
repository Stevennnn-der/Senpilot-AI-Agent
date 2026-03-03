import zipfile
from pathlib import Path
from .downloader import sanitize_filename


class Zipper:
    @staticmethod
    def zip_tab(download_root: Path, matter: str, tab_name: str) -> str:
        src_dir = download_root / matter / tab_name
        zip_path = download_root / f"{matter}_{sanitize_filename(tab_name)}.zip"
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in src_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=str(p.relative_to(download_root)))

        return str(zip_path)