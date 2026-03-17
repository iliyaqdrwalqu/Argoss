[app]

# Application metadata
title = ARGOS Universal OS
package.name = argos_universal
package.domain = org.labuaqlysnecy.argos
version = 1.4.0

# Source
source.dir = .
source.main = main_kivy.py
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt,md
source.include_patterns = assets/*,config/*

# Requirements (Kivy + Android-compatible deps only)
requirements = python3==3.11.0,kivy==2.3.0,requests,pyjnius,android,paho-mqtt,python-dotenv

# Orientation
orientation = portrait
fullscreen = 0

# Android permissions
android.permissions = INTERNET,BLUETOOTH_ADMIN,NFC,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,USB_HOST,ACCESS_NETWORK_STATE,FOREGROUND_SERVICE

# Android API / NDK / SDK
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.arch = arm64-v8a

# Enable Android features
android.accept_sdk_license = True

# Icons
icon.filename = %(source.dir)s/assets/argos_icon_512.png

[buildozer]
log_level = 2
warn_on_root = 0
