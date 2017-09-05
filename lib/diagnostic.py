#MIT License
#
#Copyright (c) 2017 Tom van Ommeren
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

import os
from collections import OrderedDict
import sublime
from .util import util
from .event_hub import EventHub
import mdpopups
show_diagnostics_phantoms = True
UNDERLINE_FLAGS = (sublime.DRAW_NO_FILL
                   | sublime.DRAW_NO_OUTLINE
                   | sublime.DRAW_EMPTY_AS_OVERWRITE)
window_file_diagnostics = dict(
)
auto_show_diagnostics_panel = False
class Point(object):
    def __init__(self, row: int, col: int) -> None:
        self.row = int(row)
        self.col = int(col)

    def __repr__(self):
        return "{}:{}".format(self.row, self.col)

    @classmethod
    def from_lsp(cls, point: dict) -> 'Point':
        return Point(point['line'], point['character'])

    def to_lsp(self) -> dict:
        r = OrderedDict()  # type: OrderedDict[str, Any]
        r['line'] = self.row
        r['character'] = self.col
        return r

    @classmethod
    def from_text_point(self, view: sublime.View, point: int) -> 'Point':
        return Point(*view.rowcol(point))

    def to_text_point(self, view) -> int:
        return view.text_point(self.row, self.col)


class Range(object):
    def __init__(self, start: Point, end: Point) -> None:
        self.start = start
        self.end = end

    def __repr__(self):
        return "({} {})".format(self.start, self.end)

    @classmethod
    def from_lsp(cls, range: dict) -> 'Range':
        return Range(Point.from_lsp(range['start']), Point.from_lsp(range['end']))

    def to_lsp(self) -> dict:
        r = OrderedDict()  # type: OrderedDict[str, Any]
        r['start'] = self.start.to_lsp()
        r['end'] = self.end.to_lsp()
        return r
     
    def to_region(self, view: sublime.View) -> sublime.Region:
        return sublime.Region(self.start.to_text_point(view), self.end.to_text_point(view))

class Diagnostic(object):
    def __init__(self, message, range, severity, source, lsp_diagnostic):
        self.message = message
        self.range = range
        self.severity = severity
        self.source = source
        self._lsp_diagnostic = lsp_diagnostic

    @classmethod
    def from_lsp(cls, lsp_diagnostic):
        return Diagnostic(
            # crucial keys
            lsp_diagnostic['message'],
            Range.from_lsp(lsp_diagnostic['range']),
            # optional keys
            lsp_diagnostic.get('severity', DiagnosticSeverity.Error),
            lsp_diagnostic.get('source'),
            lsp_diagnostic
        )

    def to_lsp(self):
        return self._lsp_diagnostic

class DiagnosticSeverity(object):
    Error = 1
    Warning = 2
    Information = 3
    Hint = 4


diagnostic_severity_names = {
    DiagnosticSeverity.Error: "error",
    DiagnosticSeverity.Warning: "warning",
    DiagnosticSeverity.Information: "info",
    DiagnosticSeverity.Hint: "hint"
}

diagnostic_severity_scopes = {
    DiagnosticSeverity.Error: 'markup.deleted.lsp sublimelinter.mark.error markup.error.lsp',
    DiagnosticSeverity.Warning: 'markup.changed.lsp sublimelinter.mark.warning markup.warning.lsp',
    DiagnosticSeverity.Information: 'markup.inserted.lsp sublimelinter.gutter-mark markup.info.lsp',
    DiagnosticSeverity.Hint: 'markup.inserted.lsp sublimelinter.gutter-mark markup.info.suggestion.lsp'
}

OUTPUT_PANEL_SETTINGS = {
    "auto_indent": False,
    "draw_indent_guides": False,
    "draw_white_space": "None",
    "gutter": False,
    'is_widget': True,
    "line_numbers": False,
    "margin": 3,
    "match_brackets": False,
    "scroll_past_end": False,
    "tab_size": 4,
    "translate_tabs_to_spaces": False,
    "word_wrap": False
}

def create_output_panel(window: sublime.Window, name: str) -> sublime.View:
    panel = window.create_output_panel(name)
    settings = panel.settings()
    for key, value in OUTPUT_PANEL_SETTINGS.items():
        settings.set(key, value)
    return panel

