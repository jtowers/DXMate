import sublime
import sublime_plugin
import os
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import pathname2url
from urllib.request import url2pathname
from collections import OrderedDict
debug = True


def plugin_name():
    return 'dxmate'


def dxProjectFolder():
    # find the first dx project folder in any open window
    # should probably update this to keep track of all open projects
    for window in sublime.windows():
        open_folders = window.folders()
        for folder in open_folders:
            for root, dirs, files in os.walk(folder, topdown=False):
                for name in files:
                    if name == 'sfdx-project.json':
                        return folder
    return '' 


def active_file():
    return sublime.active_window().active_view().file_name()


def active_file_extension():
    current_file = active_file()
    file_name, file_extension = os.path.splitext(current_file)
    return file_extension


def file_extension(view):
    if view is None:
        return ''
    file_name, file_extension = os.path.splitext(view.file_name())
    return file_extension


def get_plugin_folder():
    packages_path = os.path.join(sublime.packages_path(), plugin_name())
    debug(packages_path)
    return packages_path


def get_syntax_folder():
    plugin_folder = get_plugin_folder()
    syntax_folder = os.path.join(plugin_folder, "sublime", "lang")
    debug(syntax_folder)
    return syntax_folder


def filename_to_uri(path: str) -> str:
    return urljoin('file:', pathname2url(path))


def uri_to_filename(uri: str) -> str:
    return url2pathname(urlparse(uri).path)


def get_document_position(view, point):
    if point:
        (row, col) = view.rowcol(point)
    else:
        view.sel()
    uri = filename_to_uri(view.file_name())
    position = OrderedDict(line=row, character=col)
    dp = OrderedDict()  # type: Dict[str, Any]
    dp["textDocument"] = {"uri": uri}
    dp["position"] = position
    debug('position:', dp)
    return dp


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if debug:
        print(*args)


pending_buffer_changes = dict()  # type: Dict[int, Dict]


def queue_did_change(view: sublime.View):
    buffer_id = view.buffer_id()
    buffer_version = 1
    pending_buffer = None
    if buffer_id in pending_buffer_changes:
        pending_buffer = pending_buffer_changes[buffer_id]
        buffer_version = pending_buffer["version"] + 1
        pending_buffer["version"] = buffer_version
    else:
        pending_buffer_changes[buffer_id] = {
            "view": view,
            "version": buffer_version
        }

    sublime.set_timeout_async(
        lambda: purge_did_change(buffer_id, buffer_version), 500)


def purge_did_change(buffer_id: int, buffer_version=None):
    if buffer_id not in pending_buffer_changes:
        return

    pending_buffer = pending_buffer_changes.get(buffer_id)

    if pending_buffer:
        if buffer_version is None or buffer_version == pending_buffer["version"]:
            notify_did_change(pending_buffer["view"])
