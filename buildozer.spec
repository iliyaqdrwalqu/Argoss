[app]

# Application metadata
title = ARGOS Universal OS
package.name = argos_universal
package.domain = org.labuaqlysnecy.argos
version = 1.4.0

# Source
source.dir = .
source.main = main_kivy.py
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt,md,xml
source.include_patterns = assets/*,config/*,res/*

# Requirements
requirements = python3==3.11.0,kivy==2.3.0,requests,pyjnius==1.6.1,android,paho-mqtt,python-dotenv

# Orientation
orientation = portrait
fullscreen = 0

# Android permissions
android.permissions = INTERNET,BLUETOOTH_ADMIN,NFC,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,USB_HOST,ACCESS_NETWORK_STATE,FOREGROUND_SERVICE,REQUEST_INSTALL_PACKAGES

# Android API / NDK / SDK
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.arch = arm64-v8a

# [FIX-SAI-FILEPROVIDER]
# Добавляем FileProvider чтобы SAI видел DISPLAY_NAME при установке APK.
# Без этого Content Provider возвращает null для имени файла.
android.add_src = res

# Метаданные для FileProvider — путь к xml описанию путей
android.manifest.attributes = android:requestLegacyExternalStorage="true"

# Добавляем FileProvider в AndroidManifest через extra_manifest_xml
android.extra_manifest_xml = .buildozer/android/platform/provider_meta.xml

# Enable Android features
android.accept_sdk_license = True

# Icons
icon.filename = %(source.dir)s/assets/argos_icon_512.png

[buildozer]
log_level = 2
warn_on_root = 0
p4a.hook = p4a_hook.py
