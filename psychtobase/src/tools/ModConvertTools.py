import logging
from dataclasses import dataclass
from typing import Optional

from .. import Constants

logger = logging.getLogger('ModConvertTools')

POLYMOD_API_VERSION = '0.8.4'
DEFAULT_MOD_VERSION = '1.0.0'
DEFAULT_LICENSE = 'Apache-2.0'


@dataclass
class Contributor:
    name: str
    icon: str = ''
    role: str = ''
    social: str = ''
    color: str = ''

    def toPolymodEntry(self) -> dict:
        return {
            'name': self.name,
            'role': self.role or 'Contributor',
        }


def generateDescription(name: str = 'Untitled Mod') -> str:
    return f'{name} by Unknown creator. Converted by FNF Porter v{Constants.VERSION}'


def parseCreditsLine(line: str) -> Optional[Contributor]:
    parts = [part.strip() for part in line.split('::')]
    if len(parts) < 2 or not parts[0]:
        return None

    return Contributor(
        name=parts[0],
        icon=parts[1] if len(parts) > 1 else '',
        role=parts[2] if len(parts) > 2 else '',
        social=parts[3] if len(parts) > 3 else '',
        color=parts[4] if len(parts) > 4 else '',
    )


def parseCreditsFile(text: str) -> list:
    contributors = []
    for lineNumber, rawLine in enumerate(text.split('\n'), start=1):
        line = rawLine.strip()
        if not line:
            continue

        contributor = parseCreditsLine(line)
        if contributor is None:
            logger.warning(f'Skipped malformed credits line {lineNumber}: {line}')
            continue

        contributors.append(contributor)

    return contributors


def creditsFromContributors(contributors: list) -> str:
    lines = ['Mod credits']

    for contributor in contributors:
        roleText = contributor.role or 'Contributor'
        socialText = f' ({contributor.social})' if contributor.social else ''
        lines.append(f'{roleText} - {contributor.name}{socialText}')

    return '\n'.join(lines)


def convertCredits(text: str) -> str:
    return creditsFromContributors(parseCreditsFile(text))


def convertPack(
    packJson: dict,
    contributors: Optional[list] = None,
    license: str = DEFAULT_LICENSE,
) -> dict:
    title = packJson.get('name') or packJson.get('title') or 'Untitled Mod'
    description = packJson.get('description') or generateDescription(title)
    modVersion = packJson.get('mod_version', DEFAULT_MOD_VERSION)

    result = {
        'title': title,
        'description': description,
        'contributors': [c.toPolymodEntry() for c in (contributors or [])],
        'api_version': POLYMOD_API_VERSION,
        'mod_version': modVersion,
        'license': license,
    }

    dependencies = packJson.get('dependencies')
    if dependencies:
        result['dependencies'] = dependencies

    optionalDependencies = packJson.get('optionalDependencies')
    if optionalDependencies:
        result['optionalDependencies'] = optionalDependencies

    return result


def defaultPolymodMeta(license: str = DEFAULT_LICENSE) -> dict:
    return {
        'title': 'Untitled Mod',
        'description': generateDescription(),
        'contributors': [],
        'api_version': POLYMOD_API_VERSION,
        'mod_version': DEFAULT_MOD_VERSION,
        'license': license,
    }
