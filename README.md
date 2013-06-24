# GReader-Archive

Google Reader are dying, backup our data ASAP,the *takeout* if not enough,we can do more using python.

## Usage

* run `python download.py` and it will prompt for your Google username and password to begin the download process
* all of the data are gzip compressed to save your space, I have 500+ feeds and 10+ are planet feeds and onlt accupy less than 2G disk space

## Using Config File

due to some exceptions we can not catch and handle, you may run this script again and again,the inputting of username, password and choose of mode is very annnoying, you can use config file to automate this process.

1. copy config.ini.default to config.ini
2. edit config.ini

## Thanks

Aulddays for the first version of  GReader-Archive
