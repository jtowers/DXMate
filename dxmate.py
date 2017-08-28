import sublime
import sublime_plugin
import os
import subprocess
import threading
import time
from dxmate.lib.printer import PanelPrinter
from dxmate.lib.threads import ThreadProgress
from dxmate.lib.threads import PanelThreadProgress
import ntpath

def dxProjectFolder():
	for window in sublime.windows():
		open_folders = window.folders()
		for folder in open_folders:
			for root, dirs, files in os.walk(folder, topdown=False):
				for name in files:
					if name == 'sfdx-project.json':
						return folder
		return ''


class LanguageServer:

	UBER_JAR_NAME = 'apex-jorje-lsp.jar'
	JDWP_DEBUG_PORT = 2739
	APEX_LANGUAGE_SERVER_MAIN = 'apex.jorje.lsp.ApexLanguageServerLauncher'
		
	def createServer(self):
		if(dxProjectFolder() != ''):
			self.deleteDbIfExists()
			uberJar = os.path.join(sublime.packages_path(), 'dxmate', self.UBER_JAR_NAME)
			args = ['javaw', '-cp', uberJar, '-Ddebug.internal.errors=true','-Ddebug.semantic.errors=false', self.APEX_LANGUAGE_SERVER_MAIN]
			p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.STDOUT, cwd=dxProjectFolder())
		


	def deleteDbIfExists(self):
		dx_folder = dxProjectFolder()
		if len(dx_folder) > 0:
			db_path = os.path.join(dx_folder, '.sfdx', 'tools', 'apex.db')
			if os.path.isfile(db_path):
				os.remove(db_path)
				print('db deleted')



#generic handler for writing text to an output panel (sublime text 3 requirement)
class DxmateOutputText(sublime_plugin.TextCommand):
	def run(self, edit, text,erase = False, *args, **kwargs):
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
        kw_region = kwargs.get('region', [0,0])
        status_region = sublime.Region(kw_region[0],kw_region[1])
        size = self.view.size()
        self.view.set_read_only(False)
        self.view.replace(edit, status_region, text)
        self.view.set_read_only(True)
        #self.view.show(size)

    def is_visible(self):
        return False

    def is_enabled(self):
        return True

    def description(self):
        return

ls = LanguageServer()
printer = None
def plugin_loaded():
	global ls
	global printer
	# not ready for language services yet
	#ls.createServer()
	active_window_id = sublime.active_window().id()
	printer = PanelPrinter.get(active_window_id)
	printer.write("sfdx plugin loaded", erase = True)

class DxmateRunFileTestsCommand(sublime_plugin.WindowCommand):
	def run(self):
		self.dx_folder = dxProjectFolder()
		self.active_file = sublime.active_window().active_view().file_name()
		self.active_file = ntpath.split(self.active_file)[1].replace('.cls', '')
		self.class_name = 'ApexClassName'
		t = threading.Thread(target=self.run_command)
		t.start()
		printer.show()
		printer.write('\nRunning Tests')
		printer.write('\nResult: ')
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Running tests', 'Tests run')
		PanelThreadProgress(t, 'Running Tests')

	def is_enabled(self):
		self.dx_folder = dxProjectFolder()
		if(self.dx_folder == ''):
			return False
		self.active_file = sublime.active_window().active_view().file_name()
		if not self.active_file.endswith('.cls'):
			return False
		return True

	def run_command(self):
		args = ['sfdx', 'force:apex:test:run', '-r', 'human', '-l', 'RunSpecifiedTests', '-n', self.class_name]
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=self.dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		if p.returncode == 0:
			printer.write('\n' + str(out,'utf-8'))
		else:
			printErr = err
			if err is None or err == '':
				printErr = out
			printer.write('\n' + str(printErr,'utf-8'))

class DxmateRunOrgTestsCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		
		self.dx_folder = dxProjectFolder()
		sublime.active_window().show_input_panel('Org (leave blank for default)', '', self.run_tests, None, None)
		
	
	def run_tests(self, input):
		self.test_org = input
		printer.show()
		printer.write('\nRunning Org Tests')
		printer.write('\nResult: ')
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Running Org Tests', 'Org tests run')
		PanelThreadProgress(t, 'Running Org Tests')

	def is_enabled(self):
		self.dx_folder = dxProjectFolder()
		if self.dx_folder == '':
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
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=self.dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		if p.returncode == 0:
			printer.write('\n' + str(out,'utf-8'))
		else:
			printErr = err
			if err is None or err == '':
				printErr = out
			printer.write('\n' + str(printErr,'utf-8'))


class DxmatePushSourceCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.dx_folder = dxProjectFolder()
		printer.show()
		printer.write('\nPushing Source')
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Pushing Source', 'Source Pushed')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Source Pushed')
	
	def is_enabled(self):
		self.dx_folder = dxProjectFolder()
		if self.dx_folder == '':
			return False
		return True

	def run_command(self):
		args = ['sfdx', 'force:source:push']
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=self.dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\n' + str(out,'utf-8'))
		else:
			printErr = err
			if not err is None and not err == '':
				printErr = out
			else:
				printer.write('\nError pushing source')
			printer.write('\n' + str(printErr,'utf-8'))

class DxmatePullSourceCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.dx_folder = dxProjectFolder()
		printer.show()
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Pulling Source', 'Source Pulled')
		printer.write('\nPulling Source')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Source Pulled')
	
	def is_enabled(self):
		self.dx_folder = dxProjectFolder()
		if self.dx_folder == '':
			return False
		return True

	def run_command(self):
		args = ['sfdx', 'force:source:pull']
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=self.dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\n' + str(out,'utf-8'))
		else:
			printErr = err
			if not err is None and not err == '':
				printErr = out
			else:
				printer.write('\nError pulling source')
			printer.write('\n' + str(printErr,'utf-8'))

class DxmateOpenScratchOrgCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.dx_folder = dxProjectFolder()
		printer.show()
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Opening Org', 'Org Opened')
		printer.write('\nOpening Org')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Org Opened')
	
	def is_enabled(self):
		self.dx_folder = dxProjectFolder()
		if self.dx_folder == '':
			return False
		return True

	def run_command(self):
		args = ['sfdx', 'force:org:open']
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=self.dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\nScratch org opened')
		else:
			printer.write('\nError opening')
			printer.write('\n' + str(err,'utf-8'))



class DxmateCreateScratchOrgCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.dx_folder = dxProjectFolder()
		self.def_file = os.path.join(self.dx_folder, 'config', 'project-scratch-def.json')
		sublime.active_window().show_input_panel('Class Name', self.def_file, self.create_org, None, None)
		
	def create_org(self, input):
		printer.show()
		self.def_file = input;
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Creating Scratch Org', 'Scratch Org Created')
		printer.write('\nCreatin Scratch Org')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Scratch Org Created')

	def is_enabled(self):
		self.dx_folder = dxProjectFolder()
		if self.dx_folder == '':
			return False
		return True

	def run_command(self):
		args = ['sfdx', 'force:org:create', '-f', self.def_file, '-a', 'ScratchOrg', '-s']
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=self.dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\nScratch org created')
		else:
			printer.write('\nError creating scratch org')
			printer.write('\n' + str(err,'utf-8'))



class DxmateAuthDevHubCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		printer.show()
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Opening Auth Page', 'Auth Page Opened')
		printer.write('\nOpening Auth Page')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Auth Page Opened')

	def is_enabled(self):
		dx_folder = dxProjectFolder()
		if dx_folder == '':
			return False
		return True

	def run_command(self):
		dx_folder = dxProjectFolder()
		args = ['sfdx', 'force:auth:web:login', '-d', '-s', '-a', 'DevHub']
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\nDevHub authorized')
		else:
			printer.write('\nError authorizing Dev Hub:')
			printer.write('\n' + str(err,'utf-8'))