def format_severity(severity: int) -> str:
    return diagnostic_severity_names.get(severity, "???")


def format_diagnostic(diagnostic: Diagnostic) -> str:
    location = "{:>8}:{:<4}".format(
        diagnostic.range.start.row + 1, diagnostic.range.start.col + 1)
    message = diagnostic.message.replace("\n", " ").replace("\r", "")
    return " {}\t{:<12}\t{:<10}\t{}".format(
        location, diagnostic.source, format_severity(diagnostic.severity), message)


def get_line_diagnostics(view, point):
    row, _ = view.rowcol(point)
    diagnostics = get_diagnostics_for_view(view)
    return tuple(
        diagnostic for diagnostic in diagnostics
        if diagnostic.range.start.row <= row <= diagnostic.range.end.row
    )


def get_diagnostics_for_view(view: sublime.View) -> 'List[Diagnostic]':
    window = view.window()
    file_path = view.file_name()
    origin = 'dxmate'
    if window.id() in window_file_diagnostics:
        file_diagnostics = window_file_diagnostics[window.id()]
        if file_path in file_diagnostics:
            if origin in file_diagnostics[file_path]:
                return file_diagnostics[file_path][origin]
    return []


def update_file_diagnostics(window: sublime.Window, file_path: str, source: str,
                            diagnostics: 'List[Diagnostic]'):
    if diagnostics:
        window_file_diagnostics.setdefault(window.id(), dict()).setdefault(
            file_path, dict())[source] = diagnostics
    else:
        if window.id() in window_file_diagnostics:
            file_diagnostics = window_file_diagnostics[window.id()]
            if file_path in file_diagnostics:
                if source in file_diagnostics[file_path]:
                    del file_diagnostics[file_path][source]
                if not file_diagnostics[file_path]:
                    del file_diagnostics[file_path]

def handle_diagnostics(update: 'Any'):
    util.debug('handling diagnostics')
    file_path = util.uri_to_filename(update.get('uri'))
    window = sublime.active_window()

    if not util.is_apex_file(window.active_view()):
        util.debug("Skipping diagnostics for file", file_path,
              " it is not in the workspace")
        return

    diagnostics = list(
        Diagnostic.from_lsp(item) for item in update.get('diagnostics', []))

    view = window.find_open_file(file_path)

    # diagnostics = update.get('diagnostics')

    update_diagnostics_in_view(view, diagnostics)

    # update panel if available

    origin = 'dxmate'  # TODO: use actual client name to be able to update diagnostics per client

    update_file_diagnostics(window, file_path, origin, diagnostics)
    update_diagnostics_panel(window)

phantom_sets_by_buffer = {}  # type: Dict[int, sublime.PhantomSet]

def create_diagnostics_panel(window):
    panel = create_output_panel(window, "diagnostics")
    panel.settings().set("result_file_regex", r"^\s*\S\s+(\S.*):$")
    panel.settings().set("result_line_regex", r"^\s+([0-9]+):?([0-9]+).*$")
    panel.assign_syntax("Packages/" + util.plugin_name() +
                        "/sublime/lang/Diagnostics.sublime-syntax")
    return panel

def ensure_diagnostics_panel(window):
    return window.find_output_panel("diagnostics") or create_diagnostics_panel(window)

def update_diagnostics_panel(window):
    assert window, "missing window!"
    base_dir = util.dxProjectFolder()

    panel = ensure_diagnostics_panel(window)
    assert panel, "must have a panel now!"

    if window.id() in window_file_diagnostics:
        active_panel = window.active_panel()
        is_active_panel = (active_panel == "output.diagnostics")
        panel.settings().set("result_base_dir", base_dir)
        panel.set_read_only(False)
        panel.run_command("lsp_clear_panel")
        file_diagnostics = window_file_diagnostics[window.id()]
        if file_diagnostics:
            for file_path, source_diagnostics in file_diagnostics.items():
                relative_file_path = os.path.relpath(file_path, base_dir) if base_dir else file_path
                if source_diagnostics:
                    append_diagnostics(panel, relative_file_path, source_diagnostics)
            if auto_show_diagnostics_panel and not active_panel:
                window.run_command("show_panel",
                                   {"panel": "output.diagnostics"})
        else:
            if auto_show_diagnostics_panel and is_active_panel:
                window.run_command("hide_panel",
                                   {"panel": "output.diagnostics"})
        panel.set_read_only(True)


