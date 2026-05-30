[app]

title = Mental Math
package.name = mentalmath
package.domain = org.chen

source.dir = .
source.include_exts = py
source.exclude_dirs = .git,.venv-android,.buildozer,bin,__pycache__,matplotlib_cache
source.exclude_patterns = *.bak

version = 0.1.0
requirements = python3,kivy,matplotlib

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.allow_backup = True
android.debug_artifact = apk

log_level = 2
warn_on_root = 1
