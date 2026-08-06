import json
import logging
import shutil
import time
from base64 import b64decode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from src import Constants, FileContents, files, log, Utils, window
from src.tools import StageLuaParse, StageTool, VocalSplit, WeekTools
from src.tools import ModConvertTools as ModTools
from src.tools.CharacterTools import CharacterObject
from src.tools.ChartTools import ChartObject

logger = logging.getLogger('ModConverter')

ProgressCallback = Callable[[str, float], None]


@dataclass
class ConversionOptions:
    modpackMeta: bool = False
    chartSongs: bool = False
    chartEvents: bool = False
    characterAssets: bool = False
    characterJson: bool = False
    characterIcons: bool = False
    songInst: bool = False
    songVoices: bool = False
    songSplit: bool = False
    songSounds: bool = False
    songMusic: bool = False
    weekLevels: bool = False
    weekProps: bool = False
    weekTitles: bool = False
    stages: bool = False
    images: bool = False
    vocalSplitEnabled: bool = True

    @classmethod
    def fromDict(cls, options: dict) -> 'ConversionOptions':
        charts = options.get('charts', {})
        characters = options.get('characters', {})
        songs = options.get('songs', {})
        weeks = options.get('weeks', {})
        return cls(
            modpackMeta=options.get('modpack_meta', False),
            chartSongs=charts.get('songs', False),
            chartEvents=charts.get('events', False),
            characterAssets=characters.get('assets', False),
            characterJson=characters.get('json', False),
            characterIcons=characters.get('icons', False),
            songInst=songs.get('inst', False),
            songVoices=songs.get('voices', False),
            songSplit=songs.get('split', False),
            songSounds=songs.get('sounds', False),
            songMusic=songs.get('music', False),
            weekLevels=weeks.get('levels', False),
            weekProps=weeks.get('props', False),
            weekTitles=weeks.get('titles', False),
            stages=options.get('stages', False),
            images=options.get('images', False),
        )


@dataclass
class ChartEntry:
    songKey: str
    sections: list
    bpm: float
    player: str
    opponent: str


@dataclass
class ConversionReport:
    filesCopied: int = 0
    filesFailed: int = 0
    scriptsConverted: int = 0
    scriptsSkipped: int = 0
    errors: list = field(default_factory=list)
    startedAt: float = 0.0
    finishedAt: float = 0.0

    @property
    def elapsedSeconds(self) -> float:
        return self.finishedAt - self.startedAt

    def logError(self, message: str) -> None:
        logger.error(message)
        self.errors.append(message)

    def summary(self) -> str:
        return (
            f'{self.filesCopied} files copied, {self.filesFailed} failed, '
            f'{self.scriptsConverted} scripts converted, {self.scriptsSkipped} skipped, '
            f'{len(self.errors)} errors, {self.elapsedSeconds:.2f}s elapsed'
        )


