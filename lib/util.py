import sublime
import sublime_plugin
import os
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import pathname2url
from urllib.request import url2pathname
from collections import OrderedDict
import json

class Util(object):
    sublime_version = int(float(sublime.version()))
    settings = None
    def load_settings(self):
        return sublime.load_settings('dxmate.sublime-settings')

    def get_setting(self, setting):
        if self.settings is None:
            self.settings = self.load_settings()
        if not self.settings is None:
            return self.settings.get(setting)
        return ''

    def plugin_name(self):
        return 'DXMate'


    def dxProjectFolder(self):
        for window in sublime.windows():
            open_folders = window.folders()
            for folder in open_folders:
                for root, dirs, files in os.walk(folder, topdown=False):
                    for name in files:
                        if name == 'sfdx-project.json':
                            return folder
        return ''

    def file_is_test(self,view):
        contents = view.substr(sublime.Region(0, view.size()))
        debug(contents)
        return '@istest' in contents.lower() or 'testmethod' in contents.lower()

    def run_events(self):
        if self.dxProjectFolder() != '':
            return True
        return False

    def active_file(self):
        return sublime.active_window().active_view().file_name()


    def active_file_extension(self):
        current_file = self.active_file()
        file_name, file_extension = os.path.splitext(current_file)
        return file_extension


    def file_extension(self, view):
        if view and view.file_name():
            file_name, file_extension = os.path.splitext(view.file_name())
            return file_extension


    def is_apex_file(self, view):
        ext = self.file_extension(view)
        if ext and (ext == '.cls' or ext == '.trigger'):
            return True
        return False


    def get_plugin_folder(self):
        packages_path = os.path.join(sublime.packages_path(), self.plugin_name())
        return packages_path


    def get_syntax_folder(self):
        plugin_folder = self.get_plugin_folder()
        syntax_folder = os.path.join(plugin_folder, "sublime", "lang")
        return syntax_folder


    def filename_to_uri(self, path: str) -> str:
        return urljoin('file:', pathname2url(path))


    def uri_to_filename(self, uri: str) -> str:
        return url2pathname(urlparse(uri).path)


    def get_document_position(self, view, point):
        if point:
            (row, col) = view.rowcol(point)
        else:
            view.sel()
        uri = self.filename_to_uri(view.file_name())
        position = OrderedDict(line=row, character=col)
        dp = OrderedDict()  # type: Dict[str, Any]
        dp["textDocument"] = {"uri": uri}
        dp["position"] = position
        return dp


    def debug(self, *args):
        """Print args to the console if the "debug" setting is True."""
        if self.get_setting('debug'):
            print(self.plugin_name(), ': ', *args)


    def format_request(self,payload: 'Dict[str, Any]'):
        """Converts the request into json and adds the Content-Length header"""
        content = json.dumps(payload, sort_keys=False)
        content_length = len(content)
        result = "Content-Length: {}\r\n\r\n{}".format(content_length, content)
        return result


util = Util()

