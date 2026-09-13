import subprocess
import sys
from ctypes import cdll
from ctypes import util

from rubicon.objc import ObjCClass


if sys.platform == "darwin":
    from desktop_notifier import DesktopNotifier

    _notifier = DesktopNotifier(app_name="TextChat")
else:
    _notifier = None


def iterm2_is_foreground() -> bool:
    """Return True when iTerm2 is the active macOS application."""
    if _notifier is None:
        return False

    appkit = util.find_library("AppKit")
    if appkit is None:
        return False
    cdll.LoadLibrary(appkit)

    workspace_class = ObjCClass("NSWorkspace")
    workspace_class.declare_class_property("sharedWorkspace")
    workspace = workspace_class.sharedWorkspace
    frontmost_app = workspace.frontmostApplication

    return (
        frontmost_app is not None
        and str(frontmost_app.bundleIdentifier) == "com.googlecode.iterm2"
    )


def activate_iterm2() -> None:
    """Launch iTerm2 if needed, or bring it to the foreground."""
    subprocess.run(
        ["open", "-b", "com.googlecode.iterm2"],
        check=False,
    )


async def send_desktop_notification(title: str, message: str) -> None:
    """Send a native macOS notification, or do nothing on other platforms."""
    if _notifier is None or iterm2_is_foreground():
        return

    await _notifier.send(
        title=title,
        message=message,
        on_clicked=activate_iterm2,
    )