def append_diagnostics(panel, file_path, origin_diagnostics):
    panel.run_command('append',
                      {'characters':  " ◌ {}:\n".format(file_path),
                       'force': True})
    for origin, diagnostics in origin_diagnostics.items():
        for diagnostic in diagnostics:
            item = format_diagnostic(diagnostic)
            panel.run_command('append', {
                'characters': item + "\n",
                'force': True,
                'scroll_to_end': True
            })


def update_diagnostics_phantoms(view: sublime.View, diagnostics: 'List[Diagnostic]'):
    global phantom_sets_by_buffer

    buffer_id = view.buffer_id()
    if not show_diagnostics_phantoms or view.is_dirty():
        phantoms = None
    else:
        phantoms = list(
            create_phantom(view, diagnostic) for diagnostic in diagnostics)
    if phantoms:
        phantom_set = phantom_sets_by_buffer.get(buffer_id)
        if not phantom_set:
            phantom_set = sublime.PhantomSet(view, "lsp_diagnostics")
            phantom_sets_by_buffer[buffer_id] = phantom_set
        phantom_set.update(phantoms)
    else:
        phantom_sets_by_buffer.pop(buffer_id, None)


def update_diagnostics_regions(view: sublime.View, diagnostics: 'List[Diagnostic]', severity: int):
    region_name = "lsp_" + format_severity(severity)
    if show_diagnostics_phantoms and not view.is_dirty():
        regions = None
    else:
        regions = list(diagnostic.range.to_region(view) for diagnostic in diagnostics
                       if diagnostic.severity == severity)
    if regions:
        scope_name = diagnostic_severity_scopes[severity]
        view.add_regions(region_name, regions, scope_name, "dot",
                         sublime.DRAW_SQUIGGLY_UNDERLINE | UNDERLINE_FLAGS)
    else:
        view.erase_regions(region_name)


def update_diagnostics_in_view(view: sublime.View, diagnostics: 'List[Diagnostic]'):
    if view and view.is_valid():
        update_diagnostics_phantoms(view, diagnostics)
        for severity in range(DiagnosticSeverity.Error, DiagnosticSeverity.Information):
            update_diagnostics_regions(view, diagnostics, severity)


def remove_diagnostics(view: sublime.View):
    """Removes diagnostics for a file if no views exist for it
    """
    if util.is_apex_file(view):
        window = sublime.active_window()

        file_path = view.file_name()
        if not window.find_open_file(view.file_name()):
            update_file_diagnostics(window, file_path, 'dxmate', [])
            update_diagnostics_panel(window)
        else:
            util.debug('file still open?')

def show_diagnostics_hover(view, point, diagnostics):
    #util.debug('got diagnostics: ', diagnostics)
    formatted = list("{}: {}".format(format_severity(diagnostic.severity), diagnostic.message) for diagnostic in diagnostics)
    #formatted.append("[{}]({})".format('Code Actions', 'code-actions'))
    mdpopups.show_popup(
        view,
        "\n".join(formatted),
        css=".mdpopups .lsp_hover { margin: 4px; }",
        md=True,
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        location=point,
        wrapper_class="lsp_hover",
        max_width=800,
        #on_navigate=lambda href: self.on_diagnostics_navigate(self, href, point, diagnostics)
        )

def handle_hover(view, point, hover_zone):
    if util.is_apex_file(view):
        if hover_zone != sublime.HOVER_TEXT or view.is_popup_visible():
            return
        util.debug('handling hover')
        line_diagnostics = get_line_diagnostics(view, point)
        if line_diagnostics:
            show_diagnostics_hover(view, point, line_diagnostics)
EventHub.subscribe('on_hover', handle_hover)
EventHub.subscribe('document.diagnostics', handle_diagnostics)
EventHub.subscribe('on_close', remove_diagnostics)