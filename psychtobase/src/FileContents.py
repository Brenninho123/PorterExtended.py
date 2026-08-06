import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger('FileContents')

EXAMPLES_DIR = Path(__file__).parent / 'examples'
MANIFEST_PATH = EXAMPLES_DIR / 'manifest.json'
NAME_MATCH_CONFIDENCE = 1.0
MIN_CONFIDENCE_THRESHOLD = 0.35


@dataclass
class ScriptConversion:
    id: str
    hxcFile: str
    description: str
    luaNameHints: list = field(default_factory=list)
    signatures: list = field(default_factory=list)
    keywords: list = field(default_factory=list)

    @property
    def hxcName(self) -> str:
        return self.hxcFile

    @lru_cache(maxsize=None)
    def loadContents(self) -> str:
        path = EXAMPLES_DIR / self.hxcFile
        return path.read_text(encoding='utf-8')

    def compiledSignatures(self):
        return [re.compile(sig, re.IGNORECASE) for sig in self.signatures]


@dataclass
class MatchResult:
    entry: ScriptConversion
    confidence: float
    matchedName: bool
    matchedSignatures: list
    matchedKeywords: list


class ScriptConversionRegistry:
    _entries: dict = {}
    _loaded: bool = False

    @classmethod
    def load(cls, manifestPath: Path = MANIFEST_PATH, force: bool = False) -> None:
        if cls._loaded and not force:
            return

        if not manifestPath.exists():
            raise FileNotFoundError(f'Manifest not found at {manifestPath}')

        data = json.loads(manifestPath.read_text(encoding='utf-8'))
        cls._entries = {}
        for raw in data.get('entries', []):
            entry = ScriptConversion(
                id=raw['id'],
                hxcFile=raw['hxcFile'],
                description=raw.get('description', ''),
                luaNameHints=raw.get('luaNameHints', []),
                signatures=raw.get('signatures', []),
                keywords=raw.get('keywords', []),
            )
            cls._entries[entry.id] = entry

        cls._loaded = True
        logger.info('Loaded %d script conversion entries', len(cls._entries))

    @classmethod
    def all(cls) -> list:
        cls.load()
        return list(cls._entries.values())

    @classmethod
    def get(cls, entryId: str) -> Optional[ScriptConversion]:
        cls.load()
        return cls._entries.get(entryId)

    @classmethod
    def register(cls, entry: ScriptConversion) -> ScriptConversion:
        cls.load()
        cls._entries[entry.id] = entry
        return entry

    @classmethod
    def _tokenize(cls, text: str) -> set:
        return set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower()))

    @classmethod
    def score(cls, entry: ScriptConversion, luaFilename: str, luaContents: str, luaTokens: set) -> MatchResult:
        normalizedName = luaFilename.lower().strip()
        matchedName = normalizedName in [hint.lower() for hint in entry.luaNameHints]

        matchedSignatures = [
            pattern.pattern for pattern in entry.compiledSignatures()
            if pattern.search(luaContents)
        ]
        signatureScore = (
            len(matchedSignatures) / len(entry.signatures)
            if entry.signatures else 0.0
        )

        entryKeywordTokens = {kw.lower() for kw in entry.keywords}
        matchedKeywords = sorted(entryKeywordTokens & luaTokens)
        keywordScore = (
            len(matchedKeywords) / len(entryKeywordTokens)
            if entryKeywordTokens else 0.0
        )

        confidence = 0.55 * signatureScore + 0.45 * keywordScore
        if matchedName:
            confidence = NAME_MATCH_CONFIDENCE

        return MatchResult(
            entry=entry,
            confidence=confidence,
            matchedName=matchedName,
            matchedSignatures=matchedSignatures,
            matchedKeywords=matchedKeywords,
        )

    @classmethod
    def rank(cls, luaFilename: str, luaContents: str) -> list:
        cls.load()
        luaTokens = cls._tokenize(luaContents)
        results = [
            cls.score(entry, luaFilename, luaContents, luaTokens)
            for entry in cls._entries.values()
        ]
        return sorted(results, key=lambda r: r.confidence, reverse=True)

    @classmethod
    def findMatch(cls, luaFilename: str, luaContents: str, threshold: float = MIN_CONFIDENCE_THRESHOLD) -> Optional[MatchResult]:
        ranked = cls.rank(luaFilename, luaContents)
        if not ranked:
            return None

        best = ranked[0]
        if best.confidence >= threshold:
            return best

        return None


def convertLuaFile(luaPath, outputDir, threshold: float = MIN_CONFIDENCE_THRESHOLD) -> Optional[Path]:
    luaPath = Path(luaPath)
    contents = luaPath.read_text(encoding='utf-8', errors='ignore')
    match = ScriptConversionRegistry.findMatch(luaPath.name, contents, threshold)

    if match is None:
        logger.warning('No known hxc conversion found for %s', luaPath.name)
        return None

    outputPath = Path(outputDir)
    outputPath.mkdir(parents=True, exist_ok=True)
    targetFile = outputPath / match.entry.hxcName
    targetFile.write_text(match.entry.loadContents(), encoding='utf-8')

    logger.info(
        'Converted %s -> %s (confidence %.2f, name match: %s)',
        luaPath.name, match.entry.hxcName, match.confidence, match.matchedName
    )
    return targetFile


def convertLuaFolder(luaFolder, outputDir, threshold: float = MIN_CONFIDENCE_THRESHOLD) -> dict:
    converted = []
    skipped = []

    for luaFile in sorted(Path(luaFolder).glob('*.lua')):
        result = convertLuaFile(luaFile, outputDir, threshold)
        if result is not None:
            converted.append((luaFile, result))
        else:
            skipped.append(luaFile)

    return {'converted': converted, 'skipped': skipped}


def explainMatch(luaFilename: str, luaContents: str, topN: int = 3) -> str:
    ranked = ScriptConversionRegistry.rank(luaFilename, luaContents)[:topN]
    lines = [f'Top {len(ranked)} candidates for {luaFilename}:']
    for result in ranked:
        lines.append(
            f'  {result.entry.id} -> confidence {result.confidence:.2f} '
            f'(name match: {result.matchedName}, '
            f'signatures: {len(result.matchedSignatures)}/{len(result.entry.signatures)}, '
            f'keywords: {len(result.matchedKeywords)}/{len(result.entry.keywords)})'
        )
    return '\n'.join(lines)


if __name__ == '__main__':
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

    parser = argparse.ArgumentParser(description='Convert known Lua scripts to their hxc equivalents')
    parser.add_argument('luaFolder', help='Folder containing .lua files to scan')
    parser.add_argument('outputDir', help='Folder to write matched .hxc files into')
    parser.add_argument('--threshold', type=float, default=MIN_CONFIDENCE_THRESHOLD)
    parser.add_argument('--explain', action='store_true', help='Print top candidates for skipped files')
    args = parser.parse_args()

    report = convertLuaFolder(args.luaFolder, args.outputDir, args.threshold)

    print(f"Converted: {len(report['converted'])}")
    for luaFile, hxcFile in report['converted']:
        print(f'  {luaFile.name} -> {hxcFile.name}')

    print(f"Skipped: {len(report['skipped'])}")
    for luaFile in report['skipped']:
        print(f'  {luaFile.name}')
        if args.explain:
            contents = luaFile.read_text(encoding='utf-8', errors='ignore')
            print(explainMatch(luaFile.name, contents))
