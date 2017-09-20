import sublime
import sublime_plugin
import os
import subprocess
import threading
import sys
import json
import mdpopups
import time
from collections import OrderedDict
from .lib.printer import PanelPrinter
from .lib.threads import ThreadProgress
from .lib.threads import PanelThreadProgress
from .lib.languageServer import *
from .lib.event_hub import EventHub
from .lib.util import util
from .lib.diagnostic import *
import ntpath


class SymbolKind(object):
    File = 1
    Module = 2
    Namespace = 3
    Package = 4
    Class = 5
    Method = 6
    Property = 7
    Field = 8
    Constructor = 9
    Enum = 10
    Interface = 11
    Function = 12
    Variable = 13
    Constant = 14
    String = 15
    Number = 16
    Boolean = 17
    Array = 18


symbol_kind_names = {
    SymbolKind.File: "file",
    SymbolKind.Module: "module",
    SymbolKind.Namespace: "namespace",
    SymbolKind.Package: "package",
    SymbolKind.Class: "class",
    SymbolKind.Method: "method",
    SymbolKind.Function: "function",
    SymbolKind.Field: "field",
    SymbolKind.Variable: "variable",
    SymbolKind.Constant: "constant"
}


def format_symbol_kind(kind):
    return symbol_kind_names.get(kind, str(kind))


def format_symbol(item):
    """
    items may be a list of strings, or a list of string lists.
    In the latter case, each entry in the quick panel will show multiple rows
    """
    # file_path = uri_to_filename(location.get("uri"))
    # kind = format_symbol_kind(item.get("kind"))
    # return [item.get("name"), kind]
    return [item.get("name")]


class DxmateOutputText(sublime_plugin.TextCommand):

    def run(self, edit, text, erase=False, *args, **kwargs):
        size = self.view.size()
        self.view.set_read_only(False)
        if erase == True:
            size = sublime.Region(0, self.view.size())
            self.view.replace(edit, size, text)
        else:
            self.view.insert(edit, size, text)
        self.view.set_read_only(True)
        self.view.show(size)

    def is_visible(self):
        return False

    def is_enabled(self):
        return True

    def description(self):
        return


class WriteOperationStatus(sublime_plugin.TextCommand):

    def run(self, edit, text, *args, **kwargs):
        kw_region = kwargs.get('region', [0, 0])
        status_region = sublime.Region(kw_region[0], kw_region[1])
        size = self.view.size()
        self.view.set_read_only(False)
        self.view.replace(edit, status_region, text)
        self.view.set_read_only(True)
        # self.view.show(size)

    def is_visible(self):
        return False

    def is_enabled(self):
        return True

    def description(self):
        return

# not ready for code completion yet
lsClient = None
printer = None



def plugin_loaded():
    global lsClient
    global printer
    if util.dxProjectFolder() != '':
        lsClient = start_client()
        if lsClient is None:
            util.debug('Unable start langauge server')
        EventHub.subscribe('on_load_async', set_syntax)
    active_window_id = sublime.active_window().id()
    printer = PanelPrinter.get(active_window_id)
    printer.write("sfdx plugin loaded", erase=True)


def plugin_unloaded():
    if lsClient:
        lsClient.kill()


def set_syntax(view):
    if util.is_apex_file(view):
        util.debug('setting syntax for file')
        if "linux" in sys.platform or "darwin" in sys.platform:
            view.set_syntax_file(os.path.join("Packages",util.plugin_name(),"sublime","lang","Apex.sublime-syntax"))
        else:
            view.set_syntax_file(os.path.join("Packages/"+util.plugin_name()+"/sublime/lang/Apex.sublime-syntax"))

class ExitHandler(sublime_plugin.EventListener):

    def on_window_commad(self, window, command_name, args):
        if command_name == 'exit':
            plugin_unloaded()


