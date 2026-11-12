# CHANGELOG

## Current

## v0.3.4

* Add support for embedded targets files
* Change defaut log level to info, remove `-v/--verbose` and add a `-q/--quiet` flag.
* CI : add build of a binary using pyinstaller

## v0.3.3

* Upgrade deps
* Migration gitlab-ci

## v0.3.2

* Upgrade deps

## v0.3.1

* Fix issue related to timestamp/attribute conversion

## v0.3.0

* Support for folder output type
* Fix for folder input type
* Add `-l, --long_file_name, --no-long_file_name Copy long file name (path > 215) in the LongFileNames directory (default: True)`
* Add `-T {zip,folder}, --type {zip,folder} Output type (zip or folder)`
* Add AlreadyExist skip reason when file already exist on dest