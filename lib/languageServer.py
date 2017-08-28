import sublime
import sublime_plugin
import os
import subprocess
import dxmate.lib.util as util
import threading
import json
from collections import OrderedDict
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.request import pathname2url
from urllib.request import url2pathname

client = None


def format_request(payload: 'Dict[str, Any]'):
    """Converts the request into json and adds the Content-Length header"""
    content = json.dumps(payload, sort_keys=False)
    content_length = len(content)
    result = "Content-Length: {}\r\n\r\n{}".format(content_length, content)
    return result


class Request:

    def __init__(self, method, params):
        self.method = method
        self.params = params
        self.jsonrpc = "2.0"

    @classmethod
    def initialize(cls, params):
        return Request("initialize", params)

    @classmethod
    def hover(cls, params):
        return Request("textDocument/hover", params)

    @classmethod
    def complete(cls, params):
        return Request("textDocument/completion", params)

    @classmethod
    def signatureHelp(cls, params):
        return Request("textDocument/signatureHelp", params)

    @classmethod
    def references(cls, params):
        return Request("textDocument/references", params)

    @classmethod
    def definition(cls, params):
        return Request("textDocument/definition", params)

    @classmethod
    def rename(cls, params):
        return Request("textDocument/rename", params)

    @classmethod
    def codeAction(cls, params):
        return Request("textDocument/codeAction", params)

    @classmethod
    def executeCommand(cls, params):
        return Request("workspace/executeCommand", params)

    @classmethod
    def formatting(cls, params):
        return Request("textDocument/formatting", params)

    @classmethod
    def documentSymbols(cls, params):
        return Request("textDocument/documentSymbol", params)

    def __repr__(self):
        return self.method + " " + str(self.params)

    def to_payload(self, id):
        r = OrderedDict()  # type: OrderedDict[str, Any]
        r["jsonrpc"] = "2.0"
        r["id"] = id
        r["method"] = self.method
        r["params"] = self.params
        return r


class Notification:

    def __init__(self, method, params):
        self.method = method
        self.params = params
        self.jsonrpc = "2.0"

    @classmethod
    def didOpen(cls, params):
        return Notification("textDocument/didOpen", params)

    @classmethod
    def didChange(cls, params):
        return Notification("textDocument/didChange", params)

    @classmethod
    def didSave(cls, params):
        return Notification("textDocument/didSave", params)

    @classmethod
    def didClose(cls, params):
        return Notification("textDocument/didClose", params)

    @classmethod
    def exit(cls):
        return Notification("exit", None)

    def __repr__(self):
        return self.method + " " + str(self.params)

    def to_payload(self):
        r = OrderedDict()  # type: OrderedDict[str, Any]
        r["jsonrpc"] = "2.0"
        r["method"] = self.method
        r["params"] = self.params
        return r


def filename_to_uri(path: str) -> str:
    return urljoin('file:', pathname2url(path))


def uri_to_filename(uri: str) -> str:
    return url2pathname(urlparse(uri).path)


