from textchat.utils.spellcheck import DEFAULT_SPELLCHECK_DELAY_MS
from textchat.utils.spellcheck import DEFAULT_SPELLCHECK_ENABLED
from textchat.utils.spellcheck import DEFAULT_SPELLCHECK_SUGGESTION_LIMIT
from textchat.utils.spellcheck import should_skip_spellcheck
from textchat.utils.spellcheck import SpellcheckHighlighter
from textchat.utils.spellcheck import WORD_PATTERN
from textual import events
from textual import on
from textual.binding import Binding
from textual.widgets import Input


class ChatInput(Input):
    BINDINGS = [Binding("f2", "correct_word", "Correct spelling")]

    def __init__(self, *args, **kwargs) -> None:
        self._spellcheck_ready = True
        self._spellcheck_timer = None
        self._spellcheck_suggestion_state = None
        kwargs.setdefault(
            "highlighter",
            SpellcheckHighlighter(self._ignored_words, self._spellcheck_is_ready),
        )
        super().__init__(*args, **kwargs)

    def _spellcheck_settings(self) -> dict[str, int | bool]:
        """Get the current global spellcheck preferences with safe defaults."""
        defaults: dict[str, int | bool] = {
            "enabled": DEFAULT_SPELLCHECK_ENABLED,
            "delay_ms": DEFAULT_SPELLCHECK_DELAY_MS,
            "suggestion_limit": DEFAULT_SPELLCHECK_SUGGESTION_LIMIT,
        }
        try:
            settings = getattr(self.app, "spellcheck_settings", None)
        except Exception:
            settings = None
        return defaults if settings is None else defaults | settings

    def _spellcheck_is_ready(self) -> bool:
        return bool(self._spellcheck_settings()["enabled"] and self._spellcheck_ready)

    def _finish_spellcheck_delay(self) -> None:
        self._spellcheck_ready = True
        self.refresh()

    @on(Input.Changed)
    def debounce_spellcheck(self, event: Input.Changed) -> None:
        """Wait until typing pauses before asking a spell checker for results."""
        if event.input is not self:
            return

        self._spellcheck_ready = False
        if self._spellcheck_timer is not None:
            self._spellcheck_timer.stop()

        settings = self._spellcheck_settings()
        if settings["enabled"]:
            delay_seconds = int(settings["delay_ms"]) / 1000
            self._spellcheck_timer = self.set_timer(
                delay_seconds,
                self._finish_spellcheck_delay,
            )
        self.refresh()

    def _ignored_words(self) -> set[str]:
        """Return IRC words which should not be treated as spelling errors."""
        ignored = {"irc", "textchat", "znc"}
        app = getattr(self, "app", None)
        if app is None:
            return ignored

        for users in getattr(app, "channel_users", {}).values():
            ignored.update(user.lstrip("@+%&~") for user in users)
        nickname = getattr(getattr(app, "irc_client", None), "nickname", None)
        if nickname:
            ignored.add(nickname)
        return ignored

    def action_correct_word(self) -> None:
        """Replace the word at the cursor with the best spelling suggestion."""
        if not self._spellcheck_settings()["enabled"]:
            return
        highlighter = self.highlighter
        if not isinstance(highlighter, SpellcheckHighlighter):
            return

        cursor = self.cursor_position
        state = self._spellcheck_suggestion_state
        if state is not None and self.value == (
            state["before"] + state["candidates"][state["index"]] + state["after"]
        ):
            state["index"] = (state["index"] + 1) % len(state["candidates"])
            correction = state["candidates"][state["index"]]
            self.value = state["before"] + correction + state["after"]
            self.cursor_position = len(state["before"]) + len(correction)
            self.notify(
                f"Suggestion {state['index'] + 1}/{len(state['candidates'])}: {correction}",
                title="Spell check",
            )
            return

        for match in WORD_PATTERN.finditer(self.value):
            start, end = match.span()
            if not start <= cursor <= end:
                continue

            word = match.group()
            ignored = {item.casefold() for item in self._ignored_words()}
            if should_skip_spellcheck(self.value, start, end, word, ignored):
                return

            limit = int(self._spellcheck_settings()["suggestion_limit"])
            candidates = highlighter.suggestions(word, limit)
            if not candidates:
                return

            candidates = [
                self._match_word_case(word, candidate) for candidate in candidates
            ]
            correction = candidates[0]

            self.value = self.value[:start] + correction + self.value[end:]
            self.cursor_position = start + len(correction)
            self.nick_completion = None
            self._spellcheck_suggestion_state = {
                "before": self.value[:start],
                "after": self.value[start + len(correction) :],
                "candidates": candidates,
                "index": 0,
            }
            self.notify(
                f"Suggestion 1/{len(candidates)}: {correction}",
                title="Spell check",
            )
            return

    @staticmethod
    def _match_word_case(word: str, correction: str) -> str:
        if word.isupper():
            return correction.upper()
        if word.istitle():
            return correction.capitalize()
        return correction

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "tab" and self.app.complete_nickname(self):
            event.prevent_default()
            event.stop()
            return

        await super()._on_key(event)
