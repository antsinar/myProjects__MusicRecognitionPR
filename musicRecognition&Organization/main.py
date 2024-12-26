import asyncio
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import List

from aiohttp_retry import ExponentialRetry
from shazamio import HTTPClient, Shazam


class ColorCode(StrEnum):
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


class Extension(StrEnum):
    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    WAV = "wav"


def print_colored(text: str, color: ColorCode) -> None:
    """Prints text in the specified color, using ANSI escape codes.
    :param text: The text to print.
    :param color: The enum value to print the text in.
    """
    print(f"{color.value}{text}{ColorCode.RESET}")


def get_music_files_sync(directory: Path, extension: str) -> List[str]:
    """Returns a list of all files in the directory with the specified extension.
    :param directory: The directory to search for files.
    :param extension: The file extension to search for.
    :return: An **unordered** list of all files in the directory with the specified extension.
    Caution: Blocking function call.
    """
    return [path.as_posix() for path in directory.rglob(f"*.{extension}")]


async def process_music_files(
    client: Shazam, directory: Path, extension: str = "mp3"
) -> None:
    """Get the music file information and rename it, if possible.
    :param client: The Shazam client to use.
    :param directory: The directory to search for files.
    :param extension: The file extension to search for.
    :return: None
    """
    loop = asyncio.get_event_loop()

    get_files_partial = partial(get_music_files_sync, directory, extension)
    music_files: List[str] = await loop.run_in_executor(None, get_files_partial)

    if len(music_files) == 0:
        print_colored(
            f"[X] No music files with the extention {extension} found in {directory}.",
            ColorCode.RED,
        )
        return

    async with asyncio.TaskGroup() as tg:
        results = [tg.create_task(client.recognize(file)) for file in music_files]

    for result in results:
        working_file = music_files[results.index(result)]
        res = result.result()
        try:
            track = res["track"]
        except KeyError:
            print_colored(
                f"[X] No song information found for: {working_file}. Keeping the original name.",
                ColorCode.YELLOW,
            )
            continue
        title = track.get("title", "Unknown Title")
        artist = track.get("subtitle", "Unknown Artist")

        new_filename = f"{artist} - {title}.{extension}"

        new_filename = "".join(
            [c for c in new_filename if c.isalnum() or c in " -_."]
        ).replace(" ", "_")

        print_colored(
            f"[X] Renaming {working_file} to: {new_filename}", ColorCode.MAGENTA
        )
        Path(working_file).rename(directory / new_filename) if Path(
            working_file
        ).exists() else None


async def main() -> None:
    parser = ArgumentParser(
        description="Rename music files using Shazam API.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "directory",
        type=str,
        help="Path to the directory containing music files",
        default=".",
        nargs="?",
    )
    parser.add_argument(
        "-e",
        "--extension",
        type=str,
        help="File extension to search for",
        choices=list(Extension),
        default="mp3",
    )
    args: Namespace = parser.parse_args()
    target_dir = Path(args.directory).resolve()
    if not (target_dir.exists() or target_dir.is_dir()):
        print_colored(
            f"[X] The directory '{args.directory}' does not exist.", ColorCode.RED
        )
        exit(1)

    client = Shazam(
        http_client=HTTPClient(
            retry_options=ExponentialRetry(
                attempts=12, max_timeout=204.8, statuses={500, 502, 503, 504, 429}
            ),
        ),
    )
    await process_music_files(client, target_dir, extension=args.extension)


if __name__ == "__main__":
    asyncio.run(main())