class DxmateCreateApexClassCommand(sublime_plugin.WindowCommand):
	def run(self, paths = []):
		if len(paths) != 1 or  (len(paths) > 0 and os.path.isfile(paths[0])):
			printer.show()
			printer.write('\nPlease select a single folder save the class')
			return

		self.class_name = 'ApexClassName'
		self.class_dir = paths[0]
		sublime.active_window().show_input_panel('Class Name', self.class_name, self.create_class, None, None)

	def is_enabled(self, paths = []):
		dx_folder = dxProjectFolder()
		print(dx_folder)
		if(dx_folder == ''):
			return False
		if len(paths) != 1 or  (len(paths) > 0 and os.path.isfile(paths[0])):
			return False
		return True

	def create_class(self, input):
		self.class_name = input
		printer.show()
		t = threading.Thread(target = self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Creating Apex Class', 'Apex Class Created')
		printer.write('\nCreating Apex Class')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Apex Class Created')

	def run_command(self):
		dx_folder = dxProjectFolder()
		args = ['sfdx', 'force:apex:class:create', '-n', self.class_name, '-d', self.class_dir]
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\nApex class created')
			file = os.path.join(self.class_dir, self.class_name + '.cls')
			sublime.active_window().open_file(file)
		else:
			printer.write('\nError creating Apex Class:')
			printer.write('\n' + str(err,'utf-8'))


class DxmateUpgradeProjectCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		printer.show()
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Upgrading Project', 'Project Upgraded')
		printer.write('\nUpgrading Project')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Project Upgraded')

	def is_enabled(self):
		dx_folder = dxProjectFolder()
		if dx_folder == '':
			return False
		return True

	def run_command(self):
		dx_folder = dxProjectFolder()
		args = ['sfdx', 'force:project:upgrade', '-f']
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.PIPE, startupinfo=startupinfo, cwd=dx_folder)
		
		p.wait()

		out,err = p.communicate()
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\nProject upgraded')
		else:
			printer.write('\nError upgrading project:')
			printer.write('\n' + str(err,'utf-8'))



class DxmateCreateProjectCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		self.edit = edit
		self.project_name = ''
		self.template = 'Defaultsfdx-project.json'
		self.project_path = ''
		self.namespace = None
		sublime.active_window().show_input_panel('Project Name', self.project_name, self.create_project_name, None, None)

	def create_project_name(self, input):
		self.project_name = input
		sublime.active_window().show_input_panel('Project Template', self.template, self.create_project_template, None, None)
	
	def create_project_template(self, input):
		self.project_template = input
		sublime.active_window().show_input_panel('Project Path', self.project_path, self.create_project_namespace, None, None)

	def create_project_namespace(self, input):
		self.project_path = input
		sublime.active_window().show_input_panel('Project Namespace', '', self.create_project, None, None)

	def create_project(self, input):
		printer.show()
		self.namespace = input
		t = threading.Thread(target=self.run_command)
		t.start()
		t.printer = printer
		t.process_id  = time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
		ThreadProgress(t, 'Creating Project', 'Project Created')
		printer.write('\nCreating Project')
		printer.write('\nResult: ')
		PanelThreadProgress(t, 'Project Created')
	
	def run_command(self):
		args = ['sfdx', 'force:project:create', '-n', self.project_name, '-t', self.template, '-d', self.project_path]
		if self.namespace is not None and self.namespace != '':
			args.push('-s')
			args.push(self.namespace)
		startupinfo = None
		if os.name == 'nt':
		    startupinfo = subprocess.STARTUPINFO()
		    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
		p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr = subprocess.STDOUT, startupinfo=startupinfo)
		
		p.wait()

		t = p.communicate()[0]
		r = p.returncode
		print(r)
		if p.returncode == 0:
			printer.write('\nProject created')
		else:
			printer.write('\nError creating project:')
			printer.write('\n' + t)