class Client(object):

    def __init__(self, process):
        self.process = process
        self.stdout_thread = threading.Thread(target=self.read_stdout)
        self.stdout_thread.start()
        self.stderr_thread = threading.Thread(target=self.read_stderr)
        self.stderr_thread.start()
        self.request_id = 0
        self.handlers = {}  # type: Dict[int, Callable]
        self.capabilities = {}  # type: Dict[str, Any]

    def set_capabilities(self, capabilities):
        self.capabilities = capabilities

    def has_capability(self, capability):
        return capability in self.capabilities

    def get_capability(self, capability):
        return self.capabilities.get(capability)

    def send_request(self, request: Request, handler: 'Callable'):
        self.request_id += 1
        if handler is not None:
            self.handlers[self.request_id] = handler
        self.send_payload(request.to_payload(self.request_id))

    def send_notification(self, notification: Notification):
        util.debug('notify: ' + notification.method)
        self.send_payload(notification.to_payload())

    def kill(self):
        self.process.kill()

    def send_payload(self, payload):
        try:
            message = format_request(payload)
            self.process.stdin.write(bytes(message, 'UTF-8'))
            self.process.stdin.flush()
        except BrokenPipeError as e:
            util.debug("client unexpectedly died:", e)

    def read_stdout(self):
        """
        Reads JSON responses from process and dispatch them to response_handler
        """
        ContentLengthHeader = b"Content-Length: "

        while self.process.poll() is None:
            try:

                in_headers = True
                content_length = 0
                while in_headers:
                    header = self.process.stdout.readline().strip()
                    if (len(header) == 0):
                        in_headers = False

                    if header.startswith(ContentLengthHeader):
                        content_length = int(header[len(ContentLengthHeader):])

                if (content_length > 0):
                    content = self.process.stdout.read(content_length).decode(
                        "UTF-8")

                    payload = None
                    try:
                        payload = json.loads(content)
                        limit = min(len(content), 200)
                        if payload.get("method") != "window/logMessage":
                            util.debug("got json: ", content[0:limit])
                    except IOError:
                        util.debug("Got a non-JSON payload: ", content)
                        continue

                    try:
                        if "error" in payload:
                            error = payload['error']
                            util.debug("got error: ", error)
                            sublime.status_message(error.get('message'))
                        elif "method" in payload:
                            if "id" in payload:
                                self.request_handler(payload)
                            else:
                                self.notification_handler(payload)
                        elif "id" in payload:
                            self.response_handler(payload)
                        else:
                            util.debug("Unknown payload type: ", payload)
                    except Exception as err:
                        util.debug("Error handling server content:", err)

            except IOError:
                printf("LSP stdout process ending due to exception: ",
                       sys.exc_info())
                self.process.terminate()
                self.process = None
                return

        util.debug("LSP stdout process ended.")

    def read_stderr(self):
        """
        Reads any errors from the LSP process.
        """
        while self.process.poll() is None:
            try:
                content = self.process.stderr.readline()
                util.debug("(stderr): ", content.strip())
            except IOError:
                utl.debug("LSP stderr process ending due to exception: ",
                          sys.exc_info())
                return

        util.debug("LSP stderr process ended.")

    def response_handler(self, response):
        try:
            handler_id = int(response.get("id"))  # dotty sends strings back :(
            result = response.get('result', None)
            if (self.handlers[handler_id]):
                self.handlers[handler_id](result)
            else:
                util.debug("No handler found for id" + response.get("id"))
        except Exception as e:
            util.debug("error handling response", handler_id)
            raise

    def request_handler(self, request):
        method = request.get("method")
        if method == "workspace/applyEdit":
            apply_workspace_edit(sublime.active_window(),
                                 request.get("params"))
        else:
            util.debug("Unhandled request", method)

    def notification_handler(self, response):
        method = response.get("method")
        if method == "textDocument/publishDiagnostics":
            Events.publish("document.diagnostics", response.get("params"))
        elif method == "window/showMessage":
            sublime.active_window().message_dialog(
                response.get("params").get("message"))
        elif method == "window/logMessage" and log_server:
            server_log(self.process.args[0],
                       response.get("params").get("message"))
        else:
            util.debug("Unhandled notification:", method)


class Events:
    listener_dict = dict()  # type: Dict[str, Callable[..., None]]

    @classmethod
    def subscribe(cls, key, listener):
        if key in cls.listener_dict:
            cls.listener_dict[key].append(listener)
        else:
            cls.listener_dict[key] = [listener]
        return lambda: cls.unsubscribe(key, listener)

    @classmethod
    def unsubscribe(cls, key, listener):
        if key in cls.listener_dict:
            cls.listener_dict[key].remove(listener)

    @classmethod
    def publish(cls, key, *args):
        if key in cls.listener_dict:
            for listener in cls.listener_dict[key]:
                listener(*args)

