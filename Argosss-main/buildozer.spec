[app]

# Application metadata
title = ARGOS Absolute
package.name = argos_overlord
package.domain = org.sigtrip.argos
version = 1.33.0

# Source
source.dir = .
source.main = main_kivy.py
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt

# Requirements (Kivy + Android-compatible deps only)
requirements = python3==3.11.0,kivy==2.3.0,requests,pyjnius,android,paho-mqtt

# Orientation
orientation = portrait
fullscreen = 0

# Android permissions
android.permissions = INTERNET,BLUETOOTH_ADMIN,NFC,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,USB_HOST

# Android API / NDK / SDK
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.arch = arm64-v8a

# Enable Android features
android.accept_sdk_license = True

# Icons
#icon.filename = %(source.dir)s/argos_icon.png

[buildozer]
log_level = 2
warn_on_root = 0