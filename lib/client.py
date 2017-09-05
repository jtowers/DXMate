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

from .request import *
from .notification import *
from .util import util
from .event_hub import EventHub
import sublime
import threading
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
            message = util.format_request(payload)
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
                utl.util.debug("LSP stderr process ending due to exception: ",
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
            EventHub.publish("document.diagnostics", response.get("params"))
        elif method == "window/showMessage":
            sublime.active_window().message_dialog(
                response.get("params").get("message"))
        elif method == "window/logMessage" and log_server:
            server_log(self.process.args[0],
                       response.get("params").get("message"))
        else:
            util.debug("Unhandled notification:", method)

def initialize_on_open(view: sublime.View):
    global didopen_after_initialize
    config = config_for_scope(view)
    if config:
        if config.name not in window_clients(view.window()):
            didopen_after_initialize.append(view)
            get_window_client(view, config)