document_sync_initialized = False


def notify_did_open(view: sublime.View):
    if client:
        params = {
            "textDocument": {
                "uri": filename_to_uri(view.file_name()),
                "languageId": config.languageId,
                "text": view.substr(sublime.Region(0, view.size()))
            }
        }
        client.send_notification(Notification.didOpen(params))


def notify_did_save(view: sublime.View):
    if client:
        params = {"textDocument": {"uri": filename_to_uri(view.file_name())}}
        client.send_notification(Notification.didSave(params))


def notify_did_close(view: sublime.View):
    params = {"textDocument": {"uri": filename_to_uri(view.file_name())}}
    client.send_notification(Notification.didClose(params))


def initialize_document_sync(text_document_sync_kind):
    global document_sync_initialized
    if document_sync_initialized:
        return
    document_sync_initialized = True
    Events.subscribe('view.on_load_async', notify_did_open)
    Events.subscribe('view.on_activated_async', notify_did_open)
    Events.subscribe('view.on_modified_async', util.queue_did_change)
    Events.subscribe('view.on_post_save_async', notify_did_save)
    Events.subscribe('view.on_close', notify_did_close)


def handle_initialize_result(result, client, window, config):
    global didopen_after_initialize
    capabilities = result.get("capabilities")
    client.set_capabilities(capabilities)

    # TODO: These handlers is already filtered by syntax but does not need to
    # be enabled 2x per client
    # Move filtering?
    document_sync = capabilities.get("textDocumentSync")
    if document_sync:
        initialize_document_sync(document_sync)

    Events.subscribe('document.diagnostics', handle_diagnostics)
    Events.subscribe('view.on_close', remove_diagnostics)
    for view in didopen_after_initialize:
        notify_did_open(view)
    if show_status_messages:
        window.status_message("{} initialized".format(config.name))
    didopen_after_initialize = list()


def handle_initialize_result(result, client):
    global didopen_after_initialize
    capabilities = result.get("capabilities")
    client.set_capabilities(capabilities)
    document_sync = capabilities.get("textDocumentSync")
    util.debug('document_sync', document_sync)
    initialize_document_sync(document_sync)

    # for view in didopen_after_initialize:
    # notify_did_open(view)
    util.debug('init complete')
    #didopen_after_initialize = list()


def deleteDbIfExists():
    try:
        dx_folder = util.dxProjectFolder()
        if len(dx_folder) > 0:
            db_path = os.path.join(dx_folder, '.sfdx', 'tools', 'apex.db')
            if os.path.isfile(db_path):
                os.remove(db_path)
                print('db deleted')
    except Exception as e:
        print("db not deleted")


def start_server():
    deleteDbIfExists()
    working_dir = os.path.join(util.get_plugin_folder(), 'apex-jorje-lsp.jar')
    args = ['java', '-cp', working_dir, '-Dtrace.protocol=false',
            'apex.jorje.lsp.ApexLanguageServerLauncher']
    util.debug("starting " + str(args))
    si = None
    if os.name == "nt":
        si = subprocess.STARTUPINFO()  # type: ignore
        si.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW  # type: ignore
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=util.dxProjectFolder(),
            startupinfo=si)
        return Client(process)

    except Exception as err:
        util.debug(err)


def start_client():
    global client
    client = start_server()
    if not client:
        print("Could not start language server")
        return
    project_uri = filename_to_uri(util.dxProjectFolder())
    print('project_uri ', project_uri)
    initializeParams = {
        "processId": client.process.pid,
        "rootUri": project_uri,
        "capabilities": {
            "textDocument": {
                "completion": {
                    "completionItem": {
                        "snippetSupport": True
                    }
                }
            }
        }
    }
    client.send_request(
        Request.initialize(initializeParams),
        lambda result: handle_initialize_result(result, client))
    return client
