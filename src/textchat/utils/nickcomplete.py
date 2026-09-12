from dataclasses import dataclass


@dataclass
class NickCompletion:
    channel: str
    before: str
    after: str
    candidates: list[str]
    index: int
    suffix: str
    rendered_value: str
    cursor_position: int