class ModConverter:
    def __init__(
        self,
        psychModFolder: str,
        resultFolder: str,
        options: dict,
        progressCallback: Optional[ProgressCallback] = None,
    ):
        self.modRoot = Path(psychModFolder)
        self.modFoldername = self.modRoot.name
        self.resultRoot = Path(resultFolder) / self.modFoldername
        self.options = ConversionOptions.fromDict(options)
        self.progressCallback = progressCallback
        self.report = ConversionReport()
        self.charts: list = []
        self.characterMap: dict = {}

    def _notify(self, stage: str, fraction: float) -> None:
        logger.info(stage)
        if self.progressCallback is not None:
            try:
                self.progressCallback(stage, fraction)
            except Exception as e:
                logger.error(f'Progress callback failed: {e}')

    def _ensureDir(self, path: Path) -> bool:
        if path.exists():
            return True
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.report.logError(f'Could not create folder {path}: {e}')
            return False

    def _copyFile(self, source: Path, destination: Path) -> bool:
        source = Path(source)
        destination = Path(destination)
        if not source.exists():
            self.report.logError(f'Path {source} does not exist')
            return False
        if not self._ensureDir(destination.parent):
            return False
        try:
            shutil.copyfile(source, destination)
            self.report.filesCopied += 1
            return True
        except Exception as e:
            self.report.logError(f'Could not copy {source} to {destination}: {e}')
            self.report.filesFailed += 1
            return False

    def _copyTree(self, source: Path, destination: Path) -> bool:
        source = Path(source)
        destination = Path(destination)
        if destination.exists():
            return True
        if not source.exists():
            self.report.logError(f'Path {source} does not exist')
            return False
        try:
            shutil.copytree(source, destination)
            return True
        except Exception as e:
            self.report.logError(f'Could not copy tree {source} to {destination}: {e}')
            return False

    def _readJson(self, path: Path) -> Optional[dict]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.report.logError(f'Could not read json {path}: {e}')
            return None

    def _writeJson(self, path: Path, data: dict, indent: int = 4) -> bool:
        if not self._ensureDir(path.parent):
            return False
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent)
            return True
        except Exception as e:
            self.report.logError(f'Could not write json {path}: {e}')
            return False

    def _writeText(self, path: Path, text: str) -> bool:
        if not self._ensureDir(path.parent):
            return False
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except Exception as e:
            self.report.logError(f'Could not write file {path}: {e}')
            return False

    def _readText(self, path: Path) -> Optional[str]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.report.logError(f'Could not read file {path}: {e}')
            return None

    def _bgPath(self, relative: str) -> Path:
        return self.resultRoot / relative.lstrip('/')

    def _psychPath(self, relative: str) -> Path:
        return self.modRoot / relative.lstrip('/')

    def convert(self) -> ConversionReport:
        self.report.startedAt = time.time()
        logger.info(Utils.coolText('NEW CONVERSION STARTED'))
        logger.info(self.options)

        steps = [
            (self.options.modpackMeta, 'Converting modpack metadata', self._convertModpackMeta),
            (self.options.chartSongs, 'Converting charts', self._convertCharts),
            (self.options.chartEvents, 'Converting script events', self._convertScriptEvents),
            (self.options.characterAssets, 'Copying character assets', self._convertCharacterAssets),
            (self.options.characterJson, 'Converting character data', self._convertCharacterJsons),
            (self.options.characterIcons, 'Copying character icons', self._convertCharacterIcons),
            (True, 'Converting songs', self._convertSongs),
            (self.options.weekLevels, 'Converting week levels', self._convertWeekLevels),
            (self.options.weekProps, 'Copying week props', self._convertWeekProps),
            (self.options.weekTitles, 'Copying week titles', self._convertWeekTitles),
            (self.options.stages, 'Converting stages', self._convertStages),
            (self.options.images, 'Copying images', self._convertImages),
        ]

        activeSteps = [step for step in steps if step[0]]
        for index, (_, label, handler) in enumerate(activeSteps):
            self._notify(label, index / max(len(activeSteps), 1))
            handler()

        self.report.finishedAt = time.time()
        self._notify('Conversion completed', 1.0)
        logger.info(Utils.coolText('CONVERSION COMPLETED'))
        logger.info(self.report.summary())
        return self.report

    def _convertModpackMeta(self) -> None:
        creditsDir = Constants.FILE_LOCS.get('CREDITSTXT')
        psychCredits = self._psychPath(creditsDir[0])
        contributors = []

        if psychCredits.exists():
            rawCredits = self._readText(psychCredits)
            if rawCredits is not None:
                contributors = ModTools.parseCreditsFile(rawCredits)

        packJsonDir = Constants.FILE_LOCS.get('PACKJSON')
        psychPackJson = self._psychPath(packJsonDir[0])
        bgPackJson = self._bgPath(packJsonDir[1])

        if psychPackJson.exists():
            raw = self._readJson(psychPackJson)
            if raw is not None:
                try:
                    converted = ModTools.convertPack(raw, contributors=contributors)
                    self._writeJson(bgPackJson, converted)
                except Exception as e:
                    self.report.logError(f'Could not convert pack.json: {e}')
        else:
            self._writeJson(bgPackJson, ModTools.defaultPolymodMeta())
            logger.warning('pack.json not found, replaced it with default')

        packPngDir = Constants.FILE_LOCS.get('PACKPNG')
        psychPackPng = self._psychPath(packPngDir[0])
        bgPackPng = self._bgPath(packPngDir[1])

        if psychPackPng.exists():
            self._copyFile(psychPackPng, bgPackPng)
        else:
            logger.warning('pack.png not found, replacing it with default')
            if self._ensureDir(bgPackPng.parent):
                try:
                    with open(bgPackPng, 'wb') as f:
                        f.write(b64decode(Constants.BASE64_IMAGES.get('missingModImage')))
                except Exception as e:
                    self.report.logError(f'Could not write default pack.png: {e}')

        bgCredits = self._bgPath(creditsDir[1])
        if psychCredits.exists():
            self._writeText(bgCredits, ModTools.creditsFromContributors(contributors))
        else:
            self.report.logError(f'Could not find {psychCredits}')

    def _convertCharts(self) -> None:
        chartFolderDir = Constants.FILE_LOCS.get('CHARTFOLDER')
        psychChartFolder = self._psychPath(chartFolderDir[0])
        bgChartFolder = self._bgPath(chartFolderDir[1])
        self._ensureDir(bgChartFolder)

        for song in files.findAll(f'{psychChartFolder}*'):
            songPath = Path(song)
            if not songPath.is_dir():
                continue

            outputPath = self.resultRoot
            try:
                songChart = ChartObject(song, str(outputPath), self.options.chartEvents)
            except FileNotFoundError:
                logger.warning(f'{song} data not found, skipping')
                continue
            except Exception as e:
                self.report.logError(f'Error creating ChartObject for {song}: {e}')
                continue

            songChart.convert()

            try:
                self.charts.append(ChartEntry(
                    songKey=songChart.songFile,
                    sections=songChart.sections,
                    bpm=songChart.startingBpm,
                    player=songChart.metadata['playData']['characters']['player'],
                    opponent=songChart.metadata['playData']['characters']['opponent'],
                ))
            except Exception as e:
                self.report.logError(f'Could not create chart entry for {song}: {e}')

            try:
                songChart.save()
            except Exception as e:
                self.report.logError(f'Could not save chart {song}: {e}')

    def _convertScriptEvents(self) -> None:
        scriptsDir = Constants.FILE_LOCS.get('SCRIPTS_DIR')
        psychScripts = self._psychPath(scriptsDir[0])
        bgScripts = self._bgPath(scriptsDir[1])

        if not self._ensureDir(bgScripts):
            return

        if not psychScripts.exists():
            logger.warning(f'{psychScripts} does not exist, skipping script conversion')
            return

        result = FileContents.convertLuaFolder(psychScripts, bgScripts)
        self.report.scriptsConverted += len(result['converted'])
        self.report.scriptsSkipped += len(result['skipped'])

        for luaFile, hxcFile in result['converted']:
            logger.info(f'Converted script {luaFile.name} -> {hxcFile.name}')

        for luaFile in result['skipped']:
            logger.warning(f'No known hxc conversion for script {luaFile.name}')

    def _convertCharacterAssets(self) -> None:
        dir = Constants.FILE_LOCS.get('CHARACTERASSETS')
        psychAssets = self._psychPath(dir[0])
        bgAssets = self._bgPath(dir[1])
        self._ensureDir(bgAssets)

        for character in files.findAll(f'{psychAssets}*'):
            characterPath = Path(character)
            if characterPath.is_file():
                self._copyFile(characterPath, bgAssets / characterPath.name)
            else:
                logger.warning(f'{character} is a directory, not a file, skipped')

    def _convertCharacterJsons(self) -> None:
        dir = Constants.FILE_LOCS.get('CHARACTERJSONS')
        psychCharacters = self._psychPath(dir[0])
        bgCharacters = self._bgPath(dir[1])
        self._ensureDir(bgCharacters)

        for character in files.findAll(f'{psychCharacters}*'):
            characterPath = Path(character)
            if not (characterPath.is_file() and character.endswith('.json')):
                logger.warning(f'{character} is a directory or not a json, skipped')
                continue

            try:
                convertedChar = CharacterObject(character, str(bgCharacters))
                convertedChar.convert()
                convertedChar.save()

                fileBasename = convertedChar.iconID.replace('icon-', '')
                self.characterMap.setdefault(fileBasename, []).append(convertedChar.characterName)
                logger.info(f'Saved {convertedChar.characterName} under icon id {fileBasename}')
            except Exception as e:
                self.report.logError(f'Failed to convert character {character}: {e}')

    def _convertCharacterIcons(self) -> None:
        dir = Constants.FILE_LOCS.get('CHARACTERICON')
        psychIcons = self._psychPath(dir[0])
        bgIcons = self._bgPath(dir[1])
        freeplayDir = self._bgPath(Constants.FILE_LOCS.get('FREEPLAYICON')[1])

        self._ensureDir(bgIcons)
        self._ensureDir(freeplayDir)

        logging.getLogger('PIL').setLevel(logging.INFO)

        for character in files.findAll(f'{psychIcons}*.png'):
            characterPath = Path(character)
            if not characterPath.is_file():
                continue

            filename = characterPath.name
            if not filename.startswith('icon-'):
                logger.warning(f"Invalid icon name '{filename}' renamed to 'icon-{filename}'")
                filename = 'icon-' + filename

            destination = bgIcons / filename
            if not self._copyFile(characterPath, destination):
                continue

            keyForThisIcon = filename.replace('icon-', '').replace('.png', '')
            if keyForThisIcon not in self.characterMap:
                continue

            try:
                with Image.open(characterPath) as img:
                    normalHalf = img.crop((0, 0, 150, 150))
                    pixelImg = normalHalf.resize((50, 50), Image.Resampling.NEAREST)

                    for characterName in self.characterMap[keyForThisIcon]:
                        pixelName = f'{characterName}pixel.png'
                        freeplayDestination = freeplayDir / pixelName
                        pixelImg.save(freeplayDestination)
                        logger.info(f'Saved freeplay icon to {freeplayDestination}')
            except Exception as e:
                self.report.logError(f"Failed to create freeplay icon for {keyForThisIcon}: {e}")

    def _findChart(self, songKey: str):
        for chart in self.charts:
            if chart.songKey == songKey:
                return chart
        return None

    def _convertSongs(self) -> None:
        dir = Constants.FILE_LOCS.get('SONGS')
        psychSongs = self._psychPath(dir[0])
        bgSongsBase = dir[1]

        for song in files.findAll(f'{psychSongs}*'):
            songPath = Path(song)
            if not songPath.is_dir():
                continue

            songKeyUnformatted = songPath.name
            songKeyFormatted = songKeyUnformatted.replace(' ', '-').lower()
            songDestination = self._bgPath(bgSongsBase) / songKeyFormatted

            audioFiles = files.findAll(f'{song}/*')
            audioNames = [Path(f).name for f in audioFiles]
            isPsych073Song = 'Voices-Opponent.ogg' in audioNames and 'Voices-Player.ogg' in audioNames

            for songFile in audioFiles:
                songFilePath = Path(songFile)
                fileName = songFilePath.name

                if fileName == 'Inst.ogg' and self.options.songInst:
                    self._copyFile(songFilePath, songDestination / fileName)

                elif fileName == 'Voices.ogg' and self.options.songSplit and self.options.vocalSplitEnabled and not isPsych073Song:
                    self._splitVocals(songKeyUnformatted, song, str(songDestination) + '/')

                elif isPsych073Song and fileName in ('Voices-Player.ogg', 'Voices-Opponent.ogg'):
                    self._copyPsych073Voice(songKeyUnformatted, songKeyFormatted, songFilePath, songDestination)

                elif self.options.songVoices and fileName.startswith('Voices'):
                    if not self.options.vocalSplitEnabled:
                        logger.warning('Vocal Split is disabled, copying instead')
                    self._copyFile(songFilePath, songDestination / fileName)

            if self.options.songSounds:
                self._convertSongSounds()

            if self.options.songMusic:
                self._convertSongMusic()

    def _splitVocals(self, songKey: str, sourceFolder: str, resultPath: str) -> None:
        chart = self._findChart(songKey)
        if chart is None:
            logger.warning(f'No chart found for {songKey}, copying vocals instead')
            self._copyFile(Path(sourceFolder) / 'Voices.ogg', Path(resultPath) / 'Voices.ogg')
            return

        songChars = [chart.player, chart.opponent]
        logger.info(f'Running vocal split for {songKey} at {chart.bpm} BPM')

        try:
            VocalSplit.vocalsplit(chart.sections, chart.bpm, f'{sourceFolder}/', resultPath, songKey, songChars)
        except Exception as e:
            self.report.logError(f'Vocal split failed for {songKey}: {e}')

    def _copyPsych073Voice(self, songKey: str, songKeyFormatted: str, songFilePath: Path, songDestination: Path) -> None:
        chart = self._findChart(songKey)
        if chart is None:
            logger.warning(f'{songKeyFormatted} has separated vocals but no chart was found, copying as-is')
            self._copyFile(songFilePath, songDestination / songFilePath.name)
            return

        try:
            playData = chart.__dict__ if not hasattr(chart, 'metadata') else chart
            if songFilePath.name == 'Voices-Player.ogg':
                targetName = f'Voices-{chart.player}.ogg'
            else:
                targetName = f'Voices-{chart.opponent}.ogg'
            self._copyFile(songFilePath, songDestination / targetName)
        except Exception as e:
            self.report.logError(f'Could not rename Psych 0.7.3 vocal file {songFilePath}: {e}')

    def _convertSongSounds(self) -> None:
        dir = Constants.FILE_LOCS.get('SOUNDS')
        psychSounds = self._psychPath(dir[0])
        bgSounds = self._bgPath(dir[1])

        for asset in files.findAll(f'{psychSounds}*'):
            assetPath = Path(asset)
            if assetPath.is_dir():
                self._copyTree(assetPath, bgSounds / assetPath.name)
            else:
                self._copyFile(assetPath, bgSounds / assetPath.name)

    def _convertSongMusic(self) -> None:
        dir = Constants.FILE_LOCS.get('MUSIC')
        psychMusic = self._psychPath(dir[0])
        bgMusic = self._bgPath(dir[1])

        for asset in files.findAll(f'{psychMusic}*'):
            assetPath = Path(asset)
            self._copyFile(assetPath, bgMusic / assetPath.name)

    def _convertWeekLevels(self) -> None:
        dir = Constants.FILE_LOCS.get('WEEKS')
        psychWeeks = self._psychPath(dir[0])
        bgLevels = self._bgPath(dir[1])
        self._ensureDir(bgLevels)

        for week in files.findAll(f'{psychWeeks}*.json'):
            weekPath = Path(week)
            weekJson = self._readJson(weekPath)
            if weekJson is None:
                continue

            try:
                convertedWeek = WeekTools.convert(weekJson, str(self.modRoot), weekPath.name)
                self._writeJson(bgLevels / weekPath.name, convertedWeek)
            except Exception as e:
                self.report.logError(f'Error converting week {week}: {e}')

    def _convertWeekProps(self) -> None:
        dir = Constants.FILE_LOCS.get('WEEKCHARACTERASSET')
        psychAssets = self._psychPath(dir[0])
        bgAssets = self._bgPath(dir[1])

        assetFiles = files.findAll(f'{psychAssets}*.xml') + files.findAll(f'{psychAssets}*.png')
        for asset in assetFiles:
            assetPath = Path(asset)
            self._copyFile(assetPath, bgAssets / assetPath.name)

    def _convertWeekTitles(self) -> None:
        dir = Constants.FILE_LOCS.get('WEEKIMAGE')
        psychWeeks = self._psychPath(dir[0])
        bgLevels = self._bgPath(dir[1])

        for asset in files.findAll(f'{psychWeeks}*.png'):
            assetPath = Path(asset)
            self._copyFile(assetPath, bgLevels / assetPath.name)

    def _convertStages(self) -> None:
        dir = Constants.FILE_LOCS.get('STAGE')
        psychStages = self._psychPath(dir[0])
        bgStages = self._bgPath(dir[1])
        self._ensureDir(bgStages)

        for asset in files.findAll(f'{psychStages}*.json'):
            assetPath = Path(asset)
            stageJson = self._readJson(assetPath)
            if stageJson is None:
                continue

            stageLua = assetPath.with_suffix('.lua')
            luaProps = []
            if stageLua.exists():
                try:
                    luaProps = StageLuaParse.parseStage(str(stageLua))
                except Exception as e:
                    self.report.logError(f'Could not parse {stageLua}: {e}')
                    continue

            try:
                converted = StageTool.convert(stageJson, assetPath.name, luaProps)
                self._writeJson(bgStages / assetPath.name, converted)
            except Exception as e:
                self.report.logError(f'Could not convert stage {asset}: {e}')

    def _convertImages(self) -> None:
        dir = Constants.FILE_LOCS.get('IMAGES')
        psychImages = self._psychPath(dir[0])
        bgImages = self._bgPath(dir[1])
        self._ensureDir(bgImages)

        excludeFolders = Constants.EXCLUDE_FOLDERS_IMAGES.get('PsychEngine', [])

        for asset in files.findAll(f'{psychImages}*'):
            assetPath = Path(asset)

            if assetPath.is_dir():
                if assetPath.name in excludeFolders:
                    logger.warning(f'{asset} is excluded, skipped')
                    continue
                self._copyTree(assetPath, bgImages / assetPath.name)
            else:
                self._copyFile(assetPath, bgImages / assetPath.name)


def convert(psych_mod_folder: str, result_folder: str, options: dict, progressCallback: Optional[ProgressCallback] = None) -> ConversionReport:
    converter = ModConverter(psych_mod_folder, result_folder, options, progressCallback)
    return converter.convert()


if __name__ == '__main__':
    log.setup()
    window.init()