class EventHandlers(sublime_plugin.EventListener):

    def __init__(self):
        self.completions = []  # type: List[Tuple[str, str]]
        self.refreshing = False

    def on_pre_close(self, view):
        EventHub.publish('on_pre_close', view)


    def on_close(self, view):
        EventHub.publish('on_close', view)
    def on_load_async(self, view):
        EventHub.publish('on_load_async', view)
    def on_activated_async(self, view):
        EventHub.publish('on_activated_async', view)
    def on_post_save_async(self, view):
        EventHub.publish('on_post_save_async', view)
    def on_close(self, view):
        EventHub.publish('on_close', view)
    def on_hover(self, view, point, hover_zone):
        EventHub.publish('on_hover', view, point, hover_zone)
    def on_window_command(self, window, command_name, *args):
        if command_name == 'exit':
            EventHub.publish('exit', window, *args)
        elif command_name == 'close_window':
            EventHub.publish('close_window', window, *args)
        else:
            EventHub.publish('on_window_command', window, command_name, *args)
    def on_text_command(self, window, command_name, *args):
        if command_name == 'exit':
            EventHub.publish('exit', window, *args)
        elif command_name == 'close_window':
            EventHub.publish('close_window', window, *args)
        else:
            EventHub.publish('on_window_command', window, command_name, *args)
    def on_modified_async(self, view):
        active_file_extension = util.file_extension(view)
        if active_file_extension != '.cls' and active_file_extension != '.trigger':
            return None
        EventHub.publish("on_modified_async", view)

    def on_query_completions(self, view, prefix, locations):
        active_file_extension = util.file_extension(view)
        if active_file_extension != '.cls' and active_file_extension != '.trigger':
            return None

        if not self.refreshing:
            client = lsClient

            if not client:
                return

            completionProvider = client.get_capability('completionProvider')
            if not completionProvider:
                return

            autocomplete_triggers = completionProvider.get('triggerCharacters')
            if locations[0] > 0:
                self.completions = []
            purge_did_change(view.buffer_id())
            client.send_request(
                Request.complete(
                    util.get_document_position(view, locations[0])),
                self.handle_response)
        self.refreshing = False
        return self.completions, (sublime.INHIBIT_WORD_COMPLETIONS
                                  | sublime.INHIBIT_EXPLICIT_COMPLETIONS)

    def format_completion(self, item) -> 'Tuple[str, str]':
        label = item.get("label")
        # kind = item.get("kind")
        detail = item.get("kind")
        detail = format_symbol_kind(detail)
        #detail = format_symbol(detail)
        insertText = label
        if item.get("insertTextFormat") == 2:
            insertText = item.get("insertText")
        if insertText[0] == '$':  # sublime needs leading '$' escaped.
            insertText = '\$' + insertText[1:]
        return ("{}\t{}".format(label, detail), insertText)

    def handle_response(self, response):
        self.completions = []
        items = response["items"] if isinstance(response,
                                                dict) else response
        for item in items:
            self.completions.append(self.format_completion(item))
        sublime.active_window().active_view().run_command('hide_auto_complete')
        self.run_auto_complete()

    def run_auto_complete(self):
        self.refreshing = True
        sublime.active_window().active_view().run_command(
            "auto_complete", {
                'disable_auto_insert': True,
                'api_completions_only': False,
                'next_completion_if_showing': False,
                'auto_complete_commit_on_tab': True,
            })


class DxmateRunFileTestsCommand(sublime_plugin.WindowCommand):

    def run(self):
        self.dx_folder = util.dxProjectFolder()
        self.active_file = util.active_file()
        self.active_file = ntpath.split(self.active_file)[
            1].replace('.cls', '')
        self.class_name = 'ApexClassName'
        t = threading.Thread(target=self.run_command)
        t.start()
        printer.show()
        printer.write('\nRunning Tests')
        printer.write('\nResult: ')
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Running tests', 'Tests run')
        PanelThreadProgress(t, 'Running Tests')

    def is_enabled(self):
        self.dx_folder = util.dxProjectFolder()
        if(self.dx_folder == ''):
            return False
        self.active_file = util.active_file()
        if not self.active_file.endswith('.cls'):
            return False
        if not util.file_is_test(self.window.active_view()):
            return False
        return True

    def run_command(self):
        args = ['sfdx', 'force:apex:test:run', '-r', 'human',
                '-l', 'RunSpecifiedTests', '-n', self.class_name]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\n' + str(out, 'utf-8'))
        else:
            printErr = err
            if err is None or err == '':
                printErr = out
            printer.write('\n' + str(printErr, 'utf-8'))


