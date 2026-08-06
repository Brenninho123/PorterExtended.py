import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScriptConversion:
    id: str
    hxcName: str
    hxcContents: str
    luaNameHints: list = field(default_factory=list)
    luaSignatures: list = field(default_factory=list)


class ScriptConversionRegistry:
    _entries: list = []

    @classmethod
    def register(cls, entry: ScriptConversion):
        cls._entries.append(entry)
        return entry

    @classmethod
    def findMatch(cls, luaFilename: str, luaContents: str) -> Optional[ScriptConversion]:
        normalizedName = luaFilename.lower().strip()
        for entry in cls._entries:
            if normalizedName in [hint.lower() for hint in entry.luaNameHints]:
                return entry

        bestMatch = None
        bestScore = 0
        for entry in cls._entries:
            score = sum(1 for sig in entry.luaSignatures if re.search(sig, luaContents, re.IGNORECASE))
            threshold = max(1, len(entry.luaSignatures) // 2)
            if score >= threshold and score > bestScore:
                bestScore = score
                bestMatch = entry
        return bestMatch

    @classmethod
    def all(cls):
        return list(cls._entries)


CHANGE_CHARACTER_EVENT = ScriptConversionRegistry.register(ScriptConversion(
    id='change-character-event',
    hxcName='ChangeCharacterEvent.hxc',
    hxcContents=CHANGE_CHARACTER_EVENT_HXC_CONTENTS,
    luaNameHints=['changecharacter.lua', 'change_character.lua', 'changecharacterevent.lua'],
    luaSignatures=[r'changeCharacter\s*\(', r'setCharacter\s*\(', r'CharacterType', r'boyfriend|dad|girlfriend']
))

COMBO_POSITION_NX = ScriptConversionRegistry.register(ScriptConversion(
    id='combo-position-nx',
    hxcName='ComboPositionNX.hxc',
    hxcContents="""import funkin.play.PlayState;
import funkin.modding.module.Module;
import funkin.modding.events.UpdateScriptEvent;
import flixel.FlxG;

class ComboPositionNX extends Module
{
	function new()
	{
		super('ComboPositionNX', 0, {state: PlayState});
	}

	function isTargetNoteStyle():Bool
	{
		var game = PlayState.instance;
		if (game == null || game.noteStyle == null) return false;
		return (game.noteStyle.id ?? '').toLowerCase() == 'nucleon';
	}

	override function onUpdate(event:UpdateScriptEvent)
	{
		super.onUpdate(event);

		if (!isTargetNoteStyle()) return;

		var game = PlayState.instance;
		if (game == null || game.comboPopUps == null) return;

		game.comboPopUps.offsets[0] = -450 - (FlxG.onMobile ? 100 : 0);
		game.comboPopUps.offsets[1] = game.playerStrumline.isDownscroll ? -175 : 350;
	}
}""",
    luaNameHints=['comboposition.lua', 'combo_position.lua', 'comboposition_nx.lua', 'combopositionnx.lua'],
    luaSignatures=[r'comboPopUps', r'noteStyle', r'nucleon', r'setPropertyFromGroup.*offset']
))


def convertLuaFile(luaPath, outputDir) -> Optional[Path]:
    luaPath = Path(luaPath)
    contents = luaPath.read_text(encoding='utf-8', errors='ignore')
    match = ScriptConversionRegistry.findMatch(luaPath.name, contents)
    if match is None:
        print(f"No known hxc conversion found for {luaPath.name}")
        return None

    outputPath = Path(outputDir)
    outputPath.mkdir(parents=True, exist_ok=True)
    targetFile = outputPath / match.hxcName
    targetFile.write_text(match.hxcContents, encoding='utf-8')
    print(f"Converted {luaPath.name} -> {match.hxcName}")
    return targetFile


def convertLuaFolder(luaFolder, outputDir) -> list:
    results = []
    for luaFile in Path(luaFolder).glob('*.lua'):
        converted = convertLuaFile(luaFile, outputDir)
        if converted:
            results.append(converted)
    return results
