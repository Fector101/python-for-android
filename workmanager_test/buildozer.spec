[app]

title = WorkManager Test
package.name = workmanagertest
package.domain = io.github.fector101
author = Fabian
version = 0.1

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,json,xml
source.exclude_dirs = bin, venv, .buildozer, tests, __pycache__, .pytest_cache

# Patched local p4a with WorkManager worker support (PR #2613 port).
p4a.source_dir = /home/fabian/Documents/widget/python-for-android
p4a.bootstrap = sdl3
requirements = python3, kivy==master
requirements.source.kivy = /home/fabian/Documents/widget/kivy
p4a.extra_args = --skip-prebuilt --worker=script:./workers/heartbeat.py --worker=audit:./workers/audit.py

android.enable_androidx = True
android.permissions = POST_NOTIFICATIONS
android.api = 36
android.minapi = 24
android.ndk = 29
android.archs = arm64-v8a
android.release_artifact = apk

fullscreen = 0
orientation = portrait

[buildozer]
log_level = 2
warn_on_root = 1
