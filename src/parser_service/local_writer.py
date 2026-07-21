from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pydantic import BaseModel


class LocalEventWriter:
    def __init__(
        self,
        output_directory: str | Path,
    ) -> None:
        self.output_directory = Path(
            output_directory
        )

        self.output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    def write_events(
        self,
        filename: str,
        events: Iterable[BaseModel],
    ) -> Path:
        output_path = (
            self.output_directory / filename
        )

        with output_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as output_file:
            for event in events:
                output_file.write(
                    event.model_dump_json(
                        by_alias=True,
                    )
                )

                output_file.write("\n")

        return output_path