class DxmateRunOrgTestsCommand(sublime_plugin.TextCommand):

    def run(self, edit):

        self.dx_folder = util.dxProjectFolder()
        sublime.active_window().show_input_panel(
            'Org (leave blank for default)', '', self.run_tests, None, None)

    def run_tests(self, input):
        self.test_org = input
        printer.show()
        printer.write('\nRunning Org Tests')
        printer.write('\nResult: ')
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Running Org Tests', 'Org tests run')
        PanelThreadProgress(t, 'Running Org Tests')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True
        

    def run_command(self):
        args = ['sfdx', 'force:apex:test:run', '-r', 'human']
        if not self.test_org is None and len(self.test_org) > 0:
            args.push('-u')
            args.push(self.input)
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\n' + str(out, 'utf-8'))
        else:
            printErr = err
            if err is None or err == '':
                printErr = out
            printer.write('\n' + str(printErr, 'utf-8'))


class DxmatePushSourceCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.dx_folder = util.dxProjectFolder()
        printer.show()
        printer.write('\nPushing Source')
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Pushing Source', 'Source Pushed')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Source Pushed')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        args = ['sfdx', 'force:source:push']
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\n' + str(out, 'utf-8'))
        else:
            printErr = err
            if not err is None and not err == '':
                printErr = out
            else:
                printer.write('\nError pushing source')
            printer.write('\n' + str(printErr, 'utf-8'))


class DxmatePullSourceCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.dx_folder = util.dxProjectFolder()
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Pulling Source', 'Source Pulled')
        printer.write('\nPulling Source')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Source Pulled')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        args = ['sfdx', 'force:source:pull']
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\n' + str(out, 'utf-8'))
        else:
            printErr = err
            if not err is None and not err == '':
                printErr = out
            else:
                printer.write('\nError pulling source')
            printer.write('\n' + str(printErr, 'utf-8'))


class DxmateOpenScratchOrgCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.dx_folder = util.dxProjectFolder()
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Opening Org', 'Org Opened')
        printer.write('\nOpening Org')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Org Opened')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        args = ['sfdx', 'force:org:open']
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nScratch org opened')
        else:
            printer.write('\nError opening')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateCreateScratchOrgCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.dx_folder = util.dxProjectFolder()
        self.def_file = os.path.join(
            self.dx_folder, 'config', 'project-scratch-def.json')
        sublime.active_window().show_input_panel(
            'Class Name', self.def_file, self.create_org, None, None)

    def create_org(self, input):
        printer.show()
        self.def_file = input
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Scratch Org', 'Scratch Org Created')
        printer.write('\nCreatin Scratch Org')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Scratch Org Created')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        args = ['sfdx', 'force:org:create', '-f',
                self.def_file, '-a', 'ScratchOrg', '-s']
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nScratch org created')
        else:
            printer.write('\nError creating scratch org')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateAuthDevHubCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Opening Auth Page', 'Auth Page Opened')
        printer.write('\nOpening Auth Page')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Auth Page Opened')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:auth:web:login', '-d', '-s', '-a', 'DevHub']
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nDevHub authorized')
        else:
            printer.write('\nError authorizing Dev Hub:')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateRunSoqlCommand(sublime_plugin.WindowCommand):

    def run(self):
        sublime.active_window().show_input_panel(
            'Query', '', self.run_query, None, None)

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_query(self, input):
        self.query = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Running query', 'Query run')
        printer.write('\nRunning query')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Query run')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:data:soql:query',
                '-q', self.query]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nOpening results file')
            content = str(out,'UTF-8')
            #try:
            #    parsed = json.loads(content)
            #    content = json.dumps(parsed,  sort_keys=True,indent=1, separators=(',', ':'))
            #    util.debug(content)
            #except Exception as e:
            #    util.debug('could not format query results\n', e)
            file = sublime.active_window().new_file()
            file.set_scratch(True)
            file.set_name('SOQL')
            syntax_path = None
            if "linux" in sys.platform or "darwin" in sys.platform:
                syntax_path = os.path.join("Packages",plugin_name(),"sublime","lang","JSON.tmLanguage")
            else:
                syntax_path = os.path.join("Packages/"+plugin_name()+"/sublime/lang/JSON.tmLanguage")
            #file.set_syntax_file(syntax_path)
            file.run_command("insert", {"characters":content})
        else:
            printer.write('\nError running query:')
            printer.write('\n' + str(err, 'utf-8'))



