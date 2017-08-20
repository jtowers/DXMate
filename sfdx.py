import sublime
import sublime_plugin
import os


class ExampleCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.view.insert(edit, 0, "Hello, World!")

UBER_JAR_NAME = 'apex-jorje-lsp.jar'
JDWP_DEBUG_PORT = 2739
APEX_LANGUAGE_SERVER_MAIN = 'apex.jorje.lsp.ApexLanguageServerLauncher'

def dxProjectFolder():
	open_folders = sublime.active_window().folders()
	for folder in open_folders:
		for root, dirs, files in os.walk(folder, topdown=False):
			for name in files:
				if name == 'sfdx-project.json':
					return folder
	return ''

def createServer():
	deleteDbIfExists()
	uberJar = os.path.join(sublime.packages_path(), 'salesforce-dx', UBER_JAR_NAME)


def deleteDbIfExists():
	dx_folder = dxProjectFolder()
	if len(dx_folder) > 0:
		db_path = os.path.join(dx_folder, '.sfdx', 'tools', 'apex.db')
		if os.path.isfile(db_path):
			os.remove(db_path)
			print('db deleted')

class DeleteDbCommand(sublime_plugin.TextCommand):
	createServer()
		