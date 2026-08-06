import json
from pathlib import Path
from typing import Optional, Any


class Paths:
    assetsDir: Path = Path('')

    @staticmethod
    def getPath(file: str, library: Optional[str] = None) -> Path:
        if library is not None:
            return Paths.getLibraryPath(file, library)
        return Paths.getPreloadPath(file)

    @staticmethod
    def getLibraryPath(file: str, library: str = 'preload') -> Path:
        if library == 'preload':
            return Paths.getPreloadPath(file)
        return Paths.getLibraryPathForce(file, library)

    @staticmethod
    def getLibraryPathForce(file: str, library: str) -> Path:
        return Paths.assetsDir / library / file

    @staticmethod
    def getPreloadPath(file: str) -> Path:
        return Paths.assetsDir / Path(file)

    @staticmethod
    def txt(key: str, library: Optional[str] = None) -> Path:
        return Paths.getPath(f'{key}.txt', library)

    @staticmethod
    def xml(key: str, library: Optional[str] = None) -> Path:
        return Paths.getPath(f'{key}.xml', library)

    @staticmethod
    def json(key: str, library: Optional[str] = None) -> Path:
        return Paths.getPath(f'{key}.json', library)

    @staticmethod
    def png(key: str, library: Optional[str] = None) -> Path:
        return Paths.getPath(f'{key}.png', library)

    @staticmethod
    def image(key: str, library: Optional[str] = None) -> Path:
        return Paths.png(key, library)

    @staticmethod
    def sound(key: str, library: Optional[str] = None, ext: str = 'ogg') -> Path:
        return Paths.getPath(f'sounds/{key}.{ext}', library)

    @staticmethod
    def music(key: str, library: Optional[str] = None, ext: str = 'ogg') -> Path:
        return Paths.getPath(f'music/{key}.{ext}', library)

    @staticmethod
    def font(key: str) -> Path:
        return Paths.assetsDir / 'fonts' / key

    @staticmethod
    def video(key: str, ext: str = 'mp4') -> Path:
        return Paths.getPath(f'videos/{key}.{ext}')

    @staticmethod
    def exists(file: str, library: Optional[str] = None) -> bool:
        return Paths.getPath(file, library).exists()

    @staticmethod
    def parseJson(file: str) -> Optional[Any]:
        path = Paths.json(file)
        if not path.exists():
            print(f"Error! File not found: {path}")
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error! {e}")
            return None

    @staticmethod
    def writeJson(file: str, writeFile: dict, indent: int = 4) -> bool:
        path = Paths.json(file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(writeFile, f, indent=indent)
            return True
        except Exception as e:
            print(f"Error! {e}")
            return False

    @staticmethod
    def openFile(file: str, library: Optional[str] = None) -> Optional[str]:
        path = Paths.getPath(file, library)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"ERROR | {e}")
            return None

    @staticmethod
    def writeFile(file: str, content: str, library: Optional[str] = None) -> bool:
        path = Paths.getPath(file, library)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"ERROR | {e}")
            return False

    @staticmethod
    def listFiles(folder: str, library: Optional[str] = None, pattern: str = '*') -> list:
        path = Paths.getPath(folder, library)
        if not path.exists():
            return []
        return [p for p in path.glob(pattern) if p.is_file()]

    @staticmethod
    def join(*path) -> str:
        return str(Path(path[0]).joinpath(*path[1:]))
