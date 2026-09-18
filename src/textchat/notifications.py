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


_ITERM2_VISIBLE_WINDOW_SCRIPT = """
ObjC.import("CoreGraphics");
const windows = $.CGWindowListCopyWindowInfo(
    $.kCGWindowListOptionOnScreenOnly,
    $.kCGNullWindowID
);
let hasVisibleWindow = false;
for (let index = 0; index < windows.count; index++) {
    const window = windows.objectAtIndex(index);
    const owner = ObjC.unwrap(window.objectForKey("kCGWindowOwnerName"));
    if (owner === "iTerm2" || owner === "iTerm") {
        hasVisibleWindow = true;
        break;
    }
}
hasVisibleWindow;
"""


def iterm2_has_visible_window() -> bool:
    """Return whether iTerm2 owns an on-screen window.

    A minimized iTerm2 window can leave iTerm2 as the frontmost application.
    CoreGraphics omits minimized windows from its on-screen window list, which
    lets us distinguish that state without needing Accessibility permission.
    """
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _ITERM2_VISIBLE_WINDOW_SCRIPT],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        # Preserve the previous foreground behavior if macOS cannot answer.
        return True

    if result.returncode != 0:
        return True
    return result.stdout.strip().lower() == "true"


def iterm2_is_foreground() -> bool:
    """Return True when iTerm2 is active and has a visible window."""
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

    is_frontmost = (
        frontmost_app is not None
        and str(frontmost_app.bundleIdentifier) == "com.googlecode.iterm2"
    )
    return is_frontmost and iterm2_has_visible_window()


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


async def request_desktop_notification_permission() -> bool:
    """Ask macOS for notification permission before the first IRC alert."""
    if _notifier is None:
        return False
    return await _notifier.request_authorisation()
