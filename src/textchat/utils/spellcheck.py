import re
import sys
from collections.abc import Callable
from ctypes import cdll
from ctypes import util

from rich.highlighter import Highlighter
from rich.text import Text


WORD_PATTERN = re.compile(r"[^\W\d_][\w'’-]*", re.UNICODE)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
IRC_PREFIXES = "#&!+@"
DEFAULT_SPELLCHECK_ENABLED = True
DEFAULT_SPELLCHECK_DELAY_MS = 500
DEFAULT_SPELLCHECK_SUGGESTION_LIMIT = 3


def should_skip_spellcheck(
    value: str,
    start: int,
    end: int,
    word: str,
    ignored_words: set[str],
) -> bool:
    """Return whether an IRC-specific token should bypass spell checking."""
    previous = value[start - 1] if start else ""
    return (
        len(word) < 2
        or word.casefold() in ignored_words
        or (previous and previous in IRC_PREFIXES + "/")
        or any(
            start >= url_match.start() and end <= url_match.end()
            for url_match in URL_PATTERN.finditer(value)
        )
    )


class MacOSSpellChecker:
    """Thin, failure-safe wrapper around macOS's spelling service."""

    def __init__(self) -> None:
        self._checker = None
        self._not_found = None
        self._unavailable = False

    def _get_checker(self):
        if sys.platform != "darwin" or self._unavailable:
            return None
        if self._checker is not None:
            return self._checker

        appkit = util.find_library("AppKit")
        if appkit is None:
            return None

        try:
            cdll.LoadLibrary(appkit)
            from rubicon.objc import NSNotFound
            from rubicon.objc import ObjCClass

            self._checker = ObjCClass("NSSpellChecker").sharedSpellChecker
            self._not_found = NSNotFound
        except Exception:
            return None

        try:
            result = self._checker.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
                "textchatspellcheckprobezz",
                0,
                "en",
                False,
                0,
                None,
            )
        except Exception:
            self._unavailable = True
            self._checker = None
            return None
        if result.location == self._not_found:
            self._unavailable = True
            self._checker = None
            return None
        return self._checker

    def is_misspelled(self, word: str) -> bool | None:
        """Return whether macOS considers one word misspelled."""
        checker = self._get_checker()
        if checker is None:
            return None

        try:
            result = checker.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
                word,
                0,
                "en",
                False,
                0,
                None,
            )
        except Exception:
            self._unavailable = True
            self._checker = None
            return None
        return result.location != self._not_found

    def correction(self, word: str) -> None:
        return None

    def suggestions(self, word: str, limit: int) -> list[str]:
        return []


class PythonSpellChecker:
    """Cross-platform fallback spell checker backed by pyspellchecker."""

    def __init__(self) -> None:
        self._checker = None
        self._unavailable = False

    def _get_checker(self):
        if self._unavailable:
            return None
        if self._checker is not None:
            return self._checker

        try:
            from spellchecker import SpellChecker

            self._checker = SpellChecker(language="en")
        except (ImportError, OSError):
            self._unavailable = True
            return None
        return self._checker

    def is_misspelled(self, word: str) -> bool | None:
        checker = self._get_checker()
        if checker is None:
            return None
        return word.casefold() in checker.unknown([word])

    def correction(self, word: str) -> str | None:
        checker = self._get_checker()
        if checker is None:
            return None
        return checker.correction(word)

    def suggestions(self, word: str, limit: int) -> list[str]:
        checker = self._get_checker()
        if checker is None or word.casefold() not in checker.unknown([word]):
            return []

        candidates = checker.candidates(word) or set()
        correction = checker.correction(word)
        ordered = sorted(
            (candidate for candidate in candidates if candidate != correction),
            key=lambda candidate: (-checker.word_usage_frequency(candidate), candidate),
        )
        if correction is not None:
            ordered.insert(0, correction)
        return ordered[:limit]


class FallbackSpellChecker:
    def __init__(
        self, primary: MacOSSpellChecker, fallback: PythonSpellChecker
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def is_misspelled(self, word: str) -> bool:
        primary_result = self._primary.is_misspelled(word)
        if primary_result is not None:
            return primary_result
        return bool(self._fallback.is_misspelled(word))

    def correction(self, word: str) -> str | None:
        correction = self._primary.correction(word)
        return correction if correction is not None else self._fallback.correction(word)

    def suggestions(self, word: str, limit: int) -> list[str]:
        suggestions = self._primary.suggestions(word, limit)
        return suggestions or self._fallback.suggestions(word, limit)


class SpellcheckHighlighter(Highlighter):
    """Underline misspelled prose while leaving IRC-specific text alone."""

    def __init__(
        self,
        ignored_words: Callable[[], set[str]],
        is_ready: Callable[[], bool] = lambda: True,
    ) -> None:
        super().__init__()
        self._ignored_words = ignored_words
        self._is_ready = is_ready
        self._checker = (
            FallbackSpellChecker(MacOSSpellChecker(), PythonSpellChecker())
            if sys.platform == "darwin"
            else PythonSpellChecker()
        )

    def highlight(self, text: Text) -> None:
        if not self._is_ready():
            return
        value = text.plain
        ignored = {word.casefold() for word in self._ignored_words()}

        for match in WORD_PATTERN.finditer(value):
            word = match.group()
            start, end = match.span()

            if should_skip_spellcheck(value, start, end, word, ignored):
                continue

            if self._checker.is_misspelled(word):
                text.stylize("underline bold #ff5f5f", start, end)

    def correction(self, word: str) -> str | None:
        """Return the best correction offered by the active spell checker."""
        return self._checker.correction(word)

    def suggestions(self, word: str, limit: int) -> list[str]:
        return self._checker.suggestions(word, limit)
