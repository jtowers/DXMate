# dxmate
Sublime Text 3 plugin to provide integration with the Salesforce DX CLI

## Instructions
1. Install the [DX CLI](https://developer.salesforce.com/tools/sfdxcli)
2. Run `Package Control: Install Package` from the command palette in Sublime and search for 'dxmate' or clone this package into your Packages directory

## Features
Supports most useful CLI commands including:
* Create a project
* Authorize dev hub
* Create\open scratch orgs
* Push\Pull source
* Create Apex classes
* Run tests for an org or specific class

Uses syntax highlighting from MavensMate

Supports code completion with the [Apex Language Server](https://developer.salesforce.com/docs/atlas.en-us.sfdx_ide2.meta/sfdx_ide2/sfdx_ide2_build_app_apex_language_server_protocol.htm)

## Settings

* `debug`: true or false to enable/disable printing debug statements to the sublime console
* `java_home`: location of your java binary if it is not in your PATH

## To Do
* Additional settings (e.g., disable language services)
* Better handling of window opening (currently only starts language server if dx project is loaded when sublime is opened)
* Additional language services


## Credits
Most utility functions are based on or copied from [MavensMate](https://github.com/joeferraro/MavensMate-SublimeText)
The LSP client code is cloned from the [Sublime LSP package](https://github.com/tomv564/LSP)