class DxmateCreateVisualforceComponentCommand(sublime_plugin.WindowCommand):
    def run(self, paths=[]):
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            printer.show()
            printer.write('\nPlease select a single folder to save the component')
            return

        self.page_name = 'ComponentName'
        self.page_label = 'Component Label'
        self.class_dir = paths[0]
        sublime.active_window().show_input_panel(
            'Component API Name', self.page_name, self.get_label, None, None)


    def get_label(self, input):
        self.page_name = input
        sublime.active_window().show_input_panel(
            'Component Label', self.page_label, self.create_page, None, None)

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            return False
        return True

    def create_page(self, input):
        self.page_label = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Visualforce Component', 'Visualforce Component Created')
        printer.write('\nCreating Visualforce Component')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Visualforce Component Created')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:visualforce:component:create',
                '-n', self.page_name,'-l', self.page_label, '-d', self.class_dir]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nVisaulforce Component created')
            file = os.path.join(self.class_dir, self.page_name + '.component')
            sublime.active_window().open_file(file)
        else:
            printer.write('\nError creating Visualforce Component:')
            printer.write('\n' + str(err, 'utf-8'))

class DxmateCreateVisualforcePageCommand(sublime_plugin.WindowCommand):
    def run(self, paths=[]):
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            printer.show()
            printer.write('\nPlease select a single folder to save the page')
            return

        self.page_name = 'PageName'
        self.page_label = 'Page Label'
        self.class_dir = paths[0]
        sublime.active_window().show_input_panel(
            'Page API Name', self.page_name, self.get_label, None, None)


    def get_label(self, input):
        self.page_name = input
        sublime.active_window().show_input_panel(
            'Page Label', self.page_label, self.create_page, None, None)

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            return False
        return True

    def create_page(self, input):
        self.page_label = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Visualforce Page', 'Visualforce Page Created')
        printer.write('\nCreating Visualforce Page')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Visualforce Page Created')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:visualforce:page:create',
                '-n', self.page_name,'-l', self.page_label, '-d', self.class_dir]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nVisaulforce page created')
            file = os.path.join(self.class_dir, self.page_name + '.page')
            sublime.active_window().open_file(file)
        else:
            printer.write('\nError creating Visualforce page:')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateCreateLightningComponentCommand(sublime_plugin.WindowCommand):
    def run(self, paths=[]):
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            printer.show()
            printer.write('\nPlease select a single folder save the component')
            return

        self.cmp_name = 'ComponentName'
        self.class_dir = paths[0]
        sublime.active_window().show_input_panel(
            'App Name', self.cmp_name, self.create_cmp, None, None)

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            return False
        return True

    def create_cmp(self, input):
        self.cmp_name = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Lightning Component', 'Lightning Component Created')
        printer.write('\nCreating Lightning Component')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Lightning Component Created')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:lightning:component:create',
                '-n', self.cmp_name, '-d', self.class_dir]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nLightning Component created')
            file = os.path.join(self.class_dir, self.cmp_name, self.cmp_name + '.cmp')
            sublime.active_window().open_file(file)
        else:
            printer.write('\nError creating Lightning Component:')
            printer.write('\n' + str(err, 'utf-8'))

class DxmateCreateLightningComponentCommand(sublime_plugin.WindowCommand):
    def run(self, paths=[]):
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            printer.show()
            printer.write('\nPlease select a single folder save the component')
            return

        self.cmp_name = 'ComponentName'
        self.class_dir = paths[0]
        sublime.active_window().show_input_panel(
            'App Name', self.cmp_name, self.create_cmp, None, None)

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            return False
        return True

    def create_cmp(self, input):
        self.cmp_name = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Lightning Component', 'Lightning Component Created')
        printer.write('\nCreating Lightning Component')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Lightning Component Created')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:lightning:component:create',
                '-n', self.cmp_name, '-d', self.class_dir]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nLightning Component created')
            file = os.path.join(self.class_dir, self.cmp_name, self.cmp_name + '.cmp')
            sublime.active_window().open_file(file)
        else:
            printer.write('\nError creating Lightning Component:')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateCreateLightningAppCommand(sublime_plugin.WindowCommand):
    def run(self, paths=[]):
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            printer.show()
            printer.write('\nPlease select a single folder save the class')
            return

        self.app_name = 'AppName'
        self.class_dir = paths[0]
        sublime.active_window().show_input_panel(
            'App Name', self.app_name, self.create_app, None, None)

    def is_enabled(self, paths=[]):
        
        if util.isDXProject() == False:
            return False
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            return False
        return True

    def create_app(self, input):
        self.app_name = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Lightning App', 'Lightning App Created')
        printer.write('\nCreating Lightning App')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Lightning App Created')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:lightning:app:create',
                '-n', self.app_name, '-d', self.class_dir]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nLightning App created')
            file = os.path.join(self.class_dir, self.app_name, self.app_name + '.app')
            sublime.active_window().open_file(file)
        else:
            printer.write('\nError creating Lightning App:')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateCreateApexClassCommand(sublime_plugin.WindowCommand):
    def run(self, paths=[]):
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            printer.show()
            printer.write('\nPlease select a single folder save the class')
            return

        self.class_name = 'ApexClassName'
        self.class_dir = paths[0]
        sublime.active_window().show_input_panel(
            'Class Name', self.class_name, self.create_class, None, None)

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        if len(paths) != 1 or (len(paths) > 0 and os.path.isfile(paths[0])):
            return False
        return True

    def create_class(self, input):
        self.class_name = input
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Apex Class', 'Apex Class Created')
        printer.write('\nCreating Apex Class')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Apex Class Created')

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:apex:class:create',
                '-n', self.class_name, '-d', self.class_dir]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nApex class created')
            file = os.path.join(self.class_dir, self.class_name + '.cls')
            sublime.active_window().open_file(file)
        else:
            printer.write('\nError creating Apex Class:')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateUpgradeProjectCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        printer.show()
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Upgrading Project', 'Project Upgraded')
        printer.write('\nUpgrading Project')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Project Upgraded')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        dx_folder = util.dxProjectFolder()
        args = ['sfdx', 'force:project:upgrade', '-f']
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nProject upgraded')
        else:
            printer.write('\nError upgrading project:')
            printer.write('\n' + str(err, 'utf-8'))


class DxmateCreateProjectCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.edit = edit
        self.project_name = ''
        self.template = 'Defaultsfdx-project.json'
        self.project_path = ''
        self.namespace = None
        sublime.active_window().show_input_panel(
            'Project Name', self.project_name, self.create_project_name, None, None)

    def create_project_name(self, input):
        self.project_name = input
        sublime.active_window().show_input_panel('Project Template', self.template,
                                                 self.create_project_template, None, None)

    def create_project_template(self, input):
        self.project_template = input
        sublime.active_window().show_input_panel('Project Path', self.project_path,
                                                 self.create_project_namespace, None, None)

    def create_project_namespace(self, input):
        self.project_path = input
        sublime.active_window().show_input_panel(
            'Project Namespace', '', self.create_project, None, None)

    def create_project(self, input):
        printer.show()
        self.namespace = input
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Creating Project', 'Project Created')
        printer.write('\nCreating Project')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Project Created')

    def run_command(self):
        args = ['sfdx', 'force:project:create', '-n', self.project_name,
                '-t', self.template, '-d', self.project_path]
        if self.namespace is not None and self.namespace != '':
            args.push('-s')
            args.push(self.namespace)
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, startupinfo=startupinfo)

        p.wait()

        t = p.communicate()[0]
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nProject created')
        else:
            printer.write('\nError creating project:')
            printer.write('\n' + t)


class DxmateExecuteAnonymousApexCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        self.selection = ''
        for region in self.view.sel():
            if not region.empty():
                self.selection += self.view.substr(region)
        if self.selection == '':
            self.selection = self.view.substr(sublime.Region(0, self.view.size()))
        self.file_path = os.path.join(util.dxProjectFolder(), '.sfdx', 'tmpFile.cls')
        with open(self.file_path, 'w+') as file_obj:
            file_obj.write(self.selection)
        printer.show()
        self.namespace = input
        t = threading.Thread(target=self.run_command)
        t.start()
        t.printer = printer
        t.process_id = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
        ThreadProgress(t, 'Running anonymous apex', 'Anonymous apex run')
        printer.write('\nRunning anonymous apex')
        printer.write('\nResult: ')
        PanelThreadProgress(t, 'Anonymous apex run')

    def is_enabled(self, paths=[]):
        #dx_folder = util.dxProjectFolder()
        if util.isDXProject() == False:
            return False
        return True

    def run_command(self):
        args = ['sfdx', 'force:apex:execute', '-f', self.file_path]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             startupinfo=startupinfo, cwd=self.dx_folder)

        p.wait()

        out, err = p.communicate()
        r = p.returncode
        if p.returncode == 0:
            printer.write('\nFinished running apex')
            printer.write('\n' + str(out, 'utf-8'))
        else:
            printErr = err
            if err is None or err == '':
                printErr = out
            printer.write('\nError running apex')
            printer.write('\n' + str(printErr, 'utf-8'))