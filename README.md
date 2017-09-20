# dxmate
Sublime Text 3 plugin to provide integration with the Salesforce DX CLI

## Instructions
1. Install the [DX CLI](https://developer.salesforce.com/tools/sfdxcli)
2. Run `Package Control: Install Package` from the command palette in Sublime and search for 'dxmate'
3. In the command pallette run `Package Control: Satisfy Dependencies`

## Features
Supports most useful CLI commands including:
* Create a project
* Authorize dev hub
* Create\open scratch orgs
* Push\Pull source
* Create Apex classes
* Create Lightning Apps, Components, Events, Interfaces and Tests
* Run tests for an org or specific class
* Run SOQL query

This plugin also supports:
* Code completion
* Diagnostics

Language services (e.g., code completion and diagnostics) are provided by the [Apex Language Server](https://developer.salesforce.com/docs/atlas.en-us.sfdx_ide2.meta/sfdx_ide2/sfdx_ide2_build_app_apex_language_server_protocol.htm)

## Settings

* `debug`: true or false to enable/disable printing debug statements to the sublime console
* `java_home`: location of your java binary if it is not in your PATH

## Getting Started
The plugin adds a new menu item (DXMate), context menu items, and command pallette items. Many of these are only enabled if you have an sfdx project currently opened.

If you don't have an sfdx proejct created, you can use DXMate > Project > Create Project to create one. If you do have one created, use Project > Add Folder to Project to add it to a project.

After that you can work with the rest of the commands (e.g., authorizing a dev hub and then creating a scratch org).

## To Do
* Additional settings (e.g., disable language services)
* Better handling of window opening (currently only starts language server if dx project is loaded when sublime is opened)
* Add goto symbol definition from latest language server update
* Add support for additional sfdx cli commands

## Compatibility
This should be compatible with windows, osx and linux with ST3.

It's been tested on windows 10 and ubuntu 16.


## Credits
* Most utility functions are based on or copied from [MavensMate](https://github.com/joeferraro/MavensMate-SublimeText). The syntax files for Apex are also from the MavensMate project.

* The LSP client code is adapted from the [Sublime LSP package](https://github.com/tomv564/LSP)
