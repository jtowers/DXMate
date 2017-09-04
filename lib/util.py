import sublime
import sublime_plugin
import os
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import pathname2url
from urllib.request import url2pathname
from collections import OrderedDict
from .languageServer import *
from .event_hub import EventHub
import json
import re
settings = None

global sublime_version
sublime_version = int(float(sublime.version()))

def load_settings():
    return sublime.load_settings('dxmate.sublime-settings')

def get_setting(setting):
    global settings
    if settings is None:
        settings = load_settings()
    if not settings is None:
        return settings.get(setting)
    return ''

def plugin_name():
    return 'dxmate'


def dxProjectFolder():
    for window in sublime.windows():
        open_folders = window.folders()
        for folder in open_folders:
            for root, dirs, files in os.walk(folder, topdown=False):
                for name in files:
                    if name == 'sfdx-project.json':
                        return folder
    return ''

def file_is_test(view):
    contents = view.substr(sublime.Region(0, view.size()))
    debug(contents)
    return '@istest' in contents.lower() or 'testmethod' in contents.lower()

def run_events():
    if dxProjectFolder() != '':
        return True
    return False

def active_file():
    return sublime.active_window().active_view().file_name()


def active_file_extension():
    current_file = active_file()
    file_name, file_extension = os.path.splitext(current_file)
    return file_extension


def file_extension(view):
    if view and view.file_name():
        file_name, file_extension = os.path.splitext(view.file_name())
        return file_extension


def is_apex_file(view):
    ext = file_extension(view)
    if ext and (ext == '.cls' or ext == '.trigger'):
        return True
    return False


def get_plugin_folder():
    packages_path = os.path.join(sublime.packages_path(), plugin_name())
    debug(packages_path)
    return packages_path


def get_syntax_folder():
    plugin_folder = get_plugin_folder()
    syntax_folder = os.path.join(plugin_folder, "sublime", "lang")
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
    return dp


def debug(*args):
    """Print args to the console if the "debug" setting is True."""
    if get_setting('debug'):
        print(plugin_name(), ': ', *args)



def handle_close(window, *args):
    client = get_client()
    if dxProjectFolder() == '' and client:
        client.kill()

def handle_exit(window, *args):
    client = get_client()
    if client:
        client.kill()

EventHub.subscribe('exit', handle_exit)
EventHub.subscribe('close_window', handle_close)

def format_request(payload: 'Dict[str, Any]'):
    """Converts the request into json and adds the Content-Length header"""
    content = json.dumps(payload, sort_keys=False)
    content_length = len(content)
    result = "Content-Length: {}\r\n\r\n{}".format(content_length, content)
    return result

def filename_to_uri(path: str) -> str:
    return urljoin('file:', pathname2url(path))


def uri_to_filename(uri: str) -> str:
    return url2pathname(urlparse(uri).path)

EventHub.subscribe('on_pre_close', handle_close